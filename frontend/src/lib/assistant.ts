import type { AssistantMessage } from "@/api/types";

export function mergeAssistantMessages(
  history: AssistantMessage[],
  live: AssistantMessage[],
): AssistantMessage[] {
  const items = new Map(history.map((item) => [item.id, item]));
  for (const item of live) items.set(item.id, item);
  return [...items.values()];
}
