import { useState } from "react";
import { Link } from "@tanstack/react-router";

import { api } from "@/api/client";
import type { ClaudeSetupAction } from "@/api/types";
import { Button } from "@/components/Button";
import { Card } from "@/components/Section";
import { useAssistantAction, useClaude, useClaudeThreads } from "@/hooks/use-assistant";
import { useConfirm } from "@/hooks/use-confirm";

/** Use the native Claude CLI and its first-party mobile UI, without SDK auth. */
export function ClaudeConnection({ account, verified }: { account: number; verified: boolean }) {
  const state = useClaude(account);
  const threads = useClaudeThreads(account, verified);
  const login = useAssistantAction(account, () => api.claude.login(account));
  const start = useAssistantAction(account, ({ path, id }: { path: string; id?: string }) =>
    api.claude.start(account, path, id),
  );
  const stop = useAssistantAction(account, () => api.claude.stop(account));
  const setup = useAssistantAction(
    account,
    ({ action, code }: { action: ClaudeSetupAction; code?: string }) =>
      api.claude.setup(account, action, code),
  );
  const confirm = useConfirm();
  const [path, setPath] = useState("");
  const [code, setCode] = useState("");
  const current = state.data;
  const error = state.error ?? login.error ?? start.error ?? stop.error ?? setup.error;
  const open = (path: string, id?: string) =>
    confirm.ask({
      title: id ? "Continue this Claude conversation?" : "Open Claude on this cluster?",
      description: `Claude Code will run in ${path} as your cluster login. Its own browser/mobile interface handles prompts and approvals. This replaces any Claude session currently opened through Pulse on this account; submitted Slurm jobs keep running.`,
      action: "Connect Claude",
      onConfirm: () => start.mutate({ path, ...(id ? { id } : {}) }),
    });
  return (
    <div className="space-y-4">
      <Card className="space-y-3 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0 flex-1">
            <h3 className="text-sm font-medium">Claude Code</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              Connect using Claude’s official Remote Control. Prompts and approvals open in Claude;
              execution stays on this cluster.
            </p>
          </div>
          {current?.running && (
            <Button
              variant="ghost"
              disabled={stop.isPending}
              onClick={() =>
                confirm.ask({
                  title: "Disconnect Claude?",
                  description:
                    "This stops the Claude process opened through Pulse. Already submitted Slurm jobs continue, and saved conversations stay on the cluster.",
                  action: "Disconnect",
                  onConfirm: () => stop.mutate(),
                })
              }
            >
              Disconnect
            </Button>
          )}
        </div>
        {current?.phase === "ready" && current.remote_url ? (
          <>
            <a
              href={current.remote_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex rounded-md bg-foreground px-3 py-2 text-sm text-background"
            >
              Open in Claude ↗
            </a>
            <p className="text-xs text-muted-foreground">
              Sign in there with the same Claude account used on this cluster. You can close Pulse
              and keep working in Claude.
            </p>
            <Link to="/" className="inline-block text-xs underline">
              Follow submitted jobs in Pulse
            </Link>
          </>
        ) : (
          <>
            <form
              className="flex flex-wrap items-end gap-3"
              onSubmit={(event) => {
                event.preventDefault();
                open(path);
              }}
            >
              <label className="min-w-0 flex-1 space-y-1 text-xs text-muted-foreground">
                Project directory
                <input
                  aria-label="Claude project directory"
                  required
                  pattern="/.*"
                  value={path}
                  onChange={(event) => setPath(event.target.value)}
                  maxLength={4096}
                  placeholder="/scratch/you/project"
                  autoCapitalize="none"
                  autoCorrect="off"
                  spellCheck={false}
                  className="block w-full rounded-md border bg-background px-3 py-2 font-mono text-sm"
                />
              </label>
              <Button type="submit" disabled={!verified || start.isPending}>
                Connect Claude
              </Button>
            </form>
            <p className="text-xs text-muted-foreground">
              Requires Claude Code with Remote Control and an eligible Claude subscription. If it
              isn’t signed in on this cluster, use the native sign-in below.
            </p>
            <Button
              variant="ghost"
              disabled={!verified || login.isPending}
              onClick={() =>
                confirm.ask({
                  title: "Sign in to Claude on the cluster?",
                  description:
                    "Pulse launches the unmodified Claude Code login command. Complete Claude’s own authorization page, then pass its one-time code to the CLI if it asks. This replaces the current Claude connection on this account.",
                  action: "Start native sign-in",
                  onConfirm: () => login.mutate(),
                })
              }
            >
              Sign in on cluster
            </Button>
          </>
        )}
        {current?.phase === "authorized" && (
          <p role="status" className="text-sm">
            Claude sign-in completed. Choose a saved conversation below or connect a project above.
          </p>
        )}
        {current?.error && (
          <p role="alert" className="text-sm text-fail">
            {current.error}
          </p>
        )}
        {error && (
          <p role="alert" className="text-sm text-fail">
            {error instanceof Error
              ? error.message
              : "Couldn't connect Claude. Check the cluster connection."}
          </p>
        )}
      </Card>
      {current?.running && current.phase !== "ready" && (
        <Card className="space-y-3 p-4">
          <p role="status" className="text-sm">
            {current.phase === "sign_in"
              ? "Complete Claude’s native sign-in"
              : "Claude is preparing the remote session…"}
          </p>
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
            <details open>
              <summary className="cursor-pointer text-xs text-muted-foreground">
                Claude setup
              </summary>
              <pre className="mt-2 max-h-64 overflow-auto rounded bg-muted p-3 font-mono text-xs whitespace-pre-wrap break-words">
                {current.setup_text}
              </pre>
            </details>
          )}
          {current.phase === "sign_in" && current.login_url && (
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
              <Button type="submit" disabled={!verified || setup.isPending || !code.trim()}>
                Finish sign-in
              </Button>
            </form>
          )}
          {current.setup_text && (
            <div className="flex flex-wrap gap-2" aria-label="Claude setup controls">
              {(
                [
                  ["↑", "up"],
                  ["↓", "down"],
                  ["Enter", "enter"],
                  ["Yes", "yes"],
                  ["Cancel", "cancel"],
                ] as const
              ).map(([label, action]) => (
                <Button
                  key={action}
                  variant="ghost"
                  disabled={!verified || setup.isPending}
                  onClick={() => setup.mutate({ action })}
                >
                  {label}
                </Button>
              ))}
            </div>
          )}
          <p className="text-xs text-muted-foreground">
            Use these controls only to answer Claude’s setup and project-trust prompts. Remote
            Control starts after you accept its confirmation.
          </p>
        </Card>
      )}
      <div className="flex items-center justify-between">
        <h3 className="text-xs text-muted-foreground uppercase">Saved Claude conversations</h3>
        <Button
          variant="ghost"
          disabled={!verified || threads.isFetching}
          onClick={() => void threads.refetch()}
        >
          Refresh
        </Button>
      </div>
      {threads.error && (
        <p role="alert" className="text-sm text-fail">
          {threads.error.message}
        </p>
      )}
      <Card className="max-h-96 divide-y overflow-y-auto">
        {threads.data?.data.length ? (
          threads.data.data.map((thread) => (
            <div key={thread.id} className="flex flex-wrap items-center gap-3 p-4">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm">{thread.title}</p>
                <p className="truncate font-mono text-xs text-muted-foreground">
                  {thread.work_dir}
                </p>
              </div>
              <Button
                variant="ghost"
                disabled={!verified || start.isPending}
                onClick={() => open(thread.work_dir, thread.id)}
              >
                Continue in Claude
              </Button>
            </div>
          ))
        ) : (
          <p className="p-4 text-sm text-muted-foreground">
            {threads.isPending
              ? "Loading saved conversations…"
              : "No recent conversations found. Connect a project above to start one."}
          </p>
        )}
      </Card>
      {confirm.dialog}
    </div>
  );
}
