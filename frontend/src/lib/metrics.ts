import type { HparamValue, StepPoint } from "@/api/types";
import { HPARAM_MAX_VALUE_LENGTH } from "@/config/constants";

/**
 * Metrics with a history get a chart; ones every run logged once (final eval
 * scores, benchmark results) are only a number, so they go in a table.
 */
export function splitMetrics(
  names: string[],
  runs: { metrics: Record<string, StepPoint[]> }[],
): { curves: string[]; values: string[] } {
  const isCurve = (name: string) => runs.some((r) => (r.metrics[name]?.length ?? 0) > 1);
  return { curves: names.filter(isCurve), values: names.filter((n) => !isCurve(n)) };
}

/** "train/loss" goes under "train", like TensorBoard and W&B; bare names under "metrics". */
export function groupByPrefix(names: string[]): [string, string[]][] {
  const groups = new Map<string, string[]>();
  for (const name of names) {
    const slash = name.indexOf("/");
    const group = slash > 0 ? name.slice(0, slash) : "metrics";
    groups.set(group, [...(groups.get(group) ?? []), name]);
  }
  return [...groups];
}

/** A metric's name inside its group: "train/rl/loss" under "train" is "rl/loss". */
export function shortName(name: string, group: string): string {
  return name.startsWith(`${group}/`) ? name.slice(group.length + 1) : name;
}

/**
 * The items of a list hyperparameter. Config readers store lists as JSON text,
 * cut at HPARAM_MAX_VALUE_LENGTH; a cut list keeps its complete string items
 * and ends with "…". Anything else is null.
 */
export function hparamList(value: HparamValue | undefined): string[] | null {
  if (typeof value !== "string" || !value.startsWith("[")) return null;
  try {
    const items: unknown = JSON.parse(value);
    if (!Array.isArray(items)) return null;
    return items.map((item) => (typeof item === "string" ? item : JSON.stringify(item)));
  } catch {
    if (value.length < HPARAM_MAX_VALUE_LENGTH) return null;
    const complete = [...value.matchAll(/"((?:[^"\\]|\\.)*)"\s*[,\]]/g)].map((m) => m[1] ?? "");
    return complete.length ? [...complete, "…"] : null;
  }
}
