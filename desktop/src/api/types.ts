export interface Position {
  contract_id: string;
  title: string;
  platform: string;
  quantity: number;
  entry_price: number;
  current_mid: number;
  market_prob: number;
  model_prob: number;
  edge: number;
  resolves_at: string;
  tte_days: number;
  fee_adjusted_breakeven: number;
  pnl: number;
  liquidity_flag: string;
}

export interface StatusResponse {
  nav: number;
  cash: number;
  portfolio_value: number;
  total_pnl: number;
  position_count: number;
  ws_connected: boolean;
  collector_running: boolean;
}

export interface OrderbookLevel {
  price: number;
  quantity: number;
}

export interface Orderbook {
  ticker: string;
  bids: OrderbookLevel[];
  asks: OrderbookLevel[];
}

export interface ComponentVaR {
  contract_id: string;
  value: number;
}

export interface VaRData {
  var_95: number;
  var_99: number;
  cvar_95: number;
  cvar_99: number;
  p_ruin: number;
  component_var: ComponentVaR[];
  pnl_distribution: number[];
}

export interface KellyAllocation {
  contract_id: string;
  raw_kelly: number;
  target_fraction: number;
  target_dollars: number;
  current_dollars: number;
  trade_dollars: number;
}

export interface KellyData {
  bankroll: number;
  cash: number;
  portfolio_value: number;
  allocations: KellyAllocation[];
}

export interface LiquidityMetric {
  contract_id: string;
  spread_pct: number;
  depth_at_best_bid: number;
  depth_at_best_ask: number;
  liquidation_slippage: number;
  liquidity_flag: string;
}

export interface ScenarioPositionPnl {
  contract_id: string;
  pnl: number;
}

export interface ScenarioResult {
  name: string;
  description: string;
  pnl: number;
  exceeds_var99: boolean;
  position_pnls: ScenarioPositionPnl[];
}

export interface CollectorStatus {
  running: boolean;
  interval: number;
}

export interface StorageInfo {
  size_bytes: number;
  nav_snapshots: number;
  position_snapshots: number;
}

export interface NavPoint {
  timestamp: number;
  nav: number;
  cash: number;
  portfolio_value: number;
  unrealized_pnl: number;
  position_count: number;
}

export interface NavOHLC {
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
}

export interface BookUpdate {
  type: "book_update";
  nav: number;
  cash: number;
  portfolio_value: number;
  total_pnl: number;
  ws_connected: boolean;
  collector_running: boolean;
  positions: Position[];
}

export interface RiskUpdate {
  type: "risk_update";
  var?: VaRData;
  kelly?: KellyData;
  liquidity?: LiquidityMetric[];
}

export type WSMessage = BookUpdate | RiskUpdate;
