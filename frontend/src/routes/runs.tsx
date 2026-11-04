import { createFileRoute, Link } from "@tanstack/react-router";
import { useMemo, useState } from "react";

import { useJobs, useRuns } from "@/api/queries";
import type { Run } from "@/api/types";
import { ColumnPicker } from "@/components/ColumnPicker";
import { ParallelCoordinates } from "@/components/ParallelCoordinates";
import { RunsTable } from "@/components/RunsTable";
import { Card, EmptyState, ErrorNotice, LoadingRows, Section } from "@/components/Section";
import { Toggle } from "@/components/Toggle";
import { MAX_AUTO_HPARAM_COLUMNS, MAX_COMPARE } from "@/config/constants";
import {
  groupSweeps,
  sortRuns,
  varyingHparams,
  type RunColumn,
  type SortDirection,
} from "@/lib/runs";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/runs")({
  // Array ids are numeric; a number keeps the URL clean (?sweep=123, not ?sweep=%22123%22).
  validateSearch: (search: Record<string, unknown>): { sweep?: number } => {
    const sweep = Number(search["sweep"]);
    return Number.isInteger(sweep) && sweep > 0 ? { sweep } : {};
  },
  head: () => ({ meta: [{ title: "Runs — Pulse" }] }),
  component: RunsPage,
});

interface CustomColumns {
  metrics: string[];
  hparams: string[];
}

function RunsPage() {
  const { sweep: sweepId } = Route.useSearch();
  const sweep = sweepId === undefined ? undefined : String(sweepId);
  const { data: runs = [], error, isPending } = useRuns(sweep);
  const { data: jobs = [] } = useJobs();
  const sweeps = groupSweeps(jobs);

  const [withMetrics, setWithMetrics] = useState(true);
  const [custom, setCustom] = useState<CustomColumns | null>(null);
  const [sort, setSort] = useState<{ column: RunColumn; direction: SortDirection } | null>(null);
  const [selected, setSelected] = useState<number[]>([]);
  const [highlighted, setHighlighted] = useState<number | null>(null);

  const visible = useMemo(
    () => runs.filter((r) => !withMetrics || Object.keys(r.metric_stats).length > 0),
    [runs, withMetrics],
  );
  const primary = mostCommonPrimary(visible);
  const allMetrics = [...new Set(visible.flatMap((r) => Object.keys(r.metric_stats)))].sort();
  const allHparams = [...new Set(visible.flatMap((r) => Object.keys(r.hparams)))].sort();
  const autoMetrics = [primary, allMetrics.find((m) => m.startsWith("val") && m.includes("loss"))]
    .filter((m): m is string => Boolean(m))
    .filter((m, i, list) => list.indexOf(m) === i);
  const shownMetrics = custom?.metrics ?? autoMetrics;
  const shownHparams = custom?.hparams ?? varyingHparams(visible).slice(0, MAX_AUTO_HPARAM_COLUMNS);

  const columns: RunColumn[] = [
    { kind: "name" },
    { kind: "state" },
    ...shownMetrics.map((key): RunColumn => ({ kind: "metric", key })),
    ...shownHparams.map((key): RunColumn => ({ kind: "hparam", key })),
  ];
  const lowerIsBetter = !primary || /loss|err/i.test(primary);
  const activeSort =
    sort ??
    (primary
      ? {
          column: { kind: "metric", key: primary } as RunColumn,
          direction: lowerIsBetter ? "asc" : "desc",
        }
      : { column: { kind: "name" } as RunColumn, direction: "asc" as SortDirection });
  const sorted = sortRuns(visible, activeSort.column, activeSort.direction);

  const onSort = (column: RunColumn) =>
    setSort((current) => ({
      column,
      direction:
        current &&
        JSON.stringify(current.column) === JSON.stringify(column) &&
        current.direction === "asc"
          ? "desc"
          : "asc",
    }));
  const toggle = (id: number) =>
    setSelected((ids) =>
      ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id].slice(-MAX_COMPARE),
    );

  return (
    <div className="space-y-6">
      <header className="space-y-3">
        <h1 className="text-2xl font-medium tracking-tight">Runs</h1>
        <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:px-0">
          <SweepChip active={!sweep} search={{}}>
            All runs
          </SweepChip>
          {sweeps.map((s) => (
            <SweepChip
              key={`${s.tasks[0]?.account_id}-${s.arrayId}`}
              active={sweep === s.arrayId}
              search={{ sweep: Number(s.arrayId) }}
            >
              {s.name} <span className="font-mono opacity-70">[{s.arrayId}]</span>
              <span className="opacity-70">· {s.tasks.length}</span>
            </SweepChip>
          ))}
        </div>
      </header>

      {error && <ErrorNotice error={error} />}
      {isPending ? (
        <LoadingRows rows={4} />
      ) : visible.length === 0 ? (
        <EmptyState title="No runs with metrics yet">
          Runs appear here once Pulse finds training metrics in a job's output or working directory.
        </EmptyState>
      ) : (
        <>
          {primary && shownHparams.length > 0 && visible.length > 1 && (
            <Section title={`How hyperparameters relate to ${primary}`}>
              <Card className="p-4">
                <ParallelCoordinates
                  runs={sorted}
                  axes={shownHparams.map((key) => ({ kind: "hparam", key }))}
                  metric={primary}
                  lowerIsBetter={lowerIsBetter}
                  selected={selected}
                  highlighted={highlighted}
                  onHighlight={setHighlighted}
                  onToggle={toggle}
                />
              </Card>
            </Section>
          )}

          <div className="flex flex-wrap items-center justify-between gap-3">
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              <Toggle
                label="Only runs with metrics"
                checked={withMetrics}
                onChange={setWithMetrics}
              />
              Only runs with metrics
            </label>
            <div className="flex items-center gap-2">
              {selected.length >= 2 && (
                <Link
                  to="/compare"
                  search={{ ids: selected.join(",") }}
                  className="inline-flex h-8 items-center rounded-md bg-foreground px-3 text-xs font-medium text-background"
                >
                  Compare {selected.length} →
                </Link>
              )}
              <ColumnPicker
                metrics={allMetrics}
                hparams={allHparams}
                shownMetrics={shownMetrics}
                shownHparams={shownHparams}
                onChange={setCustom}
                onReset={() => setCustom(null)}
                automatic={custom === null}
              />
            </div>
          </div>

          <Card>
            <RunsTable
              runs={sorted}
              columns={columns}
              sort={activeSort}
              onSort={onSort}
              selected={selected}
              onToggle={toggle}
              highlighted={highlighted}
              onHighlight={setHighlighted}
            />
          </Card>
        </>
      )}
    </div>
  );
}

function SweepChip({
  active,
  search,
  children,
}: {
  active: boolean;
  search: { sweep?: number };
  children: React.ReactNode;
}) {
  return (
    <Link
      to="/runs"
      search={search}
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1 text-xs transition-colors",
        active ? "bg-foreground text-background" : "text-muted-foreground hover:text-foreground",
      )}
    >
      {children}
    </Link>
  );
}

/** The metric most runs report as primary, for the default sort and chart. */
function mostCommonPrimary(runs: Run[]): string | null {
  const counts = new Map<string, number>();
  for (const run of runs) {
    if (run.primary_metric)
      counts.set(run.primary_metric, (counts.get(run.primary_metric) ?? 0) + 1);
  }
  return [...counts].sort((a, b) => b[1] - a[1])[0]?.[0] ?? null;
}
