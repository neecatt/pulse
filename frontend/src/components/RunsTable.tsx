import { Link } from "@tanstack/react-router";
import { ArrowDown, ArrowUp, Check } from "lucide-react";

import type { Run } from "@/api/types";
import { formatNumber } from "@/lib/format";
import { columnId, columnValue, type RunColumn, type SortDirection } from "@/lib/runs";
import { cn } from "@/lib/utils";

import { StateBadge } from "./StateBadge";

interface RunsTableProps {
  runs: Run[];
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
  columns,
  sort,
  onSort,
  selected,
  onToggle,
  highlighted,
  onHighlight,
}: RunsTableProps) {
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
          {runs.map((run) => {
            const isSelected = selected.includes(run.id);
            return (
              <tr
                key={run.id}
                onPointerEnter={() => onHighlight(run.id)}
                className={cn(
                  "transition-colors",
                  (highlighted === run.id || isSelected) && "bg-muted/50",
                )}
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
                  <td key={columnId(column)} className="px-3 py-2 whitespace-nowrap">
                    <Cell run={run} column={column} />
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
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
  const value = columnValue(run, column);
  return (
    <span className="font-mono">
      {value === null ? "—" : typeof value === "number" ? formatNumber(value, 4) : String(value)}
    </span>
  );
}

function headerLabel(column: RunColumn): string {
  if (column.kind === "name") return "Run";
  if (column.kind === "state") return "State";
  return column.key;
}
