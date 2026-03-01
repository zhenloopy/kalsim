const API_BASE = "http://127.0.0.1:8321";

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  return res.json();
}

export const api = {
  getStatus: () => fetchJSON<import("./types").StatusResponse>("/api/status"),
  getPositions: () => fetchJSON<import("./types").Position[]>("/api/positions"),
  getOrderbook: (ticker: string) =>
    fetchJSON<import("./types").Orderbook>(
      `/api/positions/${encodeURIComponent(ticker)}/orderbook`
    ),
  getVaR: () => fetchJSON<import("./types").VaRData | null>("/api/risk/var"),
  getKelly: () =>
    fetchJSON<import("./types").KellyData | null>("/api/risk/kelly"),
  getLiquidity: () =>
    fetchJSON<import("./types").LiquidityMetric[]>("/api/risk/liquidity"),
  getScenarios: () =>
    fetchJSON<import("./types").ScenarioResult[]>("/api/risk/scenarios"),
  submitScenario: (jsonStr: string) =>
    fetchJSON<import("./types").ScenarioResult>("/api/risk/scenarios", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ json_str: jsonStr }),
    }),
  refreshRisk: () =>
    fetchJSON<{ status: string }>("/api/risk/refresh", { method: "POST" }),
  getNavHistory: (range: string, maxPoints = 2000) =>
    fetchJSON<import("./types").NavPoint[]>(
      `/api/nav/history?range=${range}&max_points=${maxPoints}`
    ),
  getNavOHLC: (start: number, end: number, bucket: number) =>
    fetchJSON<import("./types").NavOHLC[]>(
      `/api/nav/history?mode=ohlc&start=${start}&end=${end}&bucket=${bucket}`
    ),
  getCollectorStatus: () =>
    fetchJSON<import("./types").CollectorStatus>("/api/collector/status"),
  startCollector: (interval: number) =>
    fetchJSON<import("./types").CollectorStatus>(
      `/api/collector/start?interval=${interval}`,
      { method: "POST" }
    ),
  stopCollector: () =>
    fetchJSON<import("./types").CollectorStatus>("/api/collector/stop", {
      method: "POST",
    }),
  getStorageInfo: () =>
    fetchJSON<import("./types").StorageInfo>("/api/collector/storage"),
  clearStorage: () =>
    fetchJSON<import("./types").StorageInfo>("/api/collector/storage", {
      method: "DELETE",
    }),
};
