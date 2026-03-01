import { useMemo } from "react";

interface PnlDistributionProps {
  data: number[];
  var95?: number;
  var99?: number;
}

export default function PnlDistribution({
  data,
  var95,
  var99,
}: PnlDistributionProps) {
  const histogram = useMemo(() => {
    if (data.length === 0) return { bins: [], counts: [], min: 0, max: 0 };

    const sorted = [...data].sort((a, b) => a - b);
    const p1 = sorted[Math.floor(sorted.length * 0.01)];
    const p99 = sorted[Math.floor(sorted.length * 0.99)];
    const filtered = data.filter((v) => v >= p1 && v <= p99);

    const min = Math.min(...filtered);
    const max = Math.max(...filtered);
    const nBins = 60;
    const binWidth = (max - min) / nBins || 1;

    const counts = new Array(nBins).fill(0);
    const bins = Array.from({ length: nBins }, (_, i) => min + i * binWidth);

    for (const v of filtered) {
      const idx = Math.min(Math.floor((v - min) / binWidth), nBins - 1);
      counts[idx]++;
    }

    return { bins, counts, min, max };
  }, [data]);

  if (data.length === 0) return null;

  const maxCount = Math.max(...histogram.counts);
  const chartHeight = 160;
  const chartWidth = 500;
  const barWidth = chartWidth / histogram.bins.length;

  const xScale = (v: number) =>
    ((v - histogram.min) / (histogram.max - histogram.min)) * chartWidth;

  return (
    <div className="mt-4">
      <h2 className="text-xs font-semibold text-accent-cyan mb-2">
        P&L DISTRIBUTION
      </h2>
      <svg
        viewBox={`0 0 ${chartWidth} ${chartHeight + 20}`}
        className="w-full max-w-[600px]"
        style={{ minHeight: 80 }}
      >
        {histogram.bins.map((bin, i) => {
          const h = (histogram.counts[i] / maxCount) * chartHeight;
          const x = i * barWidth;
          const isLoss = bin < 0;
          return (
            <rect
              key={i}
              x={x}
              y={chartHeight - h}
              width={Math.max(barWidth - 1, 1)}
              height={h}
              fill={isLoss ? "#ef4444" : "#22c55e"}
              opacity={0.6}
            />
          );
        })}

        {var95 !== undefined && (
          <line
            x1={xScale(-var95)}
            x2={xScale(-var95)}
            y1={0}
            y2={chartHeight}
            stroke="#eab308"
            strokeWidth={1.5}
            strokeDasharray="4,2"
          />
        )}
        {var99 !== undefined && (
          <line
            x1={xScale(-var99)}
            x2={xScale(-var99)}
            y1={0}
            y2={chartHeight}
            stroke="#ef4444"
            strokeWidth={1.5}
            strokeDasharray="4,2"
          />
        )}

        <line
          x1={xScale(0)}
          x2={xScale(0)}
          y1={0}
          y2={chartHeight}
          stroke="#71717a"
          strokeWidth={0.5}
        />

        <text x={2} y={chartHeight + 14} fill="#71717a" fontSize="8">
          ${histogram.min.toFixed(0)}
        </text>
        <text
          x={chartWidth - 2}
          y={chartHeight + 14}
          fill="#71717a"
          fontSize="8"
          textAnchor="end"
        >
          ${histogram.max.toFixed(0)}
        </text>
        {var95 !== undefined && (
          <text
            x={xScale(-var95) + 2}
            y={10}
            fill="#eab308"
            fontSize="8"
          >
            VaR95
          </text>
        )}
        {var99 !== undefined && (
          <text
            x={xScale(-var99) + 2}
            y={20}
            fill="#ef4444"
            fontSize="8"
          >
            VaR99
          </text>
        )}
      </svg>
    </div>
  );
}
