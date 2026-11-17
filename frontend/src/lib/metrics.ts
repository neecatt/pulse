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

// A path segment ending in a repeat marker: "use_loo_s0", "seed1", "rank-3".
const REPEAT = /(^|[_-])((?:s|seed|rank|fold|run|trial|rep)\d+)$/i;

/** One chart: a metric, or the same metric over seeds/ranks drawn as one line each. */
export interface MetricPanel {
  key: string;
  /** The metrics drawn, with the label of their line ("s0"); one metric has no label. */
  lines: { name: string; label: string | null }[];
}

/**
 * Charts for the given metrics, in order. Metrics that differ only by a seed
 * or rank marker ("rl/use_s0/loss", "rl/use_s1/loss") share one chart, like
 * W&B's grouped runs; everything else gets its own.
 */
export function metricPanels(names: string[]): MetricPanel[] {
  const panels = new Map<string, MetricPanel>();
  for (const name of names) {
    const segments = name.split("/");
    let label: string | null = null;
    for (let i = segments.length - 1; i >= 0 && label === null; i--) {
      const match = segments[i]?.match(REPEAT);
      if (match) {
        label = match[2] ?? null;
        segments[i] = segments[i]!.replace(REPEAT, "");
      }
    }
    const key = segments.filter(Boolean).join("/");
    const panel = panels.get(key) ?? { key, lines: [] };
    panel.lines.push({ name, label });
    panels.set(key, panel);
  }
  // A marker with no siblings is part of the name, not a repeat.
  return [...panels.values()].flatMap((p) =>
    p.lines.length > 1
      ? [p]
      : p.lines.map((l) => ({ key: l.name, lines: [{ ...l, label: null }] })),
  );
}

/**
 * The section a chart goes in: its first two path segments when it has three or
 * more ("train/rl/use/loss" under "train/rl"), else its first ("train/loss").
 */
export function sectionOf(key: string): string {
  const segments = key.split("/");
  if (segments.length >= 3) return segments.slice(0, 2).join("/");
  return segments.length === 2 ? (segments[0] ?? key) : "metrics";
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

/** Charts by section (see sectionOf), in first-seen order. */
export function groupBySection(panels: MetricPanel[]): [string, MetricPanel[]][] {
  const sections = new Map<string, MetricPanel[]>();
  for (const panel of panels) {
    const section = sectionOf(panel.key);
    sections.set(section, [...(sections.get(section) ?? []), panel]);
  }
  return [...sections];
}
