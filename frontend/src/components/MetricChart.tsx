import { useMemo, useState, type PointerEvent } from "react";

import { nearestIndex } from "@/lib/chart";
import { formatClock, formatNumber } from "@/lib/format";
import { smooth } from "@/lib/smoothing";
import { cn } from "@/lib/utils";

export interface ChartSeries {
  key: string;
  label: string;
  /** Any CSS colour, e.g. "var(--acc-1)". */
  color: string;
  /** Sorted by x. */
  points: { x: number; y: number }[];
}

interface MetricChartProps {
  series: ChartSeries[];
  xAxis: "step" | "time";
  smoothing?: number;
  logScale?: boolean;
  /** Fixed y range (e.g. 0..100 for percentages); defaults to the data. */
  domain?: [number, number];
  unit?: string;
  className?: string;
}

const W = 600;
const H = 180;
const PAD = 8;

interface Prepared extends ChartSeries {
  xs: number[];
  raw: number[]; // y, log10 when logScale
  shown: number[]; // smoothed
}

/**
 * Line chart for one metric across one or more runs. Smoothing draws the raw
 * line faintly behind the smoothed one, as TensorBoard does.
 */
export function MetricChart({
  series,
  xAxis,
  smoothing = 0,
  logScale = false,
  domain,
  unit = "",
  className,
}: MetricChartProps) {
  const [hover, setHover] = useState<number | null>(null); // 0..1 across the plot

  const prepared = useMemo<Prepared[]>(
    () =>
      series.map((s) => {
        const points = logScale ? s.points.filter((p) => p.y > 0) : s.points;
        const raw = points.map((p) => (logScale ? Math.log10(p.y) : p.y));
        return { ...s, xs: points.map((p) => p.x), raw, shown: smooth(raw, smoothing) };
      }),
    [series, smoothing, logScale],
  );

  const all = prepared.flatMap((s) => s.xs.map((x, i) => [x, s.raw[i] ?? 0] as const));
  if (all.length < 2) {
    return (
      <div className={cn("grid h-36 place-items-center text-xs text-muted-foreground", className)}>
        Not enough data yet
      </div>
    );
  }

  const xs = all.map(([x]) => x);
  const ys = all.map(([, y]) => y);
  const [x0, x1] = [Math.min(...xs), Math.max(...xs)];
  const [y0, y1] = domain
    ? logScale
      ? [Math.log10(Math.max(domain[0], 1e-9)), Math.log10(domain[1])]
      : domain
    : padRange(Math.min(...ys), Math.max(...ys));
  const toX = (x: number) => ((x - x0) / (x1 - x0 || 1)) * W;
  const toY = (y: number) => H - PAD - ((y - y0) / (y1 - y0 || 1)) * (H - 2 * PAD);
  const fromLog = (y: number) => (logScale ? 10 ** y : y);
  const formatX = (x: number) =>
    xAxis === "time"
      ? formatClock(new Date(x).toISOString())
      : `step ${Math.round(x).toLocaleString()}`;

  const onMove = (e: PointerEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    setHover(Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width)));
  };

  const hovered =
    hover === null
      ? []
      : prepared
          .map((s) => {
            const i = nearestIndex(s.xs, x0 + hover * (x1 - x0));
            return i === null ? null : { s, x: s.xs[i] ?? 0, y: s.shown[i] ?? 0 };
          })
          .filter((h) => h !== null);

  return (
    <div className={cn("grid grid-cols-[1fr_auto] gap-x-2 gap-y-1", className)}>
      <div
        className="relative h-36 touch-pan-y select-none"
        onPointerMove={onMove}
        onPointerDown={onMove}
        onPointerLeave={() => setHover(null)}
      >
        <svg
          viewBox={`0 0 ${W} ${H}`}
          preserveAspectRatio="none"
          className="h-full w-full"
          aria-hidden
        >
          {prepared.map((s) => (
            <g key={s.key} stroke={s.color} fill="none" strokeWidth="1.5">
              {smoothing > 0 && (
                <polyline
                  points={polyline(s.xs, s.raw, toX, toY)}
                  opacity={0.25}
                  vectorEffect="non-scaling-stroke"
                />
              )}
              <polyline
                points={polyline(s.xs, s.shown, toX, toY)}
                vectorEffect="non-scaling-stroke"
              />
            </g>
          ))}
        </svg>

        {hover !== null && hovered.length > 0 && (
          <>
            <div
              className="pointer-events-none absolute inset-y-0 w-px bg-foreground/30"
              style={{ left: `${(toX(hovered[0]?.x ?? 0) / W) * 100}%` }}
            />
            {hovered.map((h) => (
              <span
                key={h.s.key}
                className="pointer-events-none absolute size-2 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-background"
                style={{
                  left: `${(toX(h.x) / W) * 100}%`,
                  top: `${(toY(h.y) / H) * 100}%`,
                  background: h.s.color,
                }}
              />
            ))}
            <div
              className="pointer-events-none absolute top-1 z-10 min-w-28 rounded-md border bg-surface/95 px-2 py-1.5 font-mono text-[11px] shadow-sm"
              // Keep the readout beside the cursor, on whichever side has room.
              style={
                hover > 0.5
                  ? { right: `calc(${(1 - hover) * 100}% + 8px)` }
                  : { left: `calc(${hover * 100}% + 8px)` }
              }
            >
              <div className="mb-0.5 text-muted-foreground">{formatX(hovered[0]?.x ?? 0)}</div>
              {hovered.map((h) => (
                <div key={h.s.key} className="flex items-center gap-1.5 whitespace-nowrap">
                  {prepared.length > 1 && (
                    <span className="size-1.5 rounded-full" style={{ background: h.s.color }} />
                  )}
                  {prepared.length > 1 && (
                    <span className="text-muted-foreground">{h.s.label}</span>
                  )}
                  <span className="ml-auto">
                    {formatNumber(fromLog(h.y), 4)}
                    {unit}
                  </span>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
      {/* y range in a gutter beside the plot, so it never covers a line */}
      <div className="flex flex-col justify-between py-0.5 text-right font-mono text-[10px] text-muted-foreground">
        <span>
          {formatNumber(fromLog(y1))}
          {unit}
        </span>
        <span>
          {formatNumber(fromLog(y0))}
          {unit}
        </span>
      </div>
      <div className="flex justify-between font-mono text-[10px] text-muted-foreground">
        <span>{formatX(x0)}</span>
        <span>{formatX(x1)}</span>
      </div>
    </div>
  );
}

function polyline(
  xs: number[],
  ys: number[],
  toX: (x: number) => number,
  toY: (y: number) => number,
): string {
  return xs.map((x, i) => `${toX(x).toFixed(1)},${toY(ys[i] ?? 0).toFixed(1)}`).join(" ");
}

function padRange(lo: number, hi: number): [number, number] {
  const pad = (hi - lo || Math.abs(hi) || 1) * 0.05;
  // Don't invent negative values for data that never goes below zero.
  return [lo >= 0 ? Math.max(0, lo - pad) : lo - pad, hi + pad];
}
