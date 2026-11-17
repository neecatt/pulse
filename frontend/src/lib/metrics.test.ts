import { describe, expect, it } from "vitest";

import {
  groupByPrefix,
  hparamList,
  metricPanels,
  sectionOf,
  shortName,
  splitMetrics,
} from "./metrics";

const point = (s: number) => ({ s, t: "2026-01-01T00:00:00Z", v: s });

describe("splitMetrics", () => {
  it("charts metrics with a history and tables single values", () => {
    const runs = [
      { metrics: { loss: [point(1), point(2)], "bench/map": [point(9)] } },
      { metrics: { "bench/map": [point(9)], acc: [point(1), point(2)] } },
    ];
    expect(splitMetrics(["loss", "acc", "bench/map"], runs)).toEqual({
      curves: ["loss", "acc"],
      values: ["bench/map"],
    });
  });
});

describe("groupByPrefix", () => {
  it("groups by the first path segment", () => {
    expect(groupByPrefix(["train/loss", "lr", "train/acc", "val/acc"])).toEqual([
      ["train", ["train/loss", "train/acc"]],
      ["metrics", ["lr"]],
      ["val", ["val/acc"]],
    ]);
  });

  it("drops the group from names inside it", () => {
    expect(shortName("train/rl/loss", "train")).toBe("rl/loss");
    expect(shortName("lr", "metrics")).toBe("lr");
  });
});

describe("metricPanels", () => {
  it("draws a metric repeated over seeds as one chart", () => {
    const panels = metricPanels([
      "train/rl/use_s0/loss",
      "train/rl/use_s1/loss",
      "train/rl/use_s0/acc",
      "train/rl/use_s1/acc",
      "train/lr",
    ]);
    expect(panels.map((p) => [p.key, p.lines.map((l) => l.label)])).toEqual([
      ["train/rl/use/loss", ["s0", "s1"]],
      ["train/rl/use/acc", ["s0", "s1"]],
      ["train/lr", [null]],
    ]);
  });

  it("drops a segment that is only a marker, and keeps lone markers in the name", () => {
    expect(metricPanels(["seed0/loss", "seed1/loss"])[0]?.key).toBe("loss");
    expect(metricPanels(["train/run3/loss"])).toEqual([
      { key: "train/run3/loss", lines: [{ name: "train/run3/loss", label: null }] },
    ]);
  });
});

describe("sectionOf", () => {
  it.each([
    ["train/rl/use/loss", "train/rl"],
    ["train/loss", "train"],
    ["loss", "metrics"],
  ])("%s -> %s", (key, section) => expect(sectionOf(key)).toBe(section));
});

describe("hparamList", () => {
  it("reads lists stored as JSON", () => {
    expect(hparamList('["imit", "rloo"]')).toEqual(["imit", "rloo"]);
    expect(hparamList("[0, 1, 2]")).toEqual(["0", "1", "2"]);
  });

  it("keeps the complete items of a list the server cut short", () => {
    const cut = `["a=${"x".repeat(100)}", "b=${"y".repeat(80)}", "c=${"z".repeat(30)}`;
    expect(hparamList(cut)).toEqual([`a=${"x".repeat(100)}`, `b=${"y".repeat(80)}`, "…"]);
  });

  it("leaves everything else alone", () => {
    expect(hparamList("results/qe")).toBeNull();
    expect(hparamList("[not json")).toBeNull();
    expect(hparamList(3)).toBeNull();
  });
});
