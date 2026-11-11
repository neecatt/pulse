import { describe, expect, it } from "vitest";
import type { AssistantLive, AssistantMessage } from "@/api/types";
import { applyAssistantLive, mergeAssistantMessages } from "./assistant";

const message = (id: string, text: string): AssistantMessage => ({
  id,
  text,
  role: "assistant",
  kind: "agentMessage",
  status: null,
});
describe("assistant conversation reconnects", () => {
  it("replaces the persisted copy of a live item without duplicating it", () => {
    expect(
      mergeAssistantMessages(
        [message("a", "Earlier"), message("b", "Starting")],
        [message("b", "Complete"), message("c", "Next")],
      ),
    ).toEqual([message("a", "Earlier"), message("b", "Complete"), message("c", "Next")]);
  });
  it("preserves history when there are no live messages", () => {
    expect(mergeAssistantMessages([message("a", "Saved")], [])).toEqual([message("a", "Saved")]);
  });
});

const live = (messages: AssistantLive["messages"], partial: boolean): AssistantLive => ({
  connection: { connected: true, signed_in: true, email: null },
  messages,
  active: {},
  opened: [],
  approvals: [],
  error: null,
  revision: 1,
  partial,
});
describe("assistant stream updates", () => {
  it("merges a partial update into the conversations already received", () => {
    const previous = live(
      { a: [message("1", "Hello"), message("2", "Wor")], b: [message("3", "Kept")] },
      false,
    );
    const next = applyAssistantLive(previous, live({ a: [message("2", "World")] }, true));
    expect(next.messages).toEqual({
      a: [message("1", "Hello"), message("2", "World")],
      b: [message("3", "Kept")],
    });
  });
  it("replaces everything with a full update", () => {
    const next = applyAssistantLive(live({ a: [message("1", "Old")] }, false), live({}, false));
    expect(next.messages).toEqual({});
  });
});
