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
