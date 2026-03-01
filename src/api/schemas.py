from pydantic import BaseModel


class PositionResponse(BaseModel):
    contract_id: str
    title: str
    platform: str
    quantity: int
    entry_price: float
    current_mid: float
    market_prob: float
    model_prob: float
    edge: float
    resolves_at: str
    tte_days: float
    fee_adjusted_breakeven: float
    pnl: float
    liquidity_flag: str


class StatusResponse(BaseModel):
    nav: float
    cash: float
    portfolio_value: float
    total_pnl: float
    position_count: int
    ws_connected: bool
    collector_running: bool


class NavPointResponse(BaseModel):
    timestamp: float
    nav: float
    cash: float
    portfolio_value: float
    unrealized_pnl: float
    position_count: int


class NavOHLCResponse(BaseModel):
    timestamp: float
    open: float
    high: float
    low: float
    close: float


class OrderbookLevelResponse(BaseModel):
    price: float
    quantity: int


class OrderbookResponse(BaseModel):
    ticker: str
    bids: list[OrderbookLevelResponse]
    asks: list[OrderbookLevelResponse]


class VaRResponse(BaseModel):
    var_95: float
    var_99: float
    cvar_95: float
    cvar_99: float
    p_ruin: float
    component_var: list[dict]
    pnl_distribution: list[float]


class KellyAllocationResponse(BaseModel):
    contract_id: str
    raw_kelly: float
    target_fraction: float
    target_dollars: float
    current_dollars: float
    trade_dollars: float


class KellyResponse(BaseModel):
    bankroll: float
    cash: float
    portfolio_value: float
    allocations: list[KellyAllocationResponse]


class LiquidityMetricResponse(BaseModel):
    contract_id: str
    spread_pct: float
    depth_at_best_bid: int
    depth_at_best_ask: int
    liquidation_slippage: float
    liquidity_flag: str


class ScenarioPositionPnl(BaseModel):
    contract_id: str
    pnl: float


class ScenarioResultResponse(BaseModel):
    name: str
    description: str
    pnl: float
    exceeds_var99: bool
    position_pnls: list[ScenarioPositionPnl]


class CollectorStatusResponse(BaseModel):
    running: bool
    interval: int


class StorageInfoResponse(BaseModel):
    size_bytes: int
    nav_snapshots: int
    position_snapshots: int
