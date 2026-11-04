import type { MetricPoint } from "@/api/types";
import { formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

interface LineChartProps {
  points: MetricPoint[];
  /** Fixed y-range (e.g. 0..100 for percentages); defaults to the data's range. */
  domain?: [number, number];
  unit?: string;
  className?: string;
}

const W = 600;
const H = 160;
const PAD_Y = 8;

/** Minimal time-series chart: line, soft fill, min/max labels. */
export function LineChart({ points, domain, unit = "", className }: LineChartProps) {
  if (points.length < 2) {
    return (
      <div className={cn("grid h-40 place-items-center text-xs text-muted-foreground", className)}>
        Not enough data yet
      </div>
    );
  }
  const times = points.map((p) => new Date(p.t).getTime());
  const values = points.map((p) => p.v);
  const [lo, hi] = domain ?? [Math.min(...values), Math.max(...values)];
  const t0 = times[0] ?? 0;
  const tSpan = (times.at(-1) ?? t0) - t0 || 1;
  const vSpan = hi - lo || 1;

  const xy = points.map((p, i) => {
    const x = (((times[i] ?? t0) - t0) / tSpan) * W;
    const y = H - PAD_Y - ((p.v - lo) / vSpan) * (H - 2 * PAD_Y);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const line = xy.join(" ");
  const area = `0,${H} ${line} ${W},${H}`;

  return (
    <div className={cn("relative", className)}>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="h-40 w-full" aria-hidden>
        <polygon points={area} fill="currentColor" opacity={0.08} />
        <polyline
          points={line}
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          vectorEffect="non-scaling-stroke"
        />
      </svg>
      <span className="absolute top-0 right-0 font-mono text-[10px] text-muted-foreground">
        {formatNumber(hi)}
        {unit}
      </span>
      <span className="absolute right-0 bottom-0 font-mono text-[10px] text-muted-foreground">
        {formatNumber(lo)}
        {unit}
      </span>
    </div>
  );
}
