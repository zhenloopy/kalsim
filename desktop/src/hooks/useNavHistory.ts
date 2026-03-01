import { useState, useEffect, useCallback, useRef } from "react";
import { api } from "../api/client";
import { kalsimWS } from "../api/ws";
import { NavPoint, NavOHLC, WSMessage } from "../api/types";

type ChartMode = "line" | "candle";
type Range = "1H" | "6H" | "1D" | "1W" | "2W" | "1M" | "6M" | "1Y" | "5Y";

const RANGE_SECONDS: Record<Range, number> = {
  "1H": 3600,
  "6H": 6 * 3600,
  "1D": 86400,
  "1W": 7 * 86400,
  "2W": 14 * 86400,
  "1M": 30 * 86400,
  "6M": 180 * 86400,
  "1Y": 365 * 86400,
  "5Y": 5 * 365 * 86400,
};

const BUCKET_SIZES = [60, 300, 900, 1800, 3600, 14400, 86400, 604800];

function snapBucket(rangeSecs: number): number {
  const target = rangeSecs / 80;
  let best = BUCKET_SIZES[0];
  let bestDist = Math.abs(target - best);
  for (const b of BUCKET_SIZES) {
    const dist = Math.abs(target - b);
    if (dist < bestDist) {
      best = b;
      bestDist = dist;
    }
  }
  return best;
}

export function useNavHistory() {
  const [lineData, setLineData] = useState<NavPoint[]>([]);
  const [ohlcData, setOhlcData] = useState<NavOHLC[]>([]);
  const [range, setRange] = useState<Range>("1W");
  const [chartMode, setChartMode] = useState<ChartMode>("line");
  const [loading, setLoading] = useState(false);
  const fetchId = useRef(0);

  const fetchData = useCallback(() => {
    const id = ++fetchId.current;
    setLoading(true);

    if (chartMode === "line") {
      api
        .getNavHistory(range)
        .then((data) => {
          if (id === fetchId.current) setLineData(data);
        })
        .catch(() => {})
        .finally(() => {
          if (id === fetchId.current) setLoading(false);
        });
    } else {
      const rangeSecs = RANGE_SECONDS[range];
      const now = Date.now() / 1000;
      const bucket = snapBucket(rangeSecs);
      api
        .getNavOHLC(now - rangeSecs, now, bucket)
        .then((data) => {
          if (id === fetchId.current) setOhlcData(data);
        })
        .catch(() => {})
        .finally(() => {
          if (id === fetchId.current) setLoading(false);
        });
    }
  }, [range, chartMode]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    if (chartMode !== "line") return;

    const unsub = kalsimWS.subscribe((msg: WSMessage) => {
      if (msg.type !== "book_update") return;
      const now = Date.now() / 1000;
      const point: NavPoint = {
        timestamp: now,
        nav: msg.nav,
        cash: msg.cash,
        portfolio_value: msg.portfolio_value,
        unrealized_pnl: 0,
        position_count: msg.positions.length,
      };
      setLineData((prev) => {
        const lastTs = prev.length > 0 ? prev[prev.length - 1].timestamp : 0;
        if (now <= lastTs) return prev;
        return [...prev, point];
      });
    });
    return unsub;
  }, [chartMode]);

  return {
    lineData,
    ohlcData,
    range,
    setRange: setRange as (r: string) => void,
    chartMode,
    setChartMode: setChartMode as (m: string) => void,
    loading,
  };
}

export const RANGES: Range[] = [
  "1H",
  "6H",
  "1D",
  "1W",
  "2W",
  "1M",
  "6M",
  "1Y",
  "5Y",
];
