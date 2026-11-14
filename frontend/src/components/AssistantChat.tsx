import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { api } from "@/api/client";
import type {
  AssistantApproval,
  AssistantLive,
  AssistantMessage,
  AssistantProvider,
} from "@/api/types";
import { Button } from "@/components/Button";
import { Card } from "@/components/Section";
import { ASSISTANT_MAX_INPUT } from "@/config/constants";
import { useAssistantAction, useAssistantHistory } from "@/hooks/use-assistant";
import { mergeAssistantMessages, PROVIDER_NAMES } from "@/lib/assistant";

const TOOL_LABELS: Record<string, string> = {
  commandExecution: "Command",
  fileChange: "File changes",
};

/** A tool item's summary line: its kind, or for other tools the tool's name. */
function toolLabel(item: AssistantMessage): string {
  return TOOL_LABELS[item.kind] ?? item.text.split("\n", 1)[0] ?? "Tool";
}

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
  const send = useAssistantAction(account, (prompt: string) =>
    api.assistants.turn(account, provider, id, prompt),
  );
  const interrupt = useAssistantAction(account, () =>
    api.assistants.interrupt(account, provider, id),
  );
  const [draft, setDraft] = useState("");
  const messages = mergeAssistantMessages(history.data?.messages ?? [], live.messages[id] ?? []);
  const working = id in live.active;
  const error = history.error ?? resume.error ?? send.error ?? interrupt.error;
  const approvals = live.approvals.filter((item) => item.thread_id === id);
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
      <div className="max-h-[55dvh] space-y-4 overflow-y-auto p-4" aria-label="Conversation">
        {messages.map((item) =>
          item.role === "tool" ? (
            <details key={item.id} className="rounded-md border text-xs">
              <summary className="cursor-pointer px-3 py-2 text-muted-foreground">
                {toolLabel(item)}
                {item.status ? ` · ${item.status}` : ""}
              </summary>
              <pre className="max-h-64 overflow-auto border-t p-3 font-mono whitespace-pre-wrap break-words">
                {item.text}
              </pre>
            </details>
          ) : (
            <div
              key={item.id}
              className={item.role === "user" ? "ml-6 rounded-md bg-muted p-3" : "mr-3"}
            >
              <p className="mb-1 text-[11px] text-muted-foreground">
                {item.role === "user" ? "You" : name}
              </p>
              <div className="text-sm whitespace-pre-wrap break-words [overflow-wrap:anywhere]">
                {item.text}
              </div>
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
          <p role="status" className="text-xs text-muted-foreground">
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
        {!live.opened.includes(id) ? (
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
            className="flex items-end gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              if (draft.trim() && !working && !send.isPending)
                send.mutate(draft, { onSuccess: () => setDraft("") });
            }}
          >
            <textarea
              aria-label="Prompt"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="Train this model on 4 GPUs for 12 hours…"
              rows={3}
              maxLength={ASSISTANT_MAX_INPUT}
              disabled={working}
              className="min-w-0 flex-1 resize-y rounded-md border bg-background px-3 py-2 text-sm"
            />
            <Button type="submit" disabled={working || send.isPending || !draft.trim()}>
              Send
            </Button>
          </form>
        )}
      </div>
    </Card>
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
      {approval.kind !== "question" && (
        <pre className="max-h-72 overflow-auto rounded bg-muted p-3 font-mono text-xs whitespace-pre-wrap break-words">
          {approval.detail}
        </pre>
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
