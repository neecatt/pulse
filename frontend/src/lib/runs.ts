import type { HparamValue, Job, Run } from "@/api/types";

/** A column of the runs table (and an axis of the parallel-coordinates chart). */
export type RunColumn =
  | { kind: "name" }
  | { kind: "state" }
  | { kind: "metric"; key: string }
  | { kind: "hparam"; key: string };

export type SortDirection = "asc" | "desc";

export function columnId(column: RunColumn): string {
  return "key" in column ? `${column.kind}:${column.key}` : column.kind;
}

export function columnValue(run: Run, column: RunColumn): HparamValue {
  switch (column.kind) {
    case "name":
      return run.name;
    case "state":
      return run.state;
    case "metric":
      return run.metric_stats[column.key]?.last ?? null;
    case "hparam":
      return run.hparams[column.key] ?? null;
  }
}

/** Sorted copy; missing values always go last. */
export function sortRuns(runs: Run[], column: RunColumn, direction: SortDirection): Run[] {
  const sign = direction === "asc" ? 1 : -1;
  return [...runs].sort((a, b) => {
    const x = columnValue(a, column);
    const y = columnValue(b, column);
    if (x === null || y === null) return x === y ? 0 : x === null ? 1 : -1;
    if (typeof x === "number" && typeof y === "number") return sign * (x - y);
    return sign * String(x).localeCompare(String(y), undefined, { numeric: true });
  });
}

/** Hyperparameters whose values differ between runs, most-varied first. */
export function varyingHparams(runs: Run[]): string[] {
  const keys = new Set(runs.flatMap((r) => Object.keys(r.hparams)));
  return [...keys]
    .map((key) => ({
      key,
      distinct: new Set(runs.map((r) => JSON.stringify(r.hparams[key]))).size,
    }))
    .filter(({ distinct }) => distinct > 1)
    .sort((a, b) => b.distinct - a.distinct || a.key.localeCompare(b.key))
    .map(({ key }) => key);
}

export interface Sweep {
  arrayId: string;
  name: string;
  tasks: Job[];
}

/** Job arrays with at least two tasks, in first-seen order. */
export function groupSweeps(jobs: Job[]): Sweep[] {
  const sweeps = new Map<string, Sweep>();
  for (const job of jobs) {
    if (!job.array_id) continue;
    const key = `${job.account_id}:${job.array_id}`;
    const sweep = sweeps.get(key) ?? { arrayId: job.array_id, name: job.name, tasks: [] };
    sweep.tasks.push(job);
    sweeps.set(key, sweep);
  }
  return [...sweeps.values()].filter((s) => s.tasks.length > 1);
}

export type AxisScale =
  | { type: "linear"; min: number; max: number }
  | { type: "log"; min: number; max: number }
  | { type: "category"; values: string[] };

/**
 * Pick a scale for an axis: log for positive numbers spanning 100x or more
 * (learning rates, weight decay), linear for other numbers, categories for text.
 */
export function axisScale(values: HparamValue[]): AxisScale | null {
  const present = values.filter((v): v is Exclude<HparamValue, null> => v !== null);
  if (present.length === 0) return null;
  if (present.every((v) => typeof v === "number")) {
    const numbers = present as number[];
    const min = Math.min(...numbers);
    const max = Math.max(...numbers);
    return min > 0 && max / min >= 100 ? { type: "log", min, max } : { type: "linear", min, max };
  }
  const values_ = [...new Set(present.map(String))].sort((a, b) =>
    a.localeCompare(b, undefined, { numeric: true }),
  );
  return { type: "category", values: values_ };
}

/** Position of a value on an axis, 0 (bottom) to 1 (top); null if missing. */
export function axisPosition(scale: AxisScale, value: HparamValue): number | null {
  if (value === null) return null;
  if (scale.type === "category") {
    const i = scale.values.indexOf(String(value));
    return scale.values.length > 1 ? i / (scale.values.length - 1) : 0.5;
  }
  if (typeof value !== "number") return null;
  if (scale.max === scale.min) return 0.5;
  if (scale.type === "log") {
    return Math.log(value / scale.min) / Math.log(scale.max / scale.min);
  }
  return (value - scale.min) / (scale.max - scale.min);
}
