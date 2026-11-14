import { memo, useMemo, useRef, useState } from "react";
import { Link } from "@tanstack/react-router";
import { ChevronRight } from "lucide-react";
import { api } from "@/api/client";
import type {
  AssistantApproval,
  AssistantChoice,
  AssistantLive,
  AssistantMessage,
  AssistantModel,
  AssistantProvider,
} from "@/api/types";
import { Button } from "@/components/Button";
import { Markdown } from "@/components/Markdown";
import { Card } from "@/components/Section";
import { ASSISTANT_MAX_INPUT } from "@/config/constants";
import { useAssistantAction, useAssistantHistory, useAssistantModels } from "@/hooks/use-assistant";
import { useStickToBottom } from "@/hooks/use-stick-to-bottom";
import {
  choiceToSend,
  EFFORT_LABELS,
  loadChoice,
  mergeAssistantMessages,
  PROVIDER_NAMES,
  saveChoice,
  toolSummary,
} from "@/lib/assistant";
import { parseMarkdown } from "@/lib/markdown";
import { cn } from "@/lib/utils";

export function AssistantChat({
  account,
  provider,
  id,
  live,
  verified,
}: {
  account: number;
  provider: AssistantProvider;
  id: string;
  live: AssistantLive;
  verified: boolean;
}) {
  const name = PROVIDER_NAMES[provider];
  const history = useAssistantHistory(account, provider, id, true);
  const resume = useAssistantAction(account, () => api.assistants.resume(account, provider, id));
  const opened = live.opened.includes(id);
  const models = useAssistantModels(account, provider, opened);
  const [choice, setChoice] = useState<AssistantChoice>(() => loadChoice(provider));
  const send = useAssistantAction(account, (prompt: string) =>
    api.assistants.turn(account, provider, id, prompt, choiceToSend(choice, models.data)),
  );
  const interrupt = useAssistantAction(account, () =>
    api.assistants.interrupt(account, provider, id),
  );
  const [draft, setDraft] = useState("");
  const messages = mergeAssistantMessages(history.data?.messages ?? [], live.messages[id] ?? []);
  const working = id in live.active;
  const error = history.error ?? resume.error ?? send.error ?? interrupt.error;
  const approvals = live.approvals.filter((item) => item.thread_id === id);
  // Changes whenever something new appears, including text streaming into a message.
  const growth = `${messages.length}:${messages.reduce((n, m) => n + m.text.length, 0)}:${working}`;
  const scroller = useStickToBottom<HTMLDivElement>(growth);
  const form = useRef<HTMLFormElement>(null);
  return (
    <Card className="min-w-0">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b p-4">
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-sm font-medium">
            {history.data?.thread.title ?? "Conversation"}
          </h3>
          <p className="truncate font-mono text-xs text-muted-foreground">
            {history.data?.thread.work_dir}
          </p>
        </div>
        <Link to="/" className="text-xs underline">
          View jobs
        </Link>
        {working && (
          <Button variant="ghost" disabled={interrupt.isPending} onClick={() => interrupt.mutate()}>
            Stop turn
          </Button>
        )}
      </div>
      <div
        ref={scroller.ref}
        onScroll={scroller.onScroll}
        className="max-h-[60dvh] space-y-3 overflow-y-auto p-4"
        aria-label="Conversation"
      >
        {messages.map((item) =>
          item.role === "tool" ? (
            <ToolStep key={item.id} item={item} />
          ) : item.role === "user" ? (
            <div key={item.id} className="flex justify-end">
              <div className="max-w-[85%] rounded-2xl bg-muted px-4 py-2.5 text-sm whitespace-pre-wrap break-words [overflow-wrap:anywhere]">
                <span className="sr-only">You: </span>
                {item.text}
              </div>
            </div>
          ) : (
            <div key={item.id}>
              <span className="sr-only">{name}</span>
              <AssistantText text={item.text} />
            </div>
          ),
        )}
        {!messages.length && (
          <p className="text-sm text-muted-foreground">
            {history.isPending
              ? "Loading conversation…"
              : "Describe the training or task you want to run."}
          </p>
        )}
        {working && (
          <p role="status" className="flex items-center gap-2 text-xs text-muted-foreground">
            <span className="size-2 animate-pulse rounded-full bg-run" />
            {approvals.length
              ? "Waiting for your response"
              : `${name} is working… You can close Pulse and return here.`}
          </p>
        )}
      </div>
      <div className="space-y-3 border-t p-4">
        {approvals.map((item) => (
          <ApprovalCard key={item.id} account={account} provider={provider} approval={item} />
        ))}
        {error && (
          <p role="alert" className="text-sm text-fail">
            {error instanceof Error ? error.message : "Couldn't complete that request."}
          </p>
        )}
        {!opened ? (
          <div className="space-y-2">
            <p className="text-xs text-muted-foreground">
              Continue this cluster conversation here. {name} asks you before running commands or
              changing files, and acts as your cluster login.
            </p>
            <Button disabled={!verified || resume.isPending} onClick={() => resume.mutate()}>
              {resume.isPending ? "Opening…" : "Continue this conversation"}
            </Button>
          </div>
        ) : (
          <form
            ref={form}
            className="space-y-2"
            onSubmit={(event) => {
              event.preventDefault();
              if (draft.trim() && !working && !send.isPending)
                send.mutate(draft, {
                  onSuccess: () => {
                    setDraft("");
                    scroller.follow();
                  },
                });
            }}
          >
            <textarea
              aria-label="Prompt"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                // Enter sends and Shift+Enter adds a line, where there's a keyboard to do it.
                if (
                  event.key === "Enter" &&
                  !event.shiftKey &&
                  !event.nativeEvent.isComposing &&
                  window.matchMedia("(pointer: fine)").matches
                ) {
                  event.preventDefault();
                  form.current?.requestSubmit();
                }
              }}
              placeholder="Train this model on 4 GPUs for 12 hours…"
              rows={2}
              maxLength={ASSISTANT_MAX_INPUT}
              disabled={working}
              className="block max-h-48 w-full resize-none rounded-xl border bg-background px-3 py-2 text-sm field-sizing-content"
            />
            <div className="flex items-center gap-2">
              {models.data && (
                <ChoicePicker
                  models={models.data}
                  choice={choice}
                  disabled={working}
                  onChange={(next) => {
                    setChoice(next);
                    saveChoice(provider, next);
                  }}
                />
              )}
              <Button
                type="submit"
                className="ml-auto"
                disabled={working || send.isPending || !draft.trim()}
              >
                Send
              </Button>
            </div>
          </form>
        )}
      </div>
    </Card>
  );
}

const PICKER =
  "h-8 min-w-0 max-w-44 truncate rounded-md bg-transparent px-2 text-xs text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50";

/** Model and thinking level for the next prompt, like Claude's own picker. */
function ChoicePicker({
  models,
  choice,
  disabled,
  onChange,
}: {
  models: AssistantModel[];
  choice: AssistantChoice;
  disabled: boolean;
  onChange: (choice: AssistantChoice) => void;
}) {
  const model =
    models.find((m) => m.id === choice.model) ?? models.find((m) => m.is_default) ?? models[0];
  if (!model) return null;
  const effort = choice.effort && model.efforts.includes(choice.effort) ? choice.effort : "";
  return (
    <div className="flex min-w-0 items-center gap-1">
      <select
        aria-label="Model"
        title={model.description}
        className={PICKER}
        value={model.id}
        disabled={disabled}
        onChange={(event) => {
          const next = models.find((m) => m.id === event.target.value);
          // Keep the thinking level when the new model supports it.
          onChange({
            model: event.target.value,
            ...(effort && next?.efforts.includes(effort) ? { effort } : {}),
          });
        }}
      >
        {models.map((m) => (
          <option key={m.id} value={m.id}>
            {m.name}
          </option>
        ))}
      </select>
      {model.efforts.length > 0 && (
        <select
          aria-label="Thinking"
          className={PICKER}
          value={effort}
          disabled={disabled}
          onChange={(event) =>
            onChange({
              model: model.id,
              ...(event.target.value ? { effort: event.target.value } : {}),
            })
          }
        >
          <option value="">
            Thinking:{" "}
            {model.default_effort
              ? `default (${EFFORT_LABELS[model.default_effort] ?? model.default_effort})`
              : "default"}
          </option>
          {model.efforts.map((level) => (
            <option key={level} value={level}>
              Thinking: {EFFORT_LABELS[level] ?? level}
            </option>
          ))}
        </select>
      )}
    </div>
  );
}

/** Claude's reply, formatted. Memoized: replies re-render on every streamed word. */
const AssistantText = memo(function AssistantText({ text }: { text: string }) {
  const blocks = useMemo(() => parseMarkdown(text), [text]);
  return (
    <div className="text-sm break-words [overflow-wrap:anywhere]">
      <Markdown blocks={blocks} variant="chat" />
    </div>
  );
});

const STATUS_DOT: Record<string, string> = {
  inProgress: "animate-pulse bg-run",
  failed: "bg-fail",
  declined: "bg-fail",
};

/** A command, edit or other tool step: one line, with its output on demand. */
function ToolStep({ item }: { item: AssistantMessage }) {
  const { label, preview } = toolSummary(item);
  return (
    <details className="group text-xs">
      <summary className="flex cursor-pointer list-none items-center gap-2 py-0.5 text-muted-foreground hover:text-foreground [&::-webkit-details-marker]:hidden">
        <span
          className={cn(
            "size-1.5 shrink-0 rounded-full",
            STATUS_DOT[item.status ?? ""] ?? "bg-muted-foreground/50",
          )}
        />
        <span className="font-medium text-foreground">{label}</span>
        <span className="min-w-0 truncate font-mono">{preview}</span>
        {item.status && item.status !== "completed" && (
          <span className="shrink-0">{item.status === "inProgress" ? "running" : item.status}</span>
        )}
        <ChevronRight className="ml-auto size-3.5 shrink-0 transition-transform group-open:rotate-90" />
      </summary>
      <pre className="mt-1 max-h-64 overflow-auto rounded-md border bg-surface p-3 font-mono whitespace-pre-wrap break-words">
        {item.text}
      </pre>
    </details>
  );
}

function ApprovalCard({
  account,
  provider,
  approval,
}: {
  account: number;
  provider: AssistantProvider;
  approval: AssistantApproval;
}) {
  const [answers, setAnswers] = useState<Record<string, string[]>>({});
  const decide = useAssistantAction(account, (decision: "accept" | "decline") =>
    api.assistants.decide(account, provider, approval.id, decision, answers),
  );
  return (
    <div className="space-y-3 rounded-md border p-3">
      <h4 className="text-sm font-medium">{approval.title}</h4>
      {approval.kind === "plan" ? (
        <div className="max-h-96 overflow-auto rounded bg-muted p-3">
          <AssistantText text={approval.detail} />
        </div>
      ) : (
        approval.kind !== "question" && (
          <pre className="max-h-72 overflow-auto rounded bg-muted p-3 font-mono text-xs whitespace-pre-wrap break-words">
            {approval.detail}
          </pre>
        )
      )}
      {approval.questions.map((question) => (
        <label key={question.id} className="block space-y-2 text-sm">
          {question.question}
          {question.options?.length ? (
            <select
              aria-label={question.question}
              className="block w-full rounded-md border bg-background px-3 py-2 text-sm"
              value={answers[question.id]?.[0] ?? ""}
              onChange={(event) => setAnswers({ ...answers, [question.id]: [event.target.value] })}
            >
              <option value="" disabled>
                Choose an answer
              </option>
              {question.options.map((option) => (
                <option key={option.label} value={option.label}>
                  {option.label} — {option.description}
                </option>
              ))}
            </select>
          ) : (
            <input
              aria-label={question.question}
              maxLength={2000}
              value={answers[question.id]?.[0] ?? ""}
              onChange={(event) => setAnswers({ ...answers, [question.id]: [event.target.value] })}
              className="block w-full rounded-md border bg-background px-3 py-2"
            />
          )}
        </label>
      ))}
      <div className="flex gap-2">
        <Button
          disabled={
            decide.isPending ||
            (approval.kind === "question" && approval.questions.some((q) => !answers[q.id]?.[0]))
          }
          onClick={() => decide.mutate("accept")}
        >
          {approval.kind === "question"
            ? "Answer"
            : approval.kind === "plan"
              ? "Approve plan"
              : "Approve once"}
        </Button>
        <Button
          variant="ghost"
          disabled={decide.isPending}
          onClick={() => decide.mutate("decline")}
        >
          Decline
        </Button>
      </div>
      {decide.error && (
        <p role="alert" className="text-sm text-fail">
          {decide.error.message}
        </p>
      )}
    </div>
  );
}
