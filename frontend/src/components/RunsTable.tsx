import { Link } from "@tanstack/react-router";
import { ArrowDown, ArrowUp, Check, ChevronRight } from "lucide-react";
import { useState } from "react";

import type { HparamValue, JobState, Run } from "@/api/types";
import { formatDateTime, formatNumber } from "@/lib/format";
import { stateTone } from "@/lib/labels";
import {
  columnId,
  columnValue,
  groupRunRows,
  groupValue,
  type RunColumn,
  type SortDirection,
  type Sweep,
} from "@/lib/runs";
import { cn } from "@/lib/utils";

import { StateBadge } from "./StateBadge";

interface RunsTableProps {
  runs: Run[];
  /** Fold job arrays and batches into one expandable row each. */
  grouped: boolean;
  columns: RunColumn[];
  sort: { column: RunColumn; direction: SortDirection };
  onSort: (column: RunColumn) => void;
  selected: number[];
  onToggle: (id: number) => void;
  highlighted: number | null;
  onHighlight: (id: number | null) => void;
}

export function RunsTable({
  runs,
  grouped,
  columns,
  sort,
  onSort,
  selected,
  onToggle,
  highlighted,
  onHighlight,
}: RunsTableProps) {
  const rowProps = { columns, selected, onToggle, highlighted, onHighlight };
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs" onPointerLeave={() => onHighlight(null)}>
        <thead>
          <tr className="border-b text-left text-muted-foreground">
            <th className="w-8 px-3 py-2" aria-label="Select" />
            {columns.map((column) => {
              const active = columnId(column) === columnId(sort.column);
              const Arrow = sort.direction === "asc" ? ArrowUp : ArrowDown;
              return (
                <th key={columnId(column)} className="px-3 py-2 font-normal whitespace-nowrap">
                  <button
                    type="button"
                    onClick={() => onSort(column)}
                    className={cn(
                      "inline-flex items-center gap-1 hover:text-foreground",
                      active && "text-foreground",
                      column.kind !== "name" && "font-mono",
                    )}
                  >
                    {headerLabel(column)}
                    {active && <Arrow className="size-3" />}
                  </button>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody className="divide-y">
          {(grouped ? groupRunRows(runs) : runs.map((run) => ({ kind: "run" as const, run }))).map(
            (row) =>
              row.kind === "run" ? (
                <RunRow key={row.run.id} run={row.run} {...rowProps} />
              ) : (
                <GroupRows key={row.sweep.key} sweep={row.sweep} {...rowProps} />
              ),
          )}
        </tbody>
      </table>
    </div>
  );
}

interface RowProps {
  columns: RunColumn[];
  selected: number[];
  onToggle: (id: number) => void;
  highlighted: number | null;
  onHighlight: (id: number | null) => void;
}

/** A batch or array: one summary row, and its runs underneath when expanded. */
function GroupRows({ sweep, ...props }: RowProps & { sweep: Sweep<Run> }) {
  const [open, setOpen] = useState(false);
  const first = sweep.tasks[0];
  return (
    <>
      <tr onPointerEnter={() => props.onHighlight(null)} className="bg-muted/20">
        <td className="px-3 py-2">
          <button
            type="button"
            aria-expanded={open}
            aria-label={open ? `Collapse ${sweep.name}` : `Expand ${sweep.name}`}
            onClick={() => setOpen(!open)}
            className="grid size-4 place-items-center text-muted-foreground hover:text-foreground"
          >
            <ChevronRight className={cn("size-4 transition-transform", open && "rotate-90")} />
          </button>
        </td>
        {props.columns.map((column) => (
          <td key={columnId(column)} className="px-3 py-2 whitespace-nowrap">
            {column.kind === "name" ? (
              <button type="button" onClick={() => setOpen(!open)} className="text-left">
                <span className="font-medium">{sweep.name}</span>
                <span className="ml-1.5 font-mono text-muted-foreground">
                  {sweep.array
                    ? `[${sweep.id}] · ${sweep.tasks.length} tasks`
                    : `${sweep.tasks.length} jobs · ${formatDateTime(first?.submit_time ?? null)}`}
                </span>
              </button>
            ) : column.kind === "state" ? (
              <StateCounts runs={sweep.tasks} />
            ) : (
              <GroupCell runs={sweep.tasks} column={column} />
            )}
          </td>
        ))}
      </tr>
      {open && sweep.tasks.map((run) => <RunRow key={run.id} run={run} nested {...props} />)}
    </>
  );
}

function RunRow({
  run,
  nested = false,
  columns,
  selected,
  onToggle,
  highlighted,
  onHighlight,
}: RowProps & { run: Run; nested?: boolean }) {
  const isSelected = selected.includes(run.id);
  return (
    <tr
      onPointerEnter={() => onHighlight(run.id)}
      className={cn("transition-colors", (highlighted === run.id || isSelected) && "bg-muted/50")}
    >
      <td className="px-3 py-2">
        <button
          type="button"
          role="checkbox"
          aria-checked={isSelected}
          aria-label={`Select ${run.name}`}
          onClick={() => onToggle(run.id)}
          className={cn(
            "grid size-4 place-items-center rounded border",
            isSelected && "border-foreground bg-foreground text-background",
          )}
        >
          {isSelected && <Check className="size-3" strokeWidth={3} />}
        </button>
      </td>
      {columns.map((column) => (
        <td
          key={columnId(column)}
          className={cn("px-3 py-2 whitespace-nowrap", nested && column.kind === "name" && "pl-7")}
        >
          <Cell run={run} column={column} />
        </td>
      ))}
    </tr>
  );
}

function StateCounts({ runs }: { runs: Run[] }) {
  const counts = new Map<JobState, number>();
  for (const run of runs) counts.set(run.state, (counts.get(run.state) ?? 0) + 1);
  if (counts.size === 1) return <StateBadge state={runs[0]!.state} />;
  return (
    <span className="flex gap-2 font-mono text-[11px]">
      {[...counts].map(([state, n]) => (
        <span key={state} className={stateTone[state]}>
          {n} {state.toLowerCase()}
        </span>
      ))}
    </span>
  );
}

function GroupCell({ runs, column }: { runs: Run[]; column: RunColumn }) {
  const summary = groupValue(runs, column);
  if (summary.kind === "same") return <span className="font-mono">{format(summary.value)}</span>;
  return (
    <span className="font-mono text-muted-foreground">
      {summary.kind === "range"
        ? `${formatNumber(summary.min, 4)} – ${formatNumber(summary.max, 4)}`
        : `${summary.count} values`}
    </span>
  );
}

function Cell({ run, column }: { run: Run; column: RunColumn }) {
  if (column.kind === "name") {
    return (
      <Link
        to="/jobs/$jobId"
        params={{ jobId: String(run.id) }}
        className="font-medium hover:underline"
      >
        {run.name}
        <span className="ml-1.5 font-mono text-muted-foreground">#{run.slurm_id}</span>
      </Link>
    );
  }
  if (column.kind === "state") return <StateBadge state={run.state} />;
  return <span className="font-mono">{format(columnValue(run, column))}</span>;
}

function format(value: HparamValue): string {
  return value === null ? "—" : typeof value === "number" ? formatNumber(value, 4) : String(value);
}

function headerLabel(column: RunColumn): string {
  if (column.kind === "name") return "Run";
  if (column.kind === "state") return "State";
  return column.key;
}
