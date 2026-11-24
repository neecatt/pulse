import { ChevronRight } from "lucide-react";
import { Fragment, useState } from "react";

import type { HparamValue } from "@/api/types";
import { groupHparams, type HparamGroup } from "@/lib/hparams";
import { hparamList } from "@/lib/metrics";
import { cn } from "@/lib/utils";

import { Card, EmptyState } from "./Section";
import { Toggle } from "./Toggle";

// Values longer than this (paths, sentences), and lists, go under their key.
const LONG_VALUE = 32;
// Rows a group shows before "Show all"; the search box appears above this many keys.
const GROUP_ROWS = 10;

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
  const [filter, setFilter] = useState("");
  // Config order: related keys sit together, as in the file they came from.
  const keys = [...new Set(runs.flatMap((r) => Object.keys(r.hparams)))];

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
  const query = filter.trim().toLowerCase();
  const matches = (key: string) =>
    key.toLowerCase().includes(query) ||
    runs.some((r) => format(r.hparams[key]).toLowerCase().includes(query));
  const shown = keys.filter((k) => (!comparing || !onlyDiffs || differs(k)) && matches(k));
  const groups = groupHparams(shown);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-3 text-xs text-muted-foreground">
        {keys.length > GROUP_ROWS && (
          <input
            type="search"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder={`Search ${keys.length} parameters`}
            className="h-8 w-full min-w-0 rounded-md border bg-background px-2.5 font-mono text-xs outline-none focus:border-ring sm:w-56"
          />
        )}
        {comparing && (
          <label className="flex items-center gap-2">
            <Toggle label="Only differences" checked={onlyDiffs} onChange={setOnlyDiffs} />
            Only differences ({keys.filter(differs).length} of {keys.length})
          </label>
        )}
      </div>
      {comparing ? (
        <CompareTable runs={runs} groups={groups} differs={differs} />
      ) : (
        // Remount on a new search so every matching group opens in full.
        <div key={query} className="columns-1 gap-3 md:columns-2 xl:columns-3">
          {groups.map((group) => (
            <GroupCard
              key={group.name ?? ""}
              group={group}
              hparams={runs[0]?.hparams ?? {}}
              alone={groups.length === 1}
            />
          ))}
        </div>
      )}
      {shown.length === 0 && (
        <p className="text-xs text-muted-foreground">
          {query ? "No parameters match." : "All hyperparameters are identical."}
        </p>
      )}
    </div>
  );
}

/** One group of a single run's parameters: a short key/value list. */
function GroupCard({
  group,
  hparams,
  alone,
}: {
  group: HparamGroup;
  hparams: Record<string, HparamValue>;
  alone: boolean;
}) {
  const [open, setOpen] = useState(true);
  const [all, setAll] = useState(false);
  const rows = all ? group.rows : group.rows.slice(0, GROUP_ROWS);
  return (
    <Card className="mb-3 break-inside-avoid overflow-hidden font-mono text-xs">
      {!alone && (
        <button
          type="button"
          aria-expanded={open}
          onClick={() => setOpen(!open)}
          className={cn(
            "flex w-full items-center gap-1.5 px-3 py-2 text-left text-muted-foreground hover:text-foreground",
            open && "border-b",
          )}
        >
          <ChevronRight
            className={cn("size-3.5 shrink-0 transition-transform", open && "rotate-90")}
          />
          <span className="min-w-0 truncate text-foreground">{group.name ?? "general"}</span>
          <span className="text-muted-foreground/70">{group.rows.length}</span>
        </button>
      )}
      {open && (
        <dl className="divide-y">
          {rows.map(({ key, label }) => {
            const value = hparams[key];
            const long = format(value).length > LONG_VALUE || hparamList(value) !== null;
            return (
              <div
                key={key}
                className={cn(
                  "px-3 py-1.5",
                  long ? "space-y-0.5" : "flex items-baseline justify-between gap-4",
                )}
              >
                <dt className="min-w-0 text-muted-foreground wrap-anywhere" title={key}>
                  <Label text={label} />
                </dt>
                <dd className={cn("min-w-0", !long && "text-right")}>
                  <Value value={value} />
                </dd>
              </div>
            );
          })}
          {group.rows.length > rows.length && (
            <button
              type="button"
              onClick={() => setAll(true)}
              className="w-full px-3 py-1.5 text-left text-muted-foreground hover:text-foreground"
            >
              Show all {group.rows.length}
            </button>
          )}
        </dl>
      )}
    </Card>
  );
}

/** Several runs side by side, one row per parameter, under group headings. */
function CompareTable({
  runs,
  groups,
  differs,
}: {
  runs: RunHparams[];
  groups: HparamGroup[];
  differs: (key: string) => boolean;
}) {
  if (groups.length === 0) return null;
  return (
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
          {groups.map((group) => (
            <Fragment key={group.name ?? ""}>
              {group.name !== null && (
                <tr className="bg-muted/40">
                  <td colSpan={runs.length + 1} className="px-3 py-1.5 text-muted-foreground">
                    {group.name}
                  </td>
                </tr>
              )}
              {group.rows.map(({ key, label }) => (
                <tr key={key} className={cn(differs(key) && "bg-pend/5")}>
                  <td
                    className={cn(
                      "sticky left-0 max-w-48 bg-surface py-1.5 pr-3 align-top text-muted-foreground wrap-anywhere",
                      group.name === null ? "pl-3" : "pl-6",
                    )}
                    title={key}
                  >
                    <Label text={label} />
                  </td>
                  {runs.map((r) => (
                    <td key={r.id} className="min-w-36 px-3 py-1.5 align-top">
                      <Value value={r.hparams[key]} />
                    </td>
                  ))}
                </tr>
              ))}
            </Fragment>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

/** A key inside its group; deeper levels ("params.") are dimmed, the name stands out. */
function Label({ text }: { text: string }) {
  const cut = Math.max(text.lastIndexOf("."), text.lastIndexOf("/")) + 1;
  return (
    <>
      {cut > 0 && <span className="text-muted-foreground/60">{text.slice(0, cut)}</span>}
      {text.slice(cut)}
    </>
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
