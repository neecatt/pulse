import { useState } from "react";

import type { HparamValue } from "@/api/types";
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

  const differs = (key: string) =>
    new Set(runs.map((r) => JSON.stringify(r.hparams[key]))).size > 1;
  const rows = onlyDiffs ? keys.filter(differs) : keys;

  return (
    <div className="space-y-2">
      {comparing && (
        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          <Toggle label="Only differences" checked={onlyDiffs} onChange={setOnlyDiffs} />
          Only differences ({keys.filter(differs).length} of {keys.length})
        </label>
      )}
      <Card className="overflow-x-auto">
        <table className="w-full font-mono text-xs">
          {comparing && (
            <thead>
              <tr className="border-b text-left text-muted-foreground">
                <th className="px-3 py-2 font-normal">parameter</th>
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
          )}
          <tbody className="divide-y">
            {rows.map((key) => (
              <tr key={key} className={cn(comparing && differs(key) && "bg-pend/5")}>
                <td className="px-3 py-1.5 text-muted-foreground">{key}</td>
                {runs.map((r) => (
                  <td key={r.id} className="px-3 py-1.5 break-all">
                    {format(r.hparams[key])}
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

function format(value: HparamValue | undefined): string {
  if (value === undefined) return "—";
  if (value === null) return "null";
  return String(value);
}
