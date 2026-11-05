import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";

import {
  useAccounts,
  useCheckAccount,
  useDeleteAccount,
  useIssueAgentToken,
  useJobs,
  useMyTeams,
  useShareAccount,
  useUpdateAccount,
} from "@/api/queries";
import type { Account } from "@/api/types";
import { AccountDot } from "@/components/AccountDot";
import { AccountForm } from "@/components/AccountForm";
import { AgentInstall } from "@/components/AgentInstall";
import { Button } from "@/components/Button";
import { ShareSwitches } from "@/components/ShareSwitches";
import { Card, EmptyState, ErrorNotice, LoadingRows, Section } from "@/components/Section";
import { Toggle } from "@/components/Toggle";
import { accountLabel } from "@/lib/accounts";
import { formatAgo } from "@/lib/format";

export const Route = createFileRoute("/accounts")({
  head: () => ({ meta: [{ title: "Accounts — Pulse" }] }),
  component: AccountsPage,
});

function AccountsPage() {
  const { data, error, isPending } = useAccounts();
  const [adding, setAdding] = useState(false);
  const own = data?.filter((a) => a.owner === null);
  const shared = data?.filter((a) => a.owner !== null) ?? [];

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
          ) : own?.length ? (
            <Card className="divide-y">
              {own.map((a) => (
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
      {shared.length > 0 && (
        <Section title="Shared with you">
          <Card className="divide-y">
            {shared.map((a) => (
              <SharedAccountRow key={a.id} account={a} />
            ))}
          </Card>
        </Section>
      )}
    </div>
  );
}

/** A teammate's account: visible here, but only its owner can change it. */
function SharedAccountRow({ account }: { account: Account }) {
  return (
    <div className="flex items-center gap-3 p-4">
      <AccountDot color={account.color} className="size-2.5" />
      <div className="min-w-0 flex-1">
        <div className="truncate font-medium">{accountLabel(account)}</div>
        <div className="truncate text-xs text-muted-foreground">
          {account.last_error ??
            (account.last_polled_at
              ? `Shared by ${account.owner} · synced ${formatAgo(account.last_polled_at)}`
              : `Shared by ${account.owner}`)}
        </div>
      </div>
    </div>
  );
}

function AccountRow({ account }: { account: Account }) {
  const update = useUpdateAccount();
  const share = useShareAccount();
  const teams = useMyTeams();
  const remove = useDeleteAccount();
  const check = useCheckAccount();
  const issueToken = useIssueAgentToken();
  const { data: jobs } = useJobs();
  const agent = account.connection === "agent";
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
          {account.jump_host && ` · via ${account.jump_host}`}
          {agent && " · via agent"}
        </div>
        <div className={`mt-1 truncate text-xs text-muted-foreground ${status.className}`}>
          {status.text}
        </div>
        {issueToken.data && (
          <div className="mt-3">
            <AgentInstall token={issueToken.data.token} />
          </div>
        )}
        {check.data && (
          <div className={`mt-1 text-xs ${check.data.ok ? "text-run" : "text-fail"}`}>
            {check.data.ok ? "Connection OK" : check.data.error}
          </div>
        )}
      </div>
      <div className="flex w-full flex-wrap items-center justify-end gap-2 sm:w-auto">
        <ShareSwitches
          teams={teams}
          shared={account.shared_with}
          what={`${account.username}@${account.cluster}'s jobs`}
          onChange={(teamId, shared) => share.mutate({ id: account.id, teamId, shared })}
        />
        <label className="mr-auto flex items-center gap-2 text-xs text-muted-foreground sm:mr-0">
          Alerts
          <Toggle
            label={`Alerts for ${account.username}@${account.cluster}`}
            checked={account.notify}
            onChange={(notify) => update.mutate({ id: account.id, notify })}
          />
        </label>
        {agent ? (
          <Button
            variant="ghost"
            disabled={issueToken.isPending}
            onClick={() => {
              if (
                confirm(
                  "Get a new install command? The agent installed with the old one stops working.",
                )
              ) {
                issueToken.mutate(account.id);
              }
            }}
          >
            Reinstall
          </Button>
        ) : (
          <Button
            variant="ghost"
            onClick={() => check.mutate(account.id)}
            disabled={check.isPending}
          >
            {check.isPending ? "Testing…" : "Test"}
          </Button>
        )}
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
