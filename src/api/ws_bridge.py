import asyncio
import json
import logging
import time
from fastapi import WebSocket, WebSocketDisconnect

from src.api.deps import app_state
from src.collector import collector_status

logger = logging.getLogger(__name__)

DEBOUNCE_MS = 150


class WSBridge:
    def __init__(self):
        self._clients: set[WebSocket] = set()
        self._queue: asyncio.Queue | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._last_push = 0.0

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop
        self._queue = asyncio.Queue()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._clients.add(ws)
        logger.info(f"WS client connected, total={len(self._clients)}")

    def disconnect(self, ws: WebSocket):
        self._clients.discard(ws)
        logger.info(f"WS client disconnected, total={len(self._clients)}")

    def on_book_change(self):
        if self._loop is None or self._queue is None:
            return
        try:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, "book_update")
        except Exception:
            pass

    def push_risk_update(self):
        if self._loop is None or self._queue is None:
            return
        try:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, "risk_update")
        except Exception:
            pass

    async def broadcaster(self):
        self._loop = asyncio.get_event_loop()
        self._queue = asyncio.Queue()

        while True:
            msg_type = await self._queue.get()

            now = time.monotonic()
            if msg_type == "book_update" and (now - self._last_push) < DEBOUNCE_MS / 1000.0:
                continue
            self._last_push = now

            data = self._build_message(msg_type)
            if data is None:
                continue

            payload = json.dumps(data)
            dead = set()
            for ws in self._clients:
                try:
                    await ws.send_text(payload)
                except Exception:
                    dead.add(ws)
            self._clients -= dead

    def _build_message(self, msg_type: str) -> dict | None:
        bs = app_state.book_state
        if bs is None:
            return None

        if msg_type == "book_update":
            positions = []
            flag_map = {m.contract_id: m.liquidity_flag for m in app_state.risk_cache.liquidity_metrics}
            for pos in bs.positions:
                pnl = bs.get_position_pnl(pos)
                positions.append({
                    "contract_id": pos.contract_id,
                    "title": pos.title,
                    "quantity": pos.quantity,
                    "entry_price": pos.entry_price,
                    "current_mid": pos.current_mid,
                    "market_prob": pos.market_prob,
                    "model_prob": pos.model_prob,
                    "edge": pos.edge,
                    "tte_days": pos.tte_days,
                    "pnl": pnl,
                    "liquidity_flag": flag_map.get(pos.contract_id, "-"),
                })
            return {
                "type": "book_update",
                "nav": bs.compute_nav(),
                "cash": bs.cash_balance,
                "portfolio_value": bs.portfolio_value,
                "total_pnl": bs.get_total_pnl(),
                "ws_connected": bs.ws_connected,
                "collector_running": collector_status(),
                "positions": positions,
            }

        if msg_type == "risk_update":
            rc = app_state.risk_cache
            data: dict = {"type": "risk_update"}

            if rc.var_result is not None:
                r = rc.var_result
                component_var = []
                if r.component_var is not None and len(r.component_var) > 0:
                    for i, pos in enumerate(bs.positions):
                        if i < len(r.component_var):
                            component_var.append({
                                "contract_id": pos.contract_id,
                                "value": float(r.component_var[i]),
                            })
                data["var"] = {
                    "var_95": r.var_95,
                    "var_99": r.var_99,
                    "cvar_95": r.cvar_95,
                    "cvar_99": r.cvar_99,
                    "p_ruin": r.p_ruin,
                    "component_var": component_var,
                    "pnl_distribution": r.pnl_distribution.tolist(),
                }

            if rc.kelly_result is not None:
                kr = rc.kelly_result
                bankroll = bs.bankroll or 1.0
                allocations = []
                for i, cid in enumerate(kr.contract_ids):
                    tgt = kr.target_fractions[i] * bankroll
                    pos = bs.positions[i] if i < len(bs.positions) else None
                    current = pos.quantity * ((1.0 - pos.entry_price) if pos.quantity < 0 else pos.entry_price) if pos else 0.0
                    allocations.append({
                        "contract_id": cid,
                        "raw_kelly": float(kr.raw_kelly[i]),
                        "target_fraction": float(kr.target_fractions[i]),
                        "target_dollars": float(tgt),
                        "current_dollars": float(current),
                        "trade_dollars": float(tgt - current),
                    })
                data["kelly"] = {
                    "bankroll": bankroll,
                    "cash": bs.cash_balance,
                    "portfolio_value": bs.portfolio_value,
                    "allocations": allocations,
                }

            if rc.liquidity_metrics:
                data["liquidity"] = [
                    {
                        "contract_id": m.contract_id,
                        "spread_pct": m.spread_pct,
                        "depth_at_best_bid": m.depth_at_best_bid,
                        "depth_at_best_ask": m.depth_at_best_ask,
                        "liquidation_slippage": m.liquidation_slippage,
                        "liquidity_flag": m.liquidity_flag,
                    }
                    for m in rc.liquidity_metrics
                ]

            return data

        return None


bridge = WSBridge()
