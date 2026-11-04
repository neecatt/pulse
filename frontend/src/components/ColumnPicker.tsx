import { Columns3 } from "lucide-react";

import { cn } from "@/lib/utils";

interface ColumnPickerProps {
  metrics: string[];
  hparams: string[];
  shownMetrics: string[];
  shownHparams: string[];
  onChange: (next: { metrics: string[]; hparams: string[] }) => void;
  onReset: () => void;
  automatic: boolean;
}

/** Choose which metric and hyperparameter columns the runs table shows. */
export function ColumnPicker({
  metrics,
  hparams,
  shownMetrics,
  shownHparams,
  onChange,
  onReset,
  automatic,
}: ColumnPickerProps) {
  const toggle = (list: string[], key: string) =>
    list.includes(key) ? list.filter((k) => k !== key) : [...list, key];

  return (
    <details className="relative">
      <summary className="inline-flex h-8 cursor-pointer list-none items-center gap-1.5 rounded-md border px-3 text-xs hover:bg-muted">
        <Columns3 className="size-3.5" /> Columns
      </summary>
      <div className="absolute right-0 z-20 mt-1 max-h-80 w-64 overflow-y-auto rounded-lg border bg-surface p-3 text-xs shadow-lg">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-muted-foreground">
            {automatic ? "Showing what differs" : "Custom columns"}
          </span>
          {!automatic && (
            <button type="button" onClick={onReset} className="underline underline-offset-2">
              Reset
            </button>
          )}
        </div>
        <Group
          title="Metrics"
          keys={metrics}
          shown={shownMetrics}
          onToggle={(key) =>
            onChange({ metrics: toggle(shownMetrics, key), hparams: shownHparams })
          }
        />
        <Group
          title="Hyperparameters"
          keys={hparams}
          shown={shownHparams}
          onToggle={(key) =>
            onChange({ metrics: shownMetrics, hparams: toggle(shownHparams, key) })
          }
        />
      </div>
    </details>
  );
}

function Group({
  title,
  keys,
  shown,
  onToggle,
}: {
  title: string;
  keys: string[];
  shown: string[];
  onToggle: (key: string) => void;
}) {
  if (keys.length === 0) return null;
  return (
    <fieldset className="mb-2">
      <legend className="mb-1 tracking-wider text-muted-foreground uppercase">{title}</legend>
      {keys.map((key) => (
        <label key={key} className="flex cursor-pointer items-center gap-2 py-0.5 font-mono">
          <input
            type="checkbox"
            checked={shown.includes(key)}
            onChange={() => onToggle(key)}
            className={cn("accent-[var(--run)]")}
          />
          <span className="truncate">{key}</span>
        </label>
      ))}
    </fieldset>
  );
}
