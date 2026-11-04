import type { Run } from "@/api/types";
import { formatNumber } from "@/lib/format";
import { axisPosition, axisScale, columnValue, type AxisScale, type RunColumn } from "@/lib/runs";
import { cn } from "@/lib/utils";

interface ParallelCoordinatesProps {
  runs: Run[];
  /** Hyperparameter axes, then the metric axis that colours the lines. */
  axes: RunColumn[];
  metric: string;
  /** Lower is better (losses); flips the colour scale otherwise. */
  lowerIsBetter: boolean;
  selected: number[];
  highlighted: number | null;
  onHighlight: (id: number | null) => void;
  onToggle: (id: number) => void;
}

const W = 600;
const H = 200;
const PAD_Y = 10;

/**
 * One vertical axis per hyperparameter plus the metric; each run is a line
 * across them, coloured from best (green) to worst (red) by that metric.
 */
export function ParallelCoordinates({
  runs,
  axes,
  metric,
  lowerIsBetter,
  selected,
  highlighted,
  onHighlight,
  onToggle,
}: ParallelCoordinatesProps) {
  const allAxes: RunColumn[] = [...axes, { kind: "metric", key: metric }];
  const scales = allAxes.map((axis) => axisScale(runs.map((r) => columnValue(r, axis))));
  const metricScale = scales.at(-1);
  if (allAxes.length < 2 || !metricScale) return null;

  const x = (i: number) => (i / (allAxes.length - 1)) * W;
  const y = (position: number) => H - PAD_Y - position * (H - 2 * PAD_Y);
  const lines = runs.map((run) => {
    const points = allAxes.map((axis, i) => {
      const scale = scales[i];
      const position = scale ? axisPosition(scale, columnValue(run, axis)) : null;
      return position === null ? null : `${x(i).toFixed(1)},${y(position).toFixed(1)}`;
    });
    const quality = axisPosition(metricScale, columnValue(run, { kind: "metric", key: metric }));
    const badness = quality === null ? null : lowerIsBetter ? quality : 1 - quality;
    return { run, points: points.filter((p) => p !== null).join(" "), badness };
  });

  return (
    <div className="space-y-1">
      <div className="relative h-52" onPointerLeave={() => onHighlight(null)}>
        <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="h-full w-full">
          {allAxes.map((axis, i) => (
            <line
              key={i}
              x1={x(i)}
              x2={x(i)}
              y1={PAD_Y}
              y2={H - PAD_Y}
              stroke="var(--border)"
              vectorEffect="non-scaling-stroke"
            />
          ))}
          {lines.map(({ run, points, badness }) => {
            const active = highlighted === run.id || selected.includes(run.id);
            return (
              <g key={run.id}>
                <polyline
                  points={points}
                  fill="none"
                  stroke={lineColor(badness)}
                  strokeWidth={active ? 3 : 1.5}
                  opacity={highlighted === null || active ? 0.9 : 0.25}
                  vectorEffect="non-scaling-stroke"
                />
                {/* Wide invisible line: an easy target for hover and tap. */}
                <polyline
                  points={points}
                  fill="none"
                  stroke="transparent"
                  strokeWidth={12}
                  vectorEffect="non-scaling-stroke"
                  className="cursor-pointer"
                  onPointerEnter={() => onHighlight(run.id)}
                  onClick={() => onToggle(run.id)}
                >
                  <title>{run.name}</title>
                </polyline>
              </g>
            );
          })}
        </svg>
        {allAxes.map((axis, i) => (
          <AxisLabels key={i} scale={scales[i] ?? null} left={(i / (allAxes.length - 1)) * 100} />
        ))}
      </div>
      <div className="relative h-8">
        {allAxes.map((axis, i) => (
          <span
            key={i}
            className={cn(
              "absolute top-0 max-w-24 truncate font-mono text-[10px]",
              i === allAxes.length - 1 ? "-translate-x-full text-right text-foreground" : "",
              i > 0 && i < allAxes.length - 1 && "-translate-x-1/2 text-center",
              "text-muted-foreground",
            )}
            style={{ left: `${(i / (allAxes.length - 1)) * 100}%` }}
            title={"key" in axis ? axis.key : axis.kind}
          >
            {"key" in axis ? axis.key : axis.kind}
          </span>
        ))}
      </div>
    </div>
  );
}

function AxisLabels({ scale, left }: { scale: AxisScale | null; left: number }) {
  if (!scale) return null;
  const [top, bottom] =
    scale.type === "category"
      ? [scale.values.at(-1) ?? "", scale.values[0] ?? ""]
      : [formatNumber(scale.max), formatNumber(scale.min)];
  const align = left === 0 ? "left-1" : left === 100 ? "right-1 text-right" : "";
  return (
    <>
      {[top, bottom].map((label, i) => (
        <span
          key={i}
          className={cn(
            "pointer-events-none absolute max-w-20 truncate rounded bg-background/80 px-0.5 font-mono text-[10px] text-muted-foreground",
            i === 0 ? "top-0" : "bottom-0",
            align,
          )}
          style={left > 0 && left < 100 ? { left: `calc(${left}% + 4px)` } : undefined}
        >
          {label}
        </span>
      ))}
    </>
  );
}

function lineColor(badness: number | null): string {
  if (badness === null) return "var(--muted-foreground)";
  const good = Math.round((1 - badness) * 100);
  return `color-mix(in oklch, var(--run) ${good}%, var(--fail))`;
}
