import { describe, expect, it } from "vitest";

import type { Job, Run } from "@/api/types";

import { axisPosition, axisScale, groupSweeps, sortRuns, varyingHparams } from "./runs";

function run(id: number, hparams: Run["hparams"], loss?: number): Run {
  return {
    id,
    name: `run-${id}`,
    state: "RUNNING",
    hparams,
    metric_stats: loss === undefined ? {} : { loss: { last: loss, min: loss, max: loss } },
  } as Run;
}

describe("varyingHparams", () => {
  it("keeps keys that differ, most varied first", () => {
    const runs = [
      run(1, { lr: 0.1, seed: 1, model: "vit", bs: 32 }),
      run(2, { lr: 0.01, seed: 2, model: "vit", bs: 32 }),
      run(3, { lr: 0.001, seed: 2, model: "vit" }),
    ];
    expect(varyingHparams(runs)).toEqual(["lr", "bs", "seed"]);
  });
});

describe("sortRuns", () => {
  const runs = [run(1, { lr: 0.1 }, 0.5), run(2, { lr: 0.01 }), run(3, { lr: 0.001 }, 0.2)];

  it("sorts numbers and puts missing values last", () => {
    const byLoss = sortRuns(runs, { kind: "metric", key: "loss" }, "asc").map((r) => r.id);
    expect(byLoss).toEqual([3, 1, 2]);
    const desc = sortRuns(runs, { kind: "metric", key: "loss" }, "desc").map((r) => r.id);
    expect(desc).toEqual([1, 3, 2]);
  });

  it("sorts names naturally", () => {
    const named = [
      { ...runs[0]!, name: "sweep-10" },
      { ...runs[1]!, name: "sweep-9" },
    ] as Run[];
    expect(sortRuns(named, { kind: "name" }, "asc").map((r) => r.name)).toEqual([
      "sweep-9",
      "sweep-10",
    ]);
  });
});

describe("axis scales", () => {
  it("uses log for values spanning orders of magnitude", () => {
    const scale = axisScale([1e-4, 1e-3, 1e-2]);
    expect(scale).toEqual({ type: "log", min: 1e-4, max: 1e-2 });
    expect(axisPosition(scale!, 1e-3)).toBeCloseTo(0.5);
  });

  it("uses linear otherwise, and categories for text", () => {
    expect(axisScale([16, 32, 64])?.type).toBe("linear");
    const category = axisScale(["sgd", "adamw", "adam"]);
    expect(category).toEqual({ type: "category", values: ["adam", "adamw", "sgd"] });
    expect(axisPosition(category!, "adamw")).toBe(0.5);
    expect(axisPosition(category!, null)).toBeNull();
    expect(axisScale([null, null])).toBeNull();
  });
});

describe("groupSweeps", () => {
  const job = (id: number, array_id: string | null, account_id = 1) =>
    ({ id, name: "lr-sweep", array_id, account_id }) as Job;

  it("groups array tasks per account and skips lone tasks", () => {
    const sweeps = groupSweeps([
      job(1, "7"),
      job(2, "7"),
      job(3, null),
      job(4, "8"),
      job(5, "7", 2),
    ]);
    expect(sweeps).toHaveLength(1);
    expect(sweeps[0]?.tasks.map((t) => t.id)).toEqual([1, 2]);
  });
});
