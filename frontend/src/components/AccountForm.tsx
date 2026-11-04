import { useState, type FormEvent } from "react";

import {
  useAccounts,
  useCheckAccount,
  useCreateAccount,
  useIssueAgentToken,
  useSetup,
} from "@/api/queries";
import type { Account, Connection } from "@/api/types";
import { useCopy } from "@/hooks/use-copy";
import { parseSshTarget } from "@/lib/ssh-target";
import { cn } from "@/lib/utils";

import { AgentInstall } from "./AgentInstall";
import { Button } from "./Button";
import { CopyButton } from "./CopyButton";
import { Segmented } from "./Segmented";

const inputClass =
  "h-10 w-full rounded-md border bg-background px-3 font-mono text-sm outline-none placeholder:text-muted-foreground/60 focus:border-ring";

const CONNECTIONS: { value: Connection; label: string; hint: string }[] = [
  { value: "direct", label: "Direct", hint: "Pulse signs in over SSH with its own key." },
  {
    value: "agent",
    label: "Via agent",
    hint: "For clusters with 2FA: a small script on the login node reports to Pulse.",
  },
];

/**
 * Add an account from the login people already use (`jdoe@lumi.csc.fi`), then
 * connect straight away so problems show up here rather than later.
 */
export function AccountForm({ onDone }: { onDone: () => void }) {
  const { data: setup } = useSetup();
  const create = useCreateAccount();
  const check = useCheckAccount();
  const issueToken = useIssueAgentToken();
  const [login, setLogin] = useState("");
  const [name, setName] = useState("");
  const [connection, setConnection] = useState<Connection>("direct");
  const [account, setAccount] = useState<Account | null>(null);

  const target = parseSshTarget(login);
  const busy = create.isPending || check.isPending || issueToken.isPending;
  const failed = check.data?.ok === false ? check.data.error : null;
  const hint = CONNECTIONS.find((c) => c.value === connection)?.hint;

  const save = async () => {
    if (account) return account;
    if (!target) return null;
    const saved = await create.mutateAsync({
      ...target,
      connection,
      ...(name.trim() ? { cluster: name.trim() } : {}),
    });
    setAccount(saved);
    return saved;
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    // Errors surface through the mutations' state, shown below.
    const saved = await save().catch(() => null);
    if (!saved) return;
    if (saved.connection === "agent") {
      issueToken.mutate(saved.id);
      return;
    }
    const result = await check.mutateAsync(saved.id).catch(() => null);
    if (result?.ok) onDone();
  };

  if (account?.connection === "agent" && issueToken.data) {
    return <AgentWaiting account={account} token={issueToken.data.token} onDone={onDone} />;
  }

  return (
    <form onSubmit={submit} className="space-y-5 p-4">
      <div className="space-y-2">
        <Segmented<Connection>
          label="How Pulse connects"
          value={connection}
          onChange={setConnection}
          disabled={account !== null}
          options={CONNECTIONS}
        />
        <p className="text-xs text-muted-foreground">{hint}</p>
      </div>

      {connection === "direct" &&
        (setup?.ssh_public_key ? (
          <KeyStep publicKey={setup.ssh_public_key} />
        ) : (
          setup && (
            <p className="rounded-md bg-muted/60 px-3 py-2 text-xs text-muted-foreground">
              Demo mode: accounts connect to a simulated cluster, so any login works.
            </p>
          )
        ))}

      <div className="space-y-2">
        <label htmlFor="ssh-login" className="text-sm font-medium">
          Your SSH login
        </label>
        <input
          id="ssh-login"
          required
          autoFocus
          value={login}
          disabled={account !== null}
          onChange={(e) => setLogin(e.target.value)}
          placeholder="jdoe@lumi.csc.fi"
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          className={inputClass}
        />
        <p className="min-h-4 font-mono text-xs text-muted-foreground">
          {target
            ? `${target.username} on ${target.host}${target.port === 22 ? "" : `:${target.port}`}`
            : login
              ? "Enter it like you'd type after ssh, e.g. jdoe@cluster.example.org"
              : "Paste the same login you use with ssh."}
        </p>
      </div>

      <details className="text-xs text-muted-foreground">
        <summary className="cursor-pointer select-none">Name (optional)</summary>
        <input
          value={name}
          disabled={account !== null}
          onChange={(e) => setName(e.target.value)}
          placeholder="Detected from the host, e.g. LUMI"
          className={`${inputClass} mt-2`}
        />
      </details>

      {(create.error ?? issueToken.error) && (
        <p className="text-xs text-fail">{(create.error ?? issueToken.error)?.message}</p>
      )}
      {failed && (
        <div className="space-y-1 rounded-md border border-fail/40 px-3 py-2 text-xs">
          <p className="text-fail">{failed}</p>
          <p className="text-muted-foreground">
            The account is saved; fix the issue and try again, or close and retry later.
          </p>
        </div>
      )}

      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={onDone}>
          {account ? "Close" : "Cancel"}
        </Button>
        <Button type="submit" disabled={busy || (!target && !account)}>
          {busy
            ? "Connecting…"
            : failed
              ? "Try again"
              : connection === "agent"
                ? "Next"
                : "Connect"}
        </Button>
      </div>
    </form>
  );
}

/** Shows the install command and waits (via live updates) for the first report. */
function AgentWaiting({
  account,
  token,
  onDone,
}: {
  account: Account;
  token: string;
  onDone: () => void;
}) {
  const { data: accounts } = useAccounts();
  const latest = accounts?.find((a) => a.id === account.id) ?? account;
  const connected = latest.last_polled_at !== null && latest.last_error === null;

  return (
    <div className="space-y-4 p-4">
      <p className="text-sm font-medium">
        Install the agent for {account.username}@{account.cluster}
      </p>
      <AgentInstall token={token} />
      <p
        className={cn("text-xs", connected ? "text-run" : "text-muted-foreground")}
        aria-live="polite"
      >
        {connected
          ? "✓ Connected. Jobs from this cluster now appear live."
          : latest.last_error
            ? latest.last_error
            : "Waiting for the agent's first report…"}
      </p>
      <div className="flex justify-end">
        <Button variant={connected ? "primary" : "ghost"} onClick={onDone}>
          {connected ? "Done" : "Finish later"}
        </Button>
      </div>
    </div>
  );
}

function KeyStep({ publicKey }: { publicKey: string }) {
  const command = `echo '${publicKey}' >> ~/.ssh/authorized_keys`;
  return (
    <div className="space-y-2">
      <p className="text-sm font-medium">Let Pulse sign in to your cluster</p>
      <p className="text-xs text-muted-foreground">
        Run this once on the cluster's login node. Pulse only runs read-only Slurm commands.
      </p>
      <div className="flex items-start gap-2">
        <code className="min-w-0 flex-1 truncate rounded-md bg-muted/60 px-3 py-2 font-mono text-xs">
          {command}
        </code>
        <CopyButton text={command} />
      </div>
      <p className="text-xs text-muted-foreground">
        If your centre manages keys through a web portal, upload{" "}
        <CopyInline text={publicKey}>Pulse's public key</CopyInline> there instead.
      </p>
    </div>
  );
}

function CopyInline({ text, children }: { text: string; children: string }) {
  const { copied, copy } = useCopy();
  return (
    <button
      type="button"
      className="underline underline-offset-2 hover:text-foreground"
      onClick={() => copy(text)}
    >
      {copied ? "copied" : children}
    </button>
  );
}
