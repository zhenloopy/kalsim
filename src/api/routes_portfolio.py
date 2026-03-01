import time
from fastapi import APIRouter

from src.api.deps import app_state
from src.api.schemas import (
    PositionResponse, StatusResponse, NavPointResponse, NavOHLCResponse,
    OrderbookResponse, OrderbookLevelResponse,
)
from src.collector import collector_status

router = APIRouter(prefix="/api")


@router.get("/status")
def get_status() -> StatusResponse:
    bs = app_state.book_state
    return StatusResponse(
        nav=bs.compute_nav(),
        cash=bs.cash_balance,
        portfolio_value=bs.portfolio_value,
        total_pnl=bs.get_total_pnl(),
        position_count=len(bs.positions),
        ws_connected=bs.ws_connected,
        collector_running=collector_status(),
    )


@router.get("/positions")
def get_positions() -> list[PositionResponse]:
    bs = app_state.book_state
    rc = app_state.risk_cache
    flag_map = {m.contract_id: m.liquidity_flag for m in rc.liquidity_metrics}

    result = []
    for pos in bs.positions:
        pnl = bs.get_position_pnl(pos)
        result.append(PositionResponse(
            contract_id=pos.contract_id,
            title=pos.title,
            platform=pos.platform,
            quantity=pos.quantity,
            entry_price=pos.entry_price,
            current_mid=pos.current_mid,
            market_prob=pos.market_prob,
            model_prob=pos.model_prob,
            edge=pos.edge,
            resolves_at=pos.resolves_at.isoformat(),
            tte_days=pos.tte_days,
            fee_adjusted_breakeven=pos.fee_adjusted_breakeven,
            pnl=pnl,
            liquidity_flag=flag_map.get(pos.contract_id, "-"),
        ))
    return result


RANGES = {
    "1H": 3600, "6H": 6 * 3600, "1D": 86400,
    "1W": 7 * 86400, "2W": 14 * 86400, "1M": 30 * 86400,
    "6M": 180 * 86400, "1Y": 365 * 86400, "5Y": 5 * 365 * 86400,
}


def _resolve_range(range: str, start: float | None, end: float | None) -> tuple[float, float]:
    if start is not None and end is not None:
        return start, end
    span = RANGES.get(range, RANGES["1W"])
    now = time.time()
    return now - span, now


@router.get("/nav/history")
def get_nav_history(
    range: str = "1W",
    start: float | None = None,
    end: float | None = None,
    max_points: int = 2000,
    mode: str = "line",
    bucket: int | None = None,
) -> list[NavPointResponse] | list[NavOHLCResponse]:
    s, e = _resolve_range(range, start, end)

    if mode == "ohlc":
        b = bucket if bucket else int((e - s) / 80)
        candles = app_state.nav_store.query_ohlc(s, e, b)
        return [
            NavOHLCResponse(
                timestamp=c.timestamp_utc,
                open=c.open,
                high=c.high,
                low=c.low,
                close=c.close,
            )
            for c in candles
        ]

    snapshots = app_state.nav_store.query(s, e, max_points=max_points)
    return [
        NavPointResponse(
            timestamp=s.timestamp_utc,
            nav=s.nav,
            cash=s.cash,
            portfolio_value=s.portfolio_value,
            unrealized_pnl=s.unrealized_pnl,
            position_count=s.position_count,
        )
        for s in snapshots
    ]


@router.get("/positions/{ticker}/orderbook")
def get_orderbook(ticker: str) -> OrderbookResponse:
    bs = app_state.book_state
    ob = bs.get_orderbook_for_api(ticker)
    if ob is None:
        return OrderbookResponse(ticker=ticker, bids=[], asks=[])

    yes_levels = ob.get("yes", [])
    no_levels = ob.get("no", [])

    bids = [
        OrderbookLevelResponse(
            price=p / 100.0 if p > 1 else p,
            quantity=q,
        )
        for p, q in yes_levels
    ]
    asks = [
        OrderbookLevelResponse(
            price=1.0 - (p / 100.0 if p > 1 else p),
            quantity=q,
        )
        for p, q in no_levels
    ]
    return OrderbookResponse(ticker=ticker, bids=bids, asks=asks)
