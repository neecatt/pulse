import { useState, type FormEvent } from "react";

import { useCheckAccount, useCreateAccount, useSetup } from "@/api/queries";
import type { Account } from "@/api/types";
import { parseSshTarget } from "@/lib/ssh-target";

import { Button } from "./Button";
import { CopyButton } from "./CopyButton";

const inputClass =
  "h-10 w-full rounded-md border bg-background px-3 font-mono text-sm outline-none placeholder:text-muted-foreground/60 focus:border-ring";

/**
 * Add an account from the login people already use (`jdoe@lumi.csc.fi`), then
 * connect straight away so problems show up here rather than later.
 */
export function AccountForm({ onDone }: { onDone: () => void }) {
  const { data: setup } = useSetup();
  const create = useCreateAccount();
  const check = useCheckAccount();
  const [login, setLogin] = useState("");
  const [name, setName] = useState("");
  const [account, setAccount] = useState<Account | null>(null);

  const target = parseSshTarget(login);
  const connecting = create.isPending || check.isPending;
  const failed = check.data?.ok === false ? check.data.error : null;

  const connect = async () => {
    const saved =
      account ??
      (target &&
        (await create.mutateAsync({
          ...target,
          ...(name.trim() ? { cluster: name.trim() } : {}),
        })));
    if (!saved) return;
    setAccount(saved);
    const result = await check.mutateAsync(saved.id);
    if (result.ok) onDone();
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    // Errors surface through create.error / check.data; nothing else to do here.
    connect().catch(() => undefined);
  };

  return (
    <form onSubmit={submit} className="space-y-5 p-4">
      {setup?.ssh_public_key ? (
        <KeyStep publicKey={setup.ssh_public_key} />
      ) : (
        setup && (
          <p className="rounded-md bg-muted/60 px-3 py-2 text-xs text-muted-foreground">
            Demo mode: accounts connect to a simulated cluster, so any login works.
          </p>
        )
      )}

      <div className="space-y-2">
        <label htmlFor="ssh-login" className="text-sm font-medium">
          {setup?.ssh_public_key ? "2. Your SSH login" : "Your SSH login"}
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
            ? `Connects as ${target.username} on ${target.host}${target.port === 22 ? "" : `:${target.port}`}`
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

      {create.error && <p className="text-xs text-fail">{create.error.message}</p>}
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
        <Button type="submit" disabled={connecting || (!target && !account)}>
          {connecting ? "Connecting…" : failed ? "Try again" : "Connect"}
        </Button>
      </div>
    </form>
  );
}

function KeyStep({ publicKey }: { publicKey: string }) {
  const command = `echo '${publicKey}' >> ~/.ssh/authorized_keys`;
  return (
    <div className="space-y-2">
      <p className="text-sm font-medium">1. Let Pulse sign in to your cluster</p>
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
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="underline underline-offset-2 hover:text-foreground"
      onClick={async () => {
        await navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
    >
      {copied ? "copied" : children}
    </button>
  );
}
