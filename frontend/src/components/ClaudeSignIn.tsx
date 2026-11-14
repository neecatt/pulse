import { useState } from "react";

import { api } from "@/api/client";
import type { ClaudeSetupAction } from "@/api/types";
import { Button } from "@/components/Button";
import { Card } from "@/components/Section";
import { useAssistantAction, useClaude } from "@/hooks/use-assistant";
import { useConfirm } from "@/hooks/use-confirm";

/** Run Claude Code's own `claude auth login` on the cluster and relay its link and code. */
export function ClaudeSignIn({
  account,
  verified,
  onSignedIn,
}: {
  account: number;
  verified: boolean;
  onSignedIn: () => void;
}) {
  const state = useClaude(account);
  const login = useAssistantAction(account, () => api.claude.login(account));
  const stop = useAssistantAction(account, () => api.claude.stop(account));
  const setup = useAssistantAction(
    account,
    ({ action, code }: { action: ClaudeSetupAction; code?: string }) =>
      api.claude.setup(account, action, code),
  );
  const confirm = useConfirm();
  const [code, setCode] = useState("");
  const current = state.data;
  const error = state.error ?? login.error ?? stop.error ?? setup.error;
  return (
    <Card className="space-y-3 p-4">
      <p className="text-sm">
        Claude Code isn’t signed in on this cluster. Sign in with your Claude account or set an API
        key on the cluster; Claude keeps its credentials there.
      </p>
      {current?.phase === "authorized" ? (
        <>
          <p role="status" className="text-sm">
            Claude sign-in completed.
          </p>
          <Button disabled={!verified} onClick={onSignedIn}>
            Continue
          </Button>
        </>
      ) : current?.running ? (
        <>
          {current.login_url && (
            <a
              href={current.login_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex rounded-md bg-foreground px-3 py-2 text-sm text-background"
            >
              Continue with Claude ↗
            </a>
          )}
          {current.setup_text && (
            <details>
              <summary className="cursor-pointer text-xs text-muted-foreground">
                Claude’s sign-in output
              </summary>
              <pre className="mt-2 max-h-64 overflow-auto rounded bg-muted p-3 font-mono text-xs whitespace-pre-wrap break-words">
                {current.setup_text}
              </pre>
            </details>
          )}
          {current.login_url && (
            <form
              className="flex flex-wrap items-end gap-2"
              onSubmit={(event) => {
                event.preventDefault();
                setup.mutate({ action: "code", code }, { onSuccess: () => setCode("") });
              }}
            >
              <label className="min-w-0 flex-1 space-y-1 text-xs text-muted-foreground">
                One-time code from Claude (if requested)
                <input
                  aria-label="Claude sign-in code"
                  type="password"
                  autoComplete="off"
                  value={code}
                  onChange={(event) => setCode(event.target.value)}
                  maxLength={2048}
                  className="block w-full rounded-md border bg-background px-3 py-2 text-sm"
                />
              </label>
              <Button type="submit" disabled={setup.isPending || !code.trim()}>
                Finish sign-in
              </Button>
            </form>
          )}
          {current.setup_text && (
            <div className="flex flex-wrap gap-2" aria-label="Claude sign-in controls">
              {(
                [
                  ["↑", "up"],
                  ["↓", "down"],
                  ["Enter", "enter"],
                  ["Cancel", "cancel"],
                ] as const
              ).map(([label, action]) => (
                <Button
                  key={action}
                  variant="ghost"
                  disabled={setup.isPending}
                  onClick={() => setup.mutate({ action })}
                >
                  {label}
                </Button>
              ))}
            </div>
          )}
          <Button variant="ghost" disabled={stop.isPending} onClick={() => stop.mutate()}>
            Stop sign-in
          </Button>
        </>
      ) : (
        <Button
          disabled={!verified || login.isPending}
          onClick={() =>
            confirm.ask({
              title: "Sign in to Claude on the cluster?",
              description:
                "Pulse runs Claude Code’s own login command on the cluster. Complete Claude’s authorization page, then pass its one-time code back if it asks. Pulse never sees your Claude credentials.",
              action: "Start sign-in",
              onConfirm: () => login.mutate(),
            })
          }
        >
          Sign in on cluster
        </Button>
      )}
      {current?.error && (
        <p role="alert" className="text-sm text-fail">
          {current.error}
        </p>
      )}
      {error && (
        <p role="alert" className="text-sm text-fail">
          {error instanceof Error ? error.message : "Couldn't start Claude sign-in."}
        </p>
      )}
      {confirm.dialog}
    </Card>
  );
}
