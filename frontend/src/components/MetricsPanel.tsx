import { useMemo, useState } from "react";

import type { StepPoint } from "@/api/types";
import { formatNumber } from "@/lib/format";
import { updateUiSettings, useUiSettings, type UiSettings } from "@/lib/ui-settings";

import { MetricChart, type ChartSeries } from "./MetricChart";
import { Card, EmptyState } from "./Section";
import { Segmented } from "./Segmented";
import { Toggle } from "./Toggle";

export interface RunMetrics {
  id: number;
  label: string;
  color: string;
  metrics: Record<string, StepPoint[]>;
}

/**
 * Every training metric of one or more runs, one chart per metric, grouped by
 * prefix ("train/loss" goes under "train") like TensorBoard and W&B.
 */
export function MetricsPanel({ runs, primary }: { runs: RunMetrics[]; primary?: string | null }) {
  const ui = useUiSettings();
  const [filter, setFilter] = useState("");

  const names = useMemo(() => {
    const all = new Set(runs.flatMap((r) => Object.keys(r.metrics)));
    return [...all].sort((a, b) => sortKey(a, primary) - sortKey(b, primary) || a.localeCompare(b));
  }, [runs, primary]);
  const shown = names.filter((n) => n.toLowerCase().includes(filter.trim().toLowerCase()));
  const groups = groupByPrefix(shown);

  if (names.length === 0) {
    return (
      <EmptyState title="No training metrics yet">
        Pulse reads TensorBoard event files and <code className="font-mono">metrics*.jsonl</code>/
        <code className="font-mono">.csv</code> in the job's working directory, plus{" "}
        <code className="font-mono">step=… loss=…</code> lines in its output.
      </EmptyState>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-3 text-xs text-muted-foreground">
        <label className="flex items-center gap-2">
          Smoothing
          <input
            type="range"
            min={0}
            max={0.99}
            step={0.01}
            value={ui.chartSmoothing}
            onChange={(e) => updateUiSettings({ chartSmoothing: Number(e.target.value) })}
            className="w-24 accent-[var(--run)]"
          />
          <span className="w-8 font-mono text-foreground">{ui.chartSmoothing.toFixed(2)}</span>
        </label>
        <label className="flex items-center gap-2">
          Log scale
          <Toggle
            label="Log scale"
            checked={ui.chartLogScale}
            onChange={(chartLogScale) => updateUiSettings({ chartLogScale })}
          />
        </label>
        <Segmented<UiSettings["chartXAxis"]>
          label="X axis"
          value={ui.chartXAxis}
          onChange={(chartXAxis) => updateUiSettings({ chartXAxis })}
          options={[
            { value: "step", label: "Step" },
            { value: "time", label: "Time" },
          ]}
        />
        {names.length > 6 && (
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder={`Filter ${names.length} metrics`}
            className="h-8 min-w-0 flex-1 rounded-md border bg-background px-2.5 font-mono text-xs outline-none focus:border-ring sm:max-w-56"
          />
        )}
      </div>

      {runs.length > 1 && (
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
          {runs.map((r) => (
            <span key={r.id} className="inline-flex items-center gap-1.5">
              <span className="size-2 rounded-full" style={{ background: r.color }} />
              {r.label}
            </span>
          ))}
        </div>
      )}

      {groups.map(([group, metricNames]) => (
        <section key={group} className="space-y-2">
          {groups.length > 1 && (
            <h3 className="text-xs tracking-wider text-muted-foreground uppercase">{group}</h3>
          )}
          <div className="grid gap-4 lg:grid-cols-2">
            {metricNames.map((name) => (
              <MetricCard key={name} name={name} runs={runs} ui={ui} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

function MetricCard({ name, runs, ui }: { name: string; runs: RunMetrics[]; ui: UiSettings }) {
  const series: ChartSeries[] = runs
    .filter((r) => r.metrics[name]?.length)
    .map((r) => ({
      key: String(r.id),
      label: r.label,
      color: r.color,
      points: toXY(r.metrics[name] ?? [], ui.chartXAxis),
    }));
  const latest = runs.length === 1 ? runs[0]?.metrics[name]?.at(-1) : undefined;

  return (
    <Card className="p-4">
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <span className="truncate font-mono text-xs">{name}</span>
        {latest && <span className="font-mono text-sm">{formatNumber(latest.v, 4)}</span>}
      </div>
      <MetricChart
        series={series}
        xAxis={ui.chartXAxis}
        smoothing={ui.chartSmoothing}
        logScale={ui.chartLogScale}
      />
    </Card>
  );
}

function toXY(points: StepPoint[], axis: UiSettings["chartXAxis"]): { x: number; y: number }[] {
  // Without step numbers (e.g. loss from plain log lines) only time works.
  const byStep = axis === "step" && points.every((p) => p.s !== null);
  const xy = points.map((p) => ({ x: byStep ? (p.s ?? 0) : Date.parse(p.t), y: p.v }));
  return xy.sort((a, b) => a.x - b.x);
}

function groupByPrefix(names: string[]): [string, string[]][] {
  const groups = new Map<string, string[]>();
  for (const name of names) {
    const slash = name.indexOf("/");
    const group = slash > 0 ? name.slice(0, slash) : "metrics";
    groups.set(group, [...(groups.get(group) ?? []), name]);
  }
  return [...groups];
}

function sortKey(name: string, primary?: string | null): number {
  if (name === primary) return 0;
  return /loss/i.test(name) ? 1 : 2;
}
