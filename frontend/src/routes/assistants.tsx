import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { api } from "@/api/client";
import { useAccounts, useAssistantAccess, useAssistantAudit } from "@/api/queries";
import { AssistantChat } from "@/components/AssistantChat";
import { ClaudeSignIn } from "@/components/ClaudeSignIn";
import { SessionReauth } from "@/components/SessionReauth";
import { Button } from "@/components/Button";
import { Card, EmptyState, Section } from "@/components/Section";
import { useAssistant, useAssistantAction, useAssistantThreads } from "@/hooks/use-assistant";
import { useConfirm } from "@/hooks/use-confirm";
import type { AssistantProvider } from "@/api/types";
import { PROVIDER_NAMES } from "@/lib/assistant";
import { formatAgo } from "@/lib/format";

export const Route = createFileRoute("/assistants")({
  head: () => ({ meta: [{ title: "Assistants — Pulse" }] }),
  component: AssistantsPage,
});

function AssistantsPage() {
  const access = useAssistantAccess();
  const accounts = useAccounts();
  const [accountId, setAccountId] = useState(0);
  const [provider, setProvider] = useState<AssistantProvider>("codex");
  const own = accounts.data?.filter((a) => a.owner === null && a.connection === "direct") ?? [];
  const selected = own.find((a) => a.id === accountId) ?? own[0];
  return (
    <div className="space-y-6">
      <Section title="Cluster assistants">
        <p className="mb-4 text-sm text-muted-foreground">
          Connect Claude Code or Codex, continue a cluster conversation, and run training from your
          phone.
        </p>
        {(access.error ?? accounts.error) && (
          <p role="alert" className="mb-4 text-sm text-fail">
            Couldn't load assistants. Try refreshing Pulse.
          </p>
        )}
        {access.data && !access.data.enabled ? (
          <EmptyState title="Assistants are off">
            <p>
              The server admin can enable them with{" "}
              <code className="break-all font-mono">PULSE_ASSISTANTS_ENABLED=true</code> and restart
              Pulse.
            </p>
            <p className="mt-2">
              Assistants run as your cluster login and can edit files and submit jobs.
            </p>
          </EmptyState>
        ) : (
          access.data?.enabled && (
            <div className="space-y-4">
              {!access.data.verified && <SessionReauth />}
              {!accounts.isPending && !selected && (
                <EmptyState title="Connect a cluster over SSH">
                  <p>
                    Assistants need your own direct SSH account. The reporting agent stays
                    read-only.
                  </p>
                  <Link to="/accounts" className="mt-3 inline-block underline">
                    Open Accounts
                  </Link>
                </EmptyState>
              )}
              {selected && (
                <>
                  <label className="block max-w-sm space-y-1 text-xs text-muted-foreground">
                    Cluster
                    <select
                      aria-label="Cluster"
                      value={selected.id}
                      onChange={(e) => setAccountId(Number(e.target.value))}
                      className="block w-full rounded-md border bg-background px-3 py-2 text-sm"
                    >
                      {own.map((a) => (
                        <option key={a.id} value={a.id}>
                          {a.username}@{a.cluster}
                        </option>
                      ))}
                    </select>
                  </label>
                  <div className="flex gap-2" aria-label="Assistant provider">
                    <Button
                      variant={provider === "codex" ? "primary" : "ghost"}
                      onClick={() => setProvider("codex")}
                    >
                      Codex
                    </Button>
                    <Button
                      variant={provider === "claude" ? "primary" : "ghost"}
                      onClick={() => setProvider("claude")}
                    >
                      Claude Code
                    </Button>
                  </div>
                  <ClusterAssistant
                    key={`${provider}-${selected.id}`}
                    account={selected.id}
                    provider={provider}
                    verified={access.data.verified}
                  />
                </>
              )}
            </div>
          )
        )}
      </Section>
      <SessionActivity />
    </div>
  );
}

const INTRO: Record<AssistantProvider, string> = {
  codex: "Use your ChatGPT account. Sign-in stays with Codex on the cluster.",
  claude: "Uses Claude Code on the cluster with its own sign-in: a Claude account or an API key.",
};

function ClusterAssistant({
  account,
  provider,
  verified,
}: {
  account: number;
  provider: AssistantProvider;
  verified: boolean;
}) {
  const name = PROVIDER_NAMES[provider];
  const state = useAssistant(account, provider, true);
  const connected = state.data?.connection.connected ?? false;
  const signedIn = connected && Boolean(state.data?.connection.signed_in);
  const threads = useAssistantThreads(account, provider, signedIn);
  const connect = useAssistantAction(account, async () => {
    const connection = await api.assistants.connect(account, provider);
    // Codex signs in with a device code; Claude runs its own login on the cluster.
    return connection.signed_in || provider === "claude" ? null : api.assistants.login(account);
  });
  const disconnect = useAssistantAction(account, () =>
    api.assistants.disconnect(account, provider),
  );
  const create = useAssistantAction(account, (path: string) =>
    api.assistants.create(account, provider, path),
  );
  const confirm = useConfirm();
  const [selected, setSelected] = useState<string | null>(null);
  const [workDir, setWorkDir] = useState("");
  const [adding, setAdding] = useState(false);
  const error = state.error ?? threads.error ?? connect.error ?? disconnect.error ?? create.error;
  const login = !signedIn ? connect.data : null;
  const data = threads.data?.pages.flatMap((page) => page.data) ?? [];
  return (
    <div className="space-y-4">
      <Card className="flex flex-wrap items-center justify-between gap-3 p-4">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium">{name}</p>
          <p className="mt-1 text-xs text-muted-foreground">
            {signedIn
              ? (state.data?.connection.email ?? `Connected using the cluster’s ${name} sign-in`)
              : INTRO[provider]}
          </p>
        </div>
        {connected ? (
          <Button
            variant="ghost"
            disabled={disconnect.isPending}
            onClick={() =>
              confirm.ask({
                title: `Disconnect ${name}?`,
                description:
                  "This stops assistant work on this connection. Submitted Slurm jobs keep running. Your cluster sign-in and saved chats remain available.",
                action: "Disconnect",
                onConfirm: () => disconnect.mutate(),
              })
            }
          >
            Disconnect
          </Button>
        ) : (
          <Button disabled={!verified || connect.isPending} onClick={() => connect.mutate()}>
            {connect.isPending ? "Connecting…" : `Connect ${name}`}
          </Button>
        )}
      </Card>
      {provider === "claude" && connected && !signedIn && (
        <ClaudeSignIn account={account} verified={verified} onSignedIn={() => connect.mutate()} />
      )}
      {login && (
        <Card className="space-y-3 p-4">
          <p className="text-sm">Sign in with ChatGPT and enter this one-time code:</p>
          <p className="select-all font-mono text-xl tracking-widest">{login.code}</p>
          <a
            href={login.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex rounded-md bg-foreground px-3 py-2 text-sm text-background"
          >
            Continue with ChatGPT ↗
          </a>
          <p role="status" className="text-xs text-muted-foreground">
            Waiting for authorization… Pulse will connect automatically. If device sign-in is
            disabled, enable it in ChatGPT’s security settings.
          </p>
        </Card>
      )}
      {error && (
        <p role="alert" className="text-sm text-fail">
          {error instanceof Error ? error.message : "Couldn't complete that request."}
        </p>
      )}
      {state.data?.error && (
        <p role="alert" className="text-sm text-fail">
          {state.data.error}
        </p>
      )}
      {signedIn && (
        <>
          <div className="flex items-center justify-between">
            <h3 className="text-xs text-muted-foreground uppercase">
              Conversations on this cluster
            </h3>
            <Button onClick={() => setAdding((v) => !v)}>+ New chat</Button>
          </div>
          {adding && (
            <Card className="p-4">
              <form
                className="flex flex-wrap items-end gap-3"
                onSubmit={(event) => {
                  event.preventDefault();
                  confirm.ask({
                    title: "Start a cluster conversation?",
                    description: `${name} will work in ${workDir} as your cluster login. It asks you before running commands or changing files.`,
                    action: "Start chat",
                    onConfirm: () =>
                      create.mutate(workDir, {
                        onSuccess: (thread) => {
                          setSelected(thread.id);
                          setAdding(false);
                        },
                      }),
                  });
                }}
              >
                <label className="min-w-0 flex-1 space-y-1 text-xs text-muted-foreground">
                  Project directory
                  <input
                    aria-label="Project directory"
                    required
                    pattern="/.*"
                    maxLength={4096}
                    value={workDir}
                    onChange={(e) => setWorkDir(e.target.value)}
                    placeholder="/scratch/you/project"
                    autoCapitalize="none"
                    autoCorrect="off"
                    spellCheck={false}
                    className="block w-full rounded-md border bg-background px-3 py-2 font-mono text-sm"
                  />
                </label>
                <Button type="submit" disabled={!verified || create.isPending}>
                  Start chat
                </Button>
              </form>
            </Card>
          )}
          <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,260px)_minmax(0,1fr)]">
            <Card className="max-h-80 divide-y overflow-y-auto lg:max-h-[70dvh]">
              {data.map((thread) => (
                <button
                  key={thread.id}
                  onClick={() => setSelected(thread.id)}
                  className={`block w-full min-w-0 px-4 py-3 text-left hover:bg-muted ${thread.id === selected ? "bg-muted" : ""}`}
                >
                  <p className="truncate text-sm">{thread.title}</p>
                  <p className="mt-1 truncate font-mono text-[11px] text-muted-foreground">
                    {thread.work_dir}
                  </p>
                  {state.data?.active[thread.id] && (
                    <p className="mt-1 text-xs text-muted-foreground">Working…</p>
                  )}
                </button>
              ))}
              {!data.length && (
                <p className="p-4 text-sm text-muted-foreground">
                  {threads.isPending
                    ? "Loading conversations…"
                    : "No saved conversations yet. Start a new chat above."}
                </p>
              )}
              {threads.hasNextPage && (
                <div className="p-3">
                  <Button
                    variant="ghost"
                    disabled={threads.isFetchingNextPage}
                    onClick={() => void threads.fetchNextPage()}
                  >
                    Load more
                  </Button>
                </div>
              )}
            </Card>
            {selected && state.data ? (
              <AssistantChat
                key={selected}
                account={account}
                provider={provider}
                id={selected}
                live={state.data}
                verified={verified}
              />
            ) : (
              <EmptyState title="Pick a conversation">
                Resume a chat you started over SSH, or start a new training task.
              </EmptyState>
            )}
          </div>
        </>
      )}
      {confirm.dialog}
    </div>
  );
}

function SessionActivity() {
  const audit = useAssistantAudit();
  const [shown, setShown] = useState(false);
  return (
    <Section
      title="Assistant activity"
      action={
        <Button variant="ghost" onClick={() => setShown((v) => !v)}>
          {shown ? "Hide" : "Show"}
        </Button>
      }
    >
      {shown && (
        <Card className="divide-y">
          {audit.data?.length ? (
            audit.data.map((entry) => (
              <div
                key={entry.id}
                className="flex flex-wrap justify-between gap-2 p-3 text-xs text-muted-foreground"
              >
                <span>
                  User {entry.user_id} · {entry.action.replaceAll("_", " ")}
                </span>
                <span>{formatAgo(entry.created_at)}</span>
              </div>
            ))
          ) : (
            <p className="p-4 text-sm text-muted-foreground">No assistant activity yet.</p>
          )}
        </Card>
      )}
    </Section>
  );
}
