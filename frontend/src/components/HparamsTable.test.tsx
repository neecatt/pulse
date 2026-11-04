import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { HparamsTable } from "./HparamsTable";

const run = (id: number, hparams: Record<string, string | number>) => ({
  id,
  label: `run ${id}`,
  color: "red",
  hparams,
});

describe("HparamsTable", () => {
  it("lists one run's hyperparameters", () => {
    render(<HparamsTable runs={[run(1, { lr: 0.001, batch_size: 32 })]} />);
    expect(screen.getByText("lr")).toBeInTheDocument();
    expect(screen.getByText("0.001")).toBeInTheDocument();
    expect(screen.queryByText(/Only differences/)).not.toBeInTheDocument();
  });

  it("shows only differing keys when comparing, with a toggle for all", () => {
    render(
      <HparamsTable
        runs={[
          run(1, { lr: 0.001, seed: 1, model: "vit" }),
          run(2, { lr: 0.003, seed: 1, model: "vit" }),
        ]}
      />,
    );
    expect(screen.getByText("Only differences (1 of 3)")).toBeInTheDocument();
    expect(screen.getByText("lr")).toBeInTheDocument();
    expect(screen.queryByText("seed")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("switch", { name: "Only differences" }));
    expect(screen.getByText("seed")).toBeInTheDocument();
  });

  it("explains how to add hyperparameters when there are none", () => {
    render(<HparamsTable runs={[run(1, {})]} />);
    expect(screen.getByText("No hyperparameters found")).toBeInTheDocument();
  });
});
