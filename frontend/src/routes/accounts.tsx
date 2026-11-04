import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";

import {
  useAccounts,
  useCheckAccount,
  useDeleteAccount,
  useJobs,
  useUpdateAccount,
} from "@/api/queries";
import type { Account } from "@/api/types";
import { AccountDot } from "@/components/AccountDot";
import { AccountForm } from "@/components/AccountForm";
import { Button } from "@/components/Button";
import { Card, EmptyState, ErrorNotice, LoadingRows, Section } from "@/components/Section";
import { Toggle } from "@/components/Toggle";
import { formatAgo } from "@/lib/format";

export const Route = createFileRoute("/accounts")({
  head: () => ({ meta: [{ title: "Accounts — Pulse" }] }),
  component: AccountsPage,
});

function AccountsPage() {
  const { data, error, isPending } = useAccounts();
  const [adding, setAdding] = useState(false);

  return (
    <div className="space-y-6">
      <Section
        title="HPC accounts"
        action={!adding && <Button onClick={() => setAdding(true)}>+ Add account</Button>}
      >
        <div className="space-y-4">
          {adding && (
            <Card>
              <AccountForm onDone={() => setAdding(false)} />
            </Card>
          )}
          {error && <ErrorNotice error={error} />}
          {isPending ? (
            <LoadingRows rows={2} />
          ) : data?.length ? (
            <Card className="divide-y">
              {data.map((a) => (
                <AccountRow key={a.id} account={a} />
              ))}
            </Card>
          ) : (
            !adding && (
              <EmptyState title="No accounts linked">
                Add each cluster login you use; Pulse watches all of them together.
              </EmptyState>
            )
          )}
        </div>
      </Section>

      <p className="text-xs leading-relaxed text-muted-foreground">
        Pulse connects to the login node over SSH using the server's key and runs read-only{" "}
        <code className="font-mono">sacct</code> / <code className="font-mono">scontrol</code>{" "}
        commands. Authorise the server's public key in{" "}
        <code className="font-mono">~/.ssh/authorized_keys</code> on each cluster.
      </p>
    </div>
  );
}

function AccountRow({ account }: { account: Account }) {
  const update = useUpdateAccount();
  const remove = useDeleteAccount();
  const check = useCheckAccount();
  const { data: jobs } = useJobs();
  const jobCount = jobs?.filter((j) => j.account_id === account.id).length;

  const status = account.last_error
    ? { text: account.last_error, className: "text-fail" }
    : account.last_polled_at
      ? {
          text: [
            jobCount !== undefined && `${jobCount} jobs`,
            `synced ${formatAgo(account.last_polled_at)}`,
          ]
            .filter(Boolean)
            .join(" · "),
          className: "",
        }
      : { text: "Waiting for first sync…", className: "" };

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-3 p-4">
      <AccountDot color={account.color} className="size-2.5" />
      <div className="min-w-0 flex-1">
        <div className="truncate font-medium">
          {account.username}@{account.cluster}
        </div>
        <div className="truncate font-mono text-xs text-muted-foreground">
          {account.host}
          {account.port !== 22 && `:${account.port}`}
        </div>
        <div className={`mt-1 truncate text-xs text-muted-foreground ${status.className}`}>
          {status.text}
        </div>
        {check.data && (
          <div className={`mt-1 text-xs ${check.data.ok ? "text-run" : "text-fail"}`}>
            {check.data.ok ? "Connection OK" : check.data.error}
          </div>
        )}
      </div>
      <div className="flex w-full items-center justify-end gap-2 sm:w-auto">
        <label className="mr-auto flex items-center gap-2 text-xs text-muted-foreground sm:mr-0">
          Alerts
          <Toggle
            label={`Alerts for ${account.username}@${account.cluster}`}
            checked={account.notify}
            onChange={(notify) => update.mutate({ id: account.id, notify })}
          />
        </label>
        <Button variant="ghost" onClick={() => check.mutate(account.id)} disabled={check.isPending}>
          {check.isPending ? "Testing…" : "Test"}
        </Button>
        <Button
          variant="danger"
          disabled={remove.isPending}
          onClick={() => {
            if (confirm(`Remove ${account.username}@${account.cluster} and its job history?`)) {
              remove.mutate(account.id);
            }
          }}
        >
          Remove
        </Button>
      </div>
    </div>
  );
}
