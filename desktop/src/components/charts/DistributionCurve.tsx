import { useMemo, useId } from "react";

interface Marker {
  value: number;
  label: string;
  color: string;
  dashed?: boolean;
}

interface DistributionCurveProps {
  data: number[];
  markers?: Marker[];
  bins?: number;
  className?: string;
}

const W = 500;
const H = 160;
const AXIS_H = 24;

function smooth(arr: number[], passes = 3, width = 5): number[] {
  let result = [...arr];
  const half = Math.floor(width / 2);
  for (let p = 0; p < passes; p++) {
    const next = [...result];
    for (let i = half; i < result.length - half; i++) {
      let sum = 0;
      for (let j = -half; j <= half; j++) sum += result[i + j];
      next[i] = sum / width;
    }
    result = next;
  }
  return result;
}

function niceTicks(min: number, max: number, target = 6): number[] {
  const range = max - min;
  if (range === 0) return [min];
  const rough = range / target;
  const pow = Math.pow(10, Math.floor(Math.log10(rough)));
  const frac = rough / pow;
  let step: number;
  if (frac <= 1.5) step = pow;
  else if (frac <= 3.5) step = 2 * pow;
  else if (frac <= 7.5) step = 5 * pow;
  else step = 10 * pow;

  const ticks: number[] = [];
  const start = Math.ceil(min / step) * step;
  for (let v = start; v <= max + step * 0.001; v += step) {
    ticks.push(Math.round(v * 1e8) / 1e8);
  }
  return ticks;
}

function catmullRom(points: [number, number][]): string {
  if (points.length < 2) return "";
  let d = `M ${points[0][0]} ${points[0][1]}`;
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[Math.max(0, i - 1)];
    const p1 = points[i];
    const p2 = points[i + 1];
    const p3 = points[Math.min(points.length - 1, i + 2)];
    d += ` C ${p1[0] + (p2[0] - p0[0]) / 6} ${p1[1] + (p2[1] - p0[1]) / 6}, ${p2[0] - (p3[0] - p1[0]) / 6} ${p2[1] - (p3[1] - p1[1]) / 6}, ${p2[0]} ${p2[1]}`;
  }
  return d;
}

export default function DistributionCurve({
  data,
  markers = [],
  bins: nBins = 80,
  className = "w-full max-w-[600px]",
}: DistributionCurveProps) {
  const safeId = useId().replace(/:/g, "");

  const computed = useMemo(() => {
    if (data.length === 0) return null;

    const sorted = [...data].sort((a, b) => a - b);
    const p1 = sorted[Math.floor(sorted.length * 0.01)];
    const p99 = sorted[Math.floor(sorted.length * 0.99)];
    const filtered = data.filter((v) => v >= p1 && v <= p99);

    const min = Math.min(...filtered);
    const max = Math.max(...filtered);
    const binW = (max - min) / nBins || 1;

    const counts = new Array(nBins).fill(0);
    for (const v of filtered) {
      counts[Math.min(Math.floor((v - min) / binW), nBins - 1)]++;
    }

    const sm = smooth(counts, 3, 5);
    const peak = Math.max(...sm);

    const xScale = (v: number) => ((v - min) / (max - min)) * W;
    const yScale = (c: number) => H * (1 - c / peak);

    const points: [number, number][] = sm.map((c, i) => [
      xScale(min + (i + 0.5) * binW),
      yScale(c),
    ]);

    const curve = catmullRom(points);
    const area =
      curve +
      ` L ${points[points.length - 1][0]} ${H} L ${points[0][0]} ${H} Z`;

    return { curve, area, ticks: niceTicks(min, max, 6), xScale, min, max };
  }, [data, nBins]);

  if (!computed) return null;

  const { curve, area, ticks, xScale, min, max } = computed;
  const zeroX = xScale(0);
  const split = min < 0 && max > 0;

  return (
    <svg viewBox={`0 0 ${W} ${H + AXIS_H}`} className={className}>
      <defs>
        <clipPath id={`${safeId}-neg`}>
          <rect x={0} y={0} width={split ? zeroX : 0} height={H + AXIS_H} />
        </clipPath>
        <clipPath id={`${safeId}-pos`}>
          <rect
            x={split ? zeroX : 0}
            y={0}
            width={split ? W - zeroX : W}
            height={H + AXIS_H}
          />
        </clipPath>
      </defs>

      {split ? (
        <>
          <path
            d={area}
            fill="#ef4444"
            opacity={0.15}
            clipPath={`url(#${safeId}-neg)`}
          />
          <path
            d={curve}
            fill="none"
            stroke="#ef4444"
            strokeWidth={1.5}
            opacity={0.8}
            clipPath={`url(#${safeId}-neg)`}
          />
          <path
            d={area}
            fill="#22c55e"
            opacity={0.15}
            clipPath={`url(#${safeId}-pos)`}
          />
          <path
            d={curve}
            fill="none"
            stroke="#22c55e"
            strokeWidth={1.5}
            opacity={0.8}
            clipPath={`url(#${safeId}-pos)`}
          />
        </>
      ) : (
        <>
          <path
            d={area}
            fill={max <= 0 ? "#ef4444" : "#22c55e"}
            opacity={0.15}
          />
          <path
            d={curve}
            fill="none"
            stroke={max <= 0 ? "#ef4444" : "#22c55e"}
            strokeWidth={1.5}
            opacity={0.8}
          />
        </>
      )}

      {split && (
        <line
          x1={zeroX}
          x2={zeroX}
          y1={0}
          y2={H}
          stroke="#71717a"
          strokeWidth={0.5}
        />
      )}

      {markers.map((m, i) => {
        const x = xScale(m.value);
        if (x < 0 || x > W) return null;
        return (
          <g key={i}>
            <line
              x1={x}
              x2={x}
              y1={0}
              y2={H}
              stroke={m.color}
              strokeWidth={1.5}
              strokeDasharray={m.dashed !== false ? "4,2" : undefined}
            />
            <text x={x + 3} y={10 + i * 12} fill={m.color} fontSize="8">
              {m.label}
            </text>
          </g>
        );
      })}

      {ticks.map((v) => {
        const x = xScale(v);
        if (x < 10 || x > W - 10) return null;
        return (
          <g key={v}>
            <line
              x1={x}
              x2={x}
              y1={H}
              y2={H + 4}
              stroke="#71717a"
              strokeWidth={0.5}
            />
            <text
              x={x}
              y={H + 15}
              fill="#71717a"
              fontSize="8"
              textAnchor="middle"
            >
              ${v.toFixed(0)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
