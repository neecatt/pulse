import type {
  AssistantChoice,
  AssistantLive,
  AssistantMessage,
  AssistantModel,
  AssistantProvider,
} from "@/api/types";
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

export const EFFORT_LABELS: Record<string, string> = {
  none: "None",
  minimal: "Minimal",
  low: "Low",
  medium: "Medium",
  high: "High",
  xhigh: "Extra high",
  max: "Max",
};

const CHOICE_KEY = "pulse.assistant-choice.";

/** The model and thinking level last picked for a provider, on this device. */
export function loadChoice(provider: AssistantProvider): AssistantChoice {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(CHOICE_KEY + provider) ?? "{}");
    if (!value || typeof value !== "object") return {};
    const { model, effort } = value as Record<string, unknown>;
    return {
      ...(typeof model === "string" ? { model } : {}),
      ...(typeof effort === "string" ? { effort } : {}),
    };
  } catch {
    return {};
  }
}

export function saveChoice(provider: AssistantProvider, choice: AssistantChoice): void {
  try {
    localStorage.setItem(CHOICE_KEY + provider, JSON.stringify(choice));
  } catch {
    // Private mode or storage off: the choice lasts until the page closes.
  }
}

/**
 * What the pickers show, as sent with a prompt: the chosen model (or the CLI's
 * default) and the chosen thinking level (or that model's default), limited to
 * what this cluster's CLI offers.
 */
export function choiceToSend(
  choice: AssistantChoice,
  models: AssistantModel[] | undefined,
): AssistantChoice {
  const model =
    models?.find((m) => m.id === choice.model) ?? models?.find((m) => m.is_default) ?? models?.[0];
  if (!model) return {};
  const effort =
    choice.effort && model.efforts.includes(choice.effort) ? choice.effort : model.default_effort;
  return { model: model.id, ...(effort ? { effort } : {}) };
}
