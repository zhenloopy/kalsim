import { useEffect, useRef } from "react";
import {
  createChart,
  IChartApi,
  ISeriesApi,
  CrosshairMode,
  UTCTimestamp,
} from "lightweight-charts";
import { useNavHistory, RANGES } from "../../hooks/useNavHistory";
import { NavPoint } from "../../api/types";

function dedup(data: NavPoint[]): NavPoint[] {
  if (data.length === 0) return data;
  const result: NavPoint[] = [data[0]];
  for (let i = 1; i < data.length; i++) {
    if (data[i].timestamp > result[result.length - 1].timestamp) {
      result.push(data[i]);
    }
  }
  return result;
}

function computeGapThreshold(data: NavPoint[]): number {
  if (data.length < 2) return Infinity;
  const intervals: number[] = [];
  for (let i = 1; i < data.length; i++) {
    intervals.push(data[i].timestamp - data[i - 1].timestamp);
  }
  intervals.sort((a, b) => a - b);
  const median = intervals[Math.floor(intervals.length / 2)];
  const threshold = median * 5;
  return Math.max(300, Math.min(threshold, 21600));
}

export default function NavChart() {
  const { lineData, ohlcData, range, setRange, chartMode, setChartMode, loading } =
    useNavHistory();
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Line"> | ISeriesApi<"Candlestick"> | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: 300,
      layout: {
        background: { color: "#12121a" },
        textColor: "#71717a",
      },
      grid: {
        vertLines: { color: "#222230" },
        horzLines: { color: "#222230" },
      },
      crosshair: { mode: CrosshairMode.Normal },
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
        borderColor: "#222230",
      },
      rightPriceScale: {
        borderColor: "#222230",
      },
      handleScroll: true,
      handleScale: true,
    });

    chartRef.current = chart;

    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        chart.applyOptions({ width: entry.contentRect.width });
      }
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    if (seriesRef.current) {
      chart.removeSeries(seriesRef.current);
      seriesRef.current = null;
    }

    if (chartMode === "line") {
      if (lineData.length === 0) return;
      const clean = dedup(lineData);
      if (clean.length === 0) return;
      const threshold = computeGapThreshold(clean);
      const series = chart.addLineSeries({
        color: "#22d3ee",
        lineWidth: 2,
        crosshairMarkerVisible: true,
        priceLineVisible: false,
      });

      const points: { time: UTCTimestamp; value?: number }[] = [];
      for (let i = 0; i < clean.length; i++) {
        if (i > 0 && clean[i].timestamp - clean[i - 1].timestamp > threshold) {
          const midTime = clean[i - 1].timestamp + 1;
          points.push({ time: midTime as UTCTimestamp });
        }
        points.push({
          time: clean[i].timestamp as UTCTimestamp,
          value: clean[i].nav,
        });
      }

      series.setData(points as any);
      seriesRef.current = series;
    } else {
      if (ohlcData.length === 0) return;
      const series = chart.addCandlestickSeries({
        upColor: "#22c55e",
        downColor: "#ef4444",
        borderUpColor: "#22c55e",
        borderDownColor: "#ef4444",
        wickUpColor: "#22c55e",
        wickDownColor: "#ef4444",
      });

      series.setData(
        ohlcData.map((c) => ({
          time: c.timestamp as UTCTimestamp,
          open: c.open,
          high: c.high,
          low: c.low,
          close: c.close,
        }))
      );
      seriesRef.current = series;
    }

    chart.timeScale().fitContent();
  }, [lineData, ohlcData, chartMode]);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <div className="flex gap-1">
          {RANGES.map((r) => (
            <button
              key={r}
              onClick={() => setRange(r)}
              className={`px-2 py-0.5 text-xs rounded ${
                range === r
                  ? "bg-accent-cyan/20 text-accent-cyan"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              {r}
            </button>
          ))}
        </div>
        <div className="flex gap-1">
          {(["line", "candle"] as const).map((m) => (
            <button
              key={m}
              onClick={() => setChartMode(m)}
              className={`px-2 py-0.5 text-xs rounded ${
                chartMode === m
                  ? "bg-accent-cyan/20 text-accent-cyan"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              {m === "line" ? "Line" : "OHLC"}
            </button>
          ))}
        </div>
      </div>
      <div
        ref={containerRef}
        className="w-full"
        style={{ height: 300, position: "relative" }}
      >
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center z-10">
            <span className="text-xs text-zinc-500">Loading...</span>
          </div>
        )}
      </div>
    </div>
  );
}
