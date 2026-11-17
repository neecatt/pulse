import { ChevronRight } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";

import type { StepPoint } from "@/api/types";
import { formatNumber } from "@/lib/format";
import { RUN_COLORS } from "@/config/constants";
import {
  groupByPrefix,
  groupBySection,
  metricPanels,
  shortName,
  splitMetrics,
  type MetricPanel,
} from "@/lib/metrics";
import { updateUiSettings, useUiSettings, type UiSettings } from "@/lib/ui-settings";
import { cn } from "@/lib/utils";

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

// Below these totals every group starts open; above, only the first does.
const OPEN_CHARTS = 12;
const OPEN_VALUES = 40;
// Charts shown per section before "Show all".
const CHARTS_PER_GROUP = 12;

/**
 * Every training metric of one or more runs. Metrics with a history get a
 * chart in collapsible sections ("train/rl/…" under "train/rl") like W&B, with
 * a metric repeated over seeds drawn as one chart; metrics logged once (final
 * scores) are listed in a compact table.
 */
export function MetricsPanel({ runs, primary }: { runs: RunMetrics[]; primary?: string | null }) {
  const ui = useUiSettings();
  const [filter, setFilter] = useState("");

  const names = useMemo(() => {
    const all = new Set(runs.flatMap((r) => Object.keys(r.metrics)));
    return [...all].sort((a, b) => sortKey(a, primary) - sortKey(b, primary) || a.localeCompare(b));
  }, [runs, primary]);
  const query = filter.trim().toLowerCase();
  const shown = names.filter((n) => n.toLowerCase().includes(query));
  const { curves, values } = splitMetrics(shown, runs);
  // Comparing runs already draws a line per run, so only one run merges seeds.
  const panels =
    runs.length === 1
      ? metricPanels(curves)
      : curves.map((name) => ({ key: name, lines: [{ name, label: null }] }));
  const sections = groupBySection(panels);
  const valueGroups = groupByPrefix(values);
  const filtering = query !== "";

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
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-3 text-xs text-muted-foreground">
        {names.length > 6 && (
          <input
            type="search"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder={`Filter ${names.length} metrics`}
            className="h-8 w-full min-w-0 rounded-md border bg-background px-2.5 font-mono text-xs outline-none focus:border-ring sm:w-56"
          />
        )}
        {curves.length > 0 && (
          <>
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
          </>
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

      {shown.length === 0 && (
        <p className="text-sm text-muted-foreground">No metric matches “{filter.trim()}”.</p>
      )}

      {sections.map(([section, sectionPanels], i) => (
        <MetricGroup
          // Remount when filtering starts or stops so groups reopen to match.
          key={`${section}-${filtering}`}
          title={sections.length > 1 || valueGroups.length > 0 ? section : null}
          count={sectionPanels.length}
          defaultOpen={filtering || i === 0 || panels.length <= OPEN_CHARTS}
        >
          <ChartGrid panels={sectionPanels} section={section} runs={runs} ui={ui} />
        </MetricGroup>
      ))}

      {values.length > 0 && (
        <div className="space-y-3">
          <h3 className="text-xs tracking-wider text-muted-foreground uppercase">Final values</h3>
          {valueGroups.map(([group, metricNames], i) => (
            <MetricGroup
              key={`${group}-${filtering}`}
              title={valueGroups.length > 1 ? group : null}
              count={metricNames.length}
              defaultOpen={filtering || i === 0 || values.length <= OPEN_VALUES}
            >
              <ValueTable names={metricNames} group={group} runs={runs} />
            </MetricGroup>
          ))}
        </div>
      )}
    </div>
  );
}

/** A collapsible group of metrics; without a title it is always open. */
function MetricGroup({
  title,
  count,
  defaultOpen,
  children,
}: {
  title: string | null;
  count: number;
  defaultOpen: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  if (title === null) return <section>{children}</section>;
  return (
    <section>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-1.5 py-1 text-left text-xs text-muted-foreground hover:text-foreground"
      >
        <ChevronRight
          className={cn("size-3.5 shrink-0 transition-transform", open && "rotate-90")}
        />
        <span className="min-w-0 truncate font-mono">{title}</span>
        <span className="font-mono text-muted-foreground/70">{count}</span>
      </button>
      {open && <div className="mt-2">{children}</div>}
    </section>
  );
}

function ChartGrid({
  panels,
  section,
  runs,
  ui,
}: {
  panels: MetricPanel[];
  section: string;
  runs: RunMetrics[];
  ui: UiSettings;
}) {
  const [all, setAll] = useState(false);
  const visible = all ? panels : panels.slice(0, CHARTS_PER_GROUP);
  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {visible.map((panel) => (
          <MetricCard
            key={panel.key}
            panel={panel}
            title={shortName(panel.key, section)}
            runs={runs}
            ui={ui}
          />
        ))}
      </div>
      {panels.length > visible.length && (
        <button
          type="button"
          onClick={() => setAll(true)}
          className="h-8 w-full rounded-md border text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          Show all {panels.length} charts
        </button>
      )}
    </div>
  );
}

function MetricCard({
  panel,
  title,
  runs,
  ui,
}: {
  panel: MetricPanel;
  title: string;
  runs: RunMetrics[];
  ui: UiSettings;
}) {
  const merged = panel.lines.length > 1;
  const series: ChartSeries[] = runs.flatMap((r) =>
    panel.lines
      .filter((line) => r.metrics[line.name]?.length)
      .map((line, i) => ({
        key: `${r.id}:${line.name}`,
        label: merged ? (line.label ?? line.name) : r.label,
        color: merged ? (RUN_COLORS[i % RUN_COLORS.length] ?? r.color) : r.color,
        points: toXY(r.metrics[line.name] ?? [], ui.chartXAxis),
      })),
  );
  const only = panel.lines[0]?.name ?? "";
  const latest = runs.length === 1 && !merged ? runs[0]?.metrics[only]?.at(-1) : undefined;

  return (
    <Card className="min-w-0 p-3">
      <div className="mb-2 flex items-baseline justify-between gap-3">
        <span className="truncate font-mono text-xs" title={panel.key}>
          {title}
        </span>
        {latest && <span className="font-mono text-sm">{formatNumber(latest.v, 4)}</span>}
      </div>
      {merged && (
        <div className="mb-2 flex flex-wrap gap-x-3 gap-y-0.5 font-mono text-[11px] text-muted-foreground">
          {series.map((s) => (
            <span key={s.key} className="inline-flex items-center gap-1">
              <span className="size-1.5 rounded-full" style={{ background: s.color }} />
              {s.label}
            </span>
          ))}
        </div>
      )}
      <MetricChart
        series={series}
        xAxis={ui.chartXAxis}
        smoothing={ui.chartSmoothing}
        logScale={ui.chartLogScale}
      />
    </Card>
  );
}

/** Single-value metrics: name and value for one run, a column per run when comparing. */
function ValueTable({
  names,
  group,
  runs,
}: {
  names: string[];
  group: string;
  runs: RunMetrics[];
}) {
  const value = (run: RunMetrics, name: string) => {
    const v = run.metrics[name]?.at(-1)?.v;
    return v === undefined ? "—" : formatNumber(v, 4);
  };

  if (runs.length === 1) {
    const [run] = runs;
    return (
      <Card className="grid gap-x-6 px-3 py-1 font-mono text-xs sm:grid-cols-2 lg:grid-cols-3">
        {run &&
          names.map((name) => (
            <div
              key={name}
              className="flex items-baseline justify-between gap-3 border-b border-border/60 py-1 sm:py-1.5"
            >
              <span className="min-w-0 truncate text-muted-foreground" title={name}>
                {shortName(name, group)}
              </span>
              <span>{value(run, name)}</span>
            </div>
          ))}
      </Card>
    );
  }

  return (
    <Card className="overflow-x-auto">
      <table className="w-full font-mono text-xs">
        <thead>
          <tr className="border-b text-left text-muted-foreground">
            <th className="sticky left-0 bg-surface px-3 py-2 font-normal">metric</th>
            {runs.map((r) => (
              <th key={r.id} className="px-3 py-2 text-right font-normal whitespace-nowrap">
                <span
                  className="mr-1.5 inline-block size-2 rounded-full"
                  style={{ background: r.color }}
                />
                {r.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y">
          {names.map((name) => (
            <tr key={name}>
              <td className="sticky left-0 bg-surface px-3 py-1.5 whitespace-nowrap text-muted-foreground">
                {shortName(name, group)}
              </td>
              {runs.map((r) => (
                <td key={r.id} className="px-3 py-1.5 text-right">
                  {value(r, name)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

function toXY(points: StepPoint[], axis: UiSettings["chartXAxis"]): { x: number; y: number }[] {
  // Without step numbers (e.g. loss from plain log lines) only time works.
  const byStep = axis === "step" && points.every((p) => p.s !== null);
  const xy = points.map((p) => ({ x: byStep ? (p.s ?? 0) : Date.parse(p.t), y: p.v }));
  return xy.sort((a, b) => a.x - b.x);
}

function sortKey(name: string, primary?: string | null): number {
  if (name === primary) return 0;
  return /loss/i.test(name) ? 1 : 2;
}
