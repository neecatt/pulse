import type { AssistantLive, AssistantMessage, AssistantProvider } from "@/api/types";
import { ASSISTANT_MAX_ITEMS } from "@/config/constants";

export const PROVIDER_NAMES: Record<AssistantProvider, string> = {
  codex: "Codex",
  claude: "Claude",
};

export function mergeAssistantMessages(
  history: AssistantMessage[],
  live: AssistantMessage[],
): AssistantMessage[] {
  const items = new Map(history.map((item) => [item.id, item]));
  for (const item of live) items.set(item.id, item);
  return [...items.values()];
}

/** Apply a stream update; partial ones only carry the messages that changed. */
export function applyAssistantLive(
  previous: AssistantLive | undefined,
  live: AssistantLive,
): AssistantLive {
  if (!live.partial || !previous) return live;
  const messages = { ...previous.messages };
  for (const [id, items] of Object.entries(live.messages)) {
    messages[id] = mergeAssistantMessages(messages[id] ?? [], items).slice(-ASSISTANT_MAX_ITEMS);
  }
  return { ...live, messages };
}

/** A tool step's one-line summary: what kind of step, and its command, file or input. */
export function toolSummary(item: AssistantMessage): { label: string; preview: string } {
  const [first = "", ...rest] = item.text.split("\n");
  if (item.kind === "commandExecution") return { label: "Command", preview: first };
  if (item.kind === "fileChange") return { label: "Edit", preview: first };
  // Other tools arrive as their name, then their input as JSON, then any output.
  let preview = "";
  try {
    const input: unknown = JSON.parse(rest.join("\n").split("\n\n")[0] ?? "");
    if (input && typeof input === "object") {
      const value = Object.values(input).find((v) => typeof v === "string");
      preview = typeof value === "string" ? (value.split("\n")[0] ?? "") : "";
    }
  } catch {
    // Cut off or not JSON: the name alone is enough.
  }
  return { label: first || "Tool", preview };
}
