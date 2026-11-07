import { describe, expect, it } from "vitest";
import type { AssistantMessage } from "@/api/types";
import { mergeAssistantMessages } from "./assistant";

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
