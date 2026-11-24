import { describe, expect, it } from "vitest";

import { groupHparams } from "./hparams";

describe("groupHparams", () => {
  it("groups by the first segment and keeps config order", () => {
    const groups = groupHparams([
      "seed",
      "trainer.precision",
      "model.params.lr",
      "trainer.max_epochs",
      "optim/lr",
      "model.target",
    ]);
    expect(groups).toEqual([
      {
        name: null,
        rows: [
          { key: "seed", label: "seed" },
          { key: "optim/lr", label: "optim/lr" },
        ],
      },
      {
        name: "trainer",
        rows: [
          { key: "trainer.precision", label: "precision" },
          { key: "trainer.max_epochs", label: "max_epochs" },
        ],
      },
      {
        name: "model",
        rows: [
          { key: "model.params.lr", label: "params.lr" },
          { key: "model.target", label: "target" },
        ],
      },
    ]);
  });

  it("looks past a key that wraps the whole config", () => {
    const groups = groupHparams(["config.seed", "config.model.depth", "config.model.width"]);
    expect(groups).toEqual([
      { name: null, rows: [{ key: "config.seed", label: "seed" }] },
      {
        name: "model",
        rows: [
          { key: "config.model.depth", label: "depth" },
          { key: "config.model.width", label: "width" },
        ],
      },
    ]);
  });

  it("leaves flat configs in one group", () => {
    expect(groupHparams(["lr", "batch_size"])).toEqual([
      {
        name: null,
        rows: [
          { key: "lr", label: "lr" },
          { key: "batch_size", label: "batch_size" },
        ],
      },
    ]);
  });
});
