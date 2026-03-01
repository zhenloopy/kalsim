import asyncio
import logging
import time
from contextlib import asynccontextmanager

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from src.api.deps import app_state
from src.api.routes_portfolio import router as portfolio_router
from src.api.routes_risk import router as risk_router
from src.api.routes_settings import router as settings_router

logger = logging.getLogger(__name__)

logging.basicConfig(
    filename="kalsim.log",
    level=logging.DEBUG,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)


def _compute_risk():
    from src.var_engine import simulate_pnl
    from src.kelly import kelly_optimize
    from src.liquidity import compute_liquidity_metrics

    bs = app_state.book_state
    positions = bs.positions
    if not positions:
        return

    pos_dicts = [p.model_dump() for p in positions]
    n = len(pos_dicts)
    corr = np.eye(n)

    try:
        var_result = simulate_pnl(pos_dicts, corr, n_sims=100_000, seed=42)
        app_state.risk_cache.var_result = var_result
    except Exception:
        pass

    try:
        bankroll = bs.bankroll or 1.0
        kelly_result = kelly_optimize(pos_dicts, bankroll=bankroll, kelly_fraction=0.25)
        app_state.risk_cache.kelly_result = kelly_result
    except Exception:
        pass

    metrics = []
    for pos in positions:
        ob = bs.get_orderbook_for_api(pos.contract_id)
        if ob is None:
            ob = {"yes": [], "no": []}
        try:
            m = compute_liquidity_metrics(
                pos.contract_id, ob, quantity=pos.quantity,
                entry_price=pos.entry_price, tte_days=pos.tte_days,
            )
            metrics.append(m)
        except Exception:
            pass
    app_state.risk_cache.liquidity_metrics = metrics


def _record_nav_snapshot():
    from src.nav_store import NavSnapshot
    bs = app_state.book_state
    ns = app_state.nav_store
    if ns is None or bs is None:
        return
    nav = bs.compute_nav()
    pnl = bs.get_total_pnl()
    snap = NavSnapshot(
        timestamp_utc=time.time(),
        nav=nav,
        cash=bs.cash_balance,
        portfolio_value=bs.portfolio_value,
        unrealized_pnl=pnl,
        position_count=len(bs.positions),
    )
    ns.record(snap)


@asynccontextmanager
async def lifespan(app: FastAPI):
    import os
    import sys
    from dotenv import load_dotenv
    load_dotenv()

    from run import check_credentials, fetch_initial_state
    from src.ws_client import KalshiWS
    from src.nav_store import NavStore

    check_credentials()

    logger.info("Fetching initial state...")
    book_state, kalshi_config = fetch_initial_state()
    nav_store = NavStore()

    app_state.book_state = book_state
    app_state.nav_store = nav_store
    app_state.kalshi_config = kalshi_config

    ws_client = KalshiWS(kalshi_config, book_state)
    app_state.ws_client = ws_client
    await ws_client.start()

    from src.api.ws_bridge import bridge
    book_state.on_change(bridge.on_book_change)
    broadcaster_task = asyncio.create_task(bridge.broadcaster())

    async def risk_loop():
        while True:
            try:
                await asyncio.to_thread(_compute_risk)
                bridge.push_risk_update()
            except Exception as e:
                logger.error(f"Risk loop error: {e}")
            await asyncio.sleep(10)

    async def nav_loop():
        while True:
            try:
                await asyncio.to_thread(_record_nav_snapshot)
            except Exception as e:
                logger.error(f"NAV snapshot error: {e}")
            await asyncio.sleep(60)

    risk_task = asyncio.create_task(risk_loop())
    nav_task = asyncio.create_task(nav_loop())

    logger.info("API server started")
    yield

    risk_task.cancel()
    nav_task.cancel()
    broadcaster_task.cancel()
    await ws_client.stop()
    nav_store.close()
    logger.info("API server stopped")


app = FastAPI(title="kalsim API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(portfolio_router)
app.include_router(risk_router)
app.include_router(settings_router)


@app.websocket("/api/ws")
async def websocket_endpoint(ws: WebSocket):
    from src.api.ws_bridge import bridge
    await bridge.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        bridge.disconnect(ws)
