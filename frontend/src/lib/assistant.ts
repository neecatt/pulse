import type {
  AssistantChoice,
  AssistantLive,
  AssistantMessage,
  AssistantMode,
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

/** Permission modes, as Claude Code's own picker offers them. */
export const MODES: { id: AssistantMode; label: string; hint: string }[] = [
  { id: "ask", label: "Ask first", hint: "Asks before running commands or changing files." },
  {
    id: "edits",
    label: "Accept edits",
    hint: "Changes files without asking; asks before commands.",
  },
  {
    id: "auto",
    label: "Don't ask",
    hint: "Runs commands and changes files without asking, as your cluster login.",
  },
];

const CHOICE_KEY = "pulse.assistant-choice.";

/** The model and thinking level last picked for a provider, on this device. */
export function loadChoice(provider: AssistantProvider): AssistantChoice {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(CHOICE_KEY + provider) ?? "{}");
    if (!value || typeof value !== "object") return {};
    const { model, effort, mode } = value as Record<string, unknown>;
    const known = MODES.find((m) => m.id === mode);
    return {
      ...(typeof model === "string" ? { model } : {}),
      ...(typeof effort === "string" ? { effort } : {}),
      ...(known ? { mode: known.id } : {}),
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
 * what this cluster's CLI offers, and the chosen mode.
 */
export function choiceToSend(
  choice: AssistantChoice,
  models: AssistantModel[] | undefined,
): AssistantChoice {
  const mode = choice.mode ? { mode: choice.mode } : {};
  const model =
    models?.find((m) => m.id === choice.model) ?? models?.find((m) => m.is_default) ?? models?.[0];
  if (!model) return mode;
  const effort =
    choice.effort && model.efforts.includes(choice.effort) ? choice.effort : model.default_effort;
  return { model: model.id, ...(effort ? { effort } : {}), ...mode };
}
