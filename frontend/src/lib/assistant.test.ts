import { describe, expect, it } from "vitest";
import type { AssistantLive, AssistantMessage, AssistantModel } from "@/api/types";
import { applyAssistantLive, choiceToSend, mergeAssistantMessages, toolSummary } from "./assistant";

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

describe("tool step summaries", () => {
  const tool = (kind: string, text: string): AssistantMessage => ({
    id: "t",
    role: "tool",
    kind,
    text,
    status: "completed",
  });
  it("shows the command or file, and for other tools their main input", () => {
    expect(toolSummary(tool("commandExecution", "sbatch train.sh\n\nSubmitted 42"))).toEqual({
      label: "Command",
      preview: "sbatch train.sh",
    });
    expect(toolSummary(tool("fileChange", "/p/a.py\n- x\n+ y")).preview).toBe("/p/a.py");
    expect(
      toolSummary(tool("toolCall", 'Read\n{\n  "file_path": "/p/a.py",\n  "limit": 5\n}\n\nok')),
    ).toEqual({ label: "Read", preview: "/p/a.py" });
    expect(toolSummary(tool("toolCall", "WebFetch\n{cut"))).toEqual({
      label: "WebFetch",
      preview: "",
    });
  });
});

describe("model and thinking sent with a prompt", () => {
  const model = (id: string, efforts: string[], extra: Partial<AssistantModel> = {}) => ({
    id,
    name: id,
    description: "",
    efforts,
    default_effort: null,
    is_default: false,
    ...extra,
  });
  const models = [
    model("default", ["low", "high"], { is_default: true }),
    model("gpt", ["low", "high"], { default_effort: "low" }),
    model("haiku", []),
  ];
  it("sends what the pickers show, limited to what the CLI offers", () => {
    expect(choiceToSend({}, models)).toEqual({ model: "default" });
    expect(choiceToSend({ model: "gpt" }, models)).toEqual({ model: "gpt", effort: "low" });
    expect(choiceToSend({ model: "gpt", effort: "high" }, models)).toEqual({
      model: "gpt",
      effort: "high",
    });
    expect(choiceToSend({ model: "haiku", effort: "high" }, models)).toEqual({ model: "haiku" });
    expect(choiceToSend({ model: "gone", effort: "high" }, models)).toEqual({
      model: "default",
      effort: "high",
    });
    expect(choiceToSend({ model: "gpt" }, undefined)).toEqual({});
  });
});
