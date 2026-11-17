import { describe, expect, it } from "vitest";

import type { EventKind, PulseEvent } from "@/api/types";

import { stackEvents } from "./events";

const event = (id: number, job_id: number, kind: EventKind, minute: number): PulseEvent => ({
  id,
  account_id: 1,
  job_id,
  kind,
  message: "",
  created_at: new Date(Date.UTC(2026, 0, 1, 12, minute)).toISOString(),
});

const names: Record<number, string> = { 1: "qe_sel", 2: "qe_sel", 3: "qe_sel", 9: "eval" };
const ids = (stacks: PulseEvent[][]) => stacks.map((s) => s.map((e) => e.id));

describe("stackEvents", () => {
  it("stacks one kind of event for same-named jobs, even when interleaved", () => {
    const events = [
      event(6, 3, "job_completed", 50),
      event(5, 3, "job_started", 40),
      event(4, 2, "job_completed", 39),
      event(3, 9, "job_completed", 38),
      event(2, 2, "job_started", 30),
      event(1, 1, "job_started", 29),
    ];
    expect(ids(stackEvents(events, (id) => names[id]))).toEqual([[6, 4], [5, 2, 1], [3]]);
  });

  it("starts a new stack after a long gap, and never stacks unknown jobs", () => {
    const events = [
      event(3, 1, "job_completed", 59),
      event(2, 2, "job_completed", 0),
      event(1, 7, "job_completed", 0),
    ];
    expect(ids(stackEvents(events, (id) => names[id]))).toEqual([[3], [2], [1]]);
  });
});
