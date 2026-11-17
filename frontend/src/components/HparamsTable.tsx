import { useState } from "react";

import type { HparamValue } from "@/api/types";
import { hparamList } from "@/lib/metrics";
import { cn } from "@/lib/utils";

import { Card, EmptyState } from "./Section";
import { Toggle } from "./Toggle";

export interface RunHparams {
  id: number;
  label: string;
  color: string;
  hparams: Record<string, HparamValue>;
}

/** Hyperparameters of one run, or a side-by-side diff of several. */
export function HparamsTable({ runs }: { runs: RunHparams[] }) {
  const comparing = runs.length > 1;
  const [onlyDiffs, setOnlyDiffs] = useState(comparing);
  const keys = [...new Set(runs.flatMap((r) => Object.keys(r.hparams)))].sort();

  if (keys.length === 0) {
    return (
      <EmptyState title="No hyperparameters found">
        Add an <code className="font-mono">hparams.yaml</code> or{" "}
        <code className="font-mono">config.yaml</code>/<code className="font-mono">.json</code> to
        the job's working directory.
      </EmptyState>
    );
  }

  if (!comparing) {
    const hparams = runs[0]?.hparams ?? {};
    return (
      <Card className="divide-y">
        {keys.map((key) => (
          <div
            key={key}
            className="grid grid-cols-[minmax(0,7rem)_1fr] gap-x-3 px-3 py-2 font-mono text-xs sm:grid-cols-[minmax(0,13rem)_1fr] sm:gap-x-4"
          >
            <div className="text-muted-foreground wrap-anywhere">{key}</div>
            <Value value={hparams[key]} />
          </div>
        ))}
      </Card>
    );
  }

  const differs = (key: string) =>
    new Set(runs.map((r) => JSON.stringify(r.hparams[key]))).size > 1;
  const rows = onlyDiffs ? keys.filter(differs) : keys;

  return (
    <div className="space-y-2">
      <label className="flex items-center gap-2 text-xs text-muted-foreground">
        <Toggle label="Only differences" checked={onlyDiffs} onChange={setOnlyDiffs} />
        Only differences ({keys.filter(differs).length} of {keys.length})
      </label>
      <Card className="overflow-x-auto">
        <table className="w-full font-mono text-xs">
          <thead>
            <tr className="border-b text-left text-muted-foreground">
              <th className="sticky left-0 bg-surface px-3 py-2 font-normal">parameter</th>
              {runs.map((r) => (
                <th key={r.id} className="px-3 py-2 font-normal whitespace-nowrap">
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
            {rows.map((key) => (
              <tr key={key} className={cn(differs(key) && "bg-pend/5")}>
                <td className="sticky left-0 max-w-40 bg-surface px-3 py-1.5 align-top text-muted-foreground wrap-anywhere">
                  {key}
                </td>
                {runs.map((r) => (
                  <td key={r.id} className="min-w-36 px-3 py-1.5 align-top">
                    <Value value={r.hparams[key]} />
                  </td>
                ))}
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td className="px-3 py-3 text-muted-foreground" colSpan={runs.length + 1}>
                  All hyperparameters are identical.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

/** One value; a list shows its items as chips instead of JSON. */
function Value({ value }: { value: HparamValue | undefined }) {
  const items = hparamList(value);
  if (items?.length) {
    return (
      <ul className="flex flex-wrap gap-1">
        {items.map((item, i) => (
          <li key={i} className="max-w-full rounded bg-muted px-1.5 wrap-anywhere">
            {item}
          </li>
        ))}
      </ul>
    );
  }
  return <div className="wrap-anywhere">{format(value)}</div>;
}

function format(value: HparamValue | undefined): string {
  if (value === undefined) return "—";
  if (value === null) return "null";
  return String(value);
}
