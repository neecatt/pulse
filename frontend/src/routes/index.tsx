import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";

import { useAccountMap, useAccounts, useEvents, useJobs } from "@/api/queries";
import type { Job } from "@/api/types";
import { AccountDot } from "@/components/AccountDot";
import { EventItem } from "@/components/EventItem";
import { JobRow } from "@/components/JobRow";
import { Card, EmptyState, ErrorNotice, LoadingRows, Section } from "@/components/Section";
import { Segmented } from "@/components/Segmented";
import { useUiSettings } from "@/lib/ui-settings";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/")({
  head: () => ({ meta: [{ title: "Jobs — Pulse" }] }),
  component: JobsPage,
});

type View = "active" | "all";
const HOUR_MS = 3600 * 1000;
const DAY_MS = 24 * HOUR_MS;

function JobsPage() {
  const accounts = useAccounts();
  const jobs = useJobs();
  const events = useEvents(8);
  const accountMap = useAccountMap();
  const [accountId, setAccountId] = useState<number | null>(null);
  const ui = useUiSettings();
  const [view, setView] = useState<View>(ui.defaultView);

  if (accounts.data?.length === 0) {
    return (
      <EmptyState title="No HPC accounts yet">
        <Link to="/accounts" className="text-foreground underline underline-offset-4">
          Link an account
        </Link>{" "}
        to start monitoring its Slurm jobs.
      </EmptyState>
    );
  }

  const all = jobs.data ?? [];
  const scoped = accountId === null ? all : all.filter((j) => j.account_id === accountId);
  const since = Date.now() - ui.historyHours * HOUR_MS;
  const visible = scoped.filter((j) =>
    view === "active" ? isActive(j) : isActive(j) || finishedSince(j, since),
  );

  return (
    <div className="space-y-8">
      <Stats jobs={jobs.data ? scoped : null} />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:px-0">
          <Chip active={accountId === null} onClick={() => setAccountId(null)}>
            All accounts
          </Chip>
          {accounts.data?.map((a) => (
            <Chip key={a.id} active={accountId === a.id} onClick={() => setAccountId(a.id)}>
              <AccountDot color={a.color} />
              {a.username}@{a.cluster}
            </Chip>
          ))}
        </div>
        <Segmented<View>
          label="Jobs to show"
          value={view}
          onChange={setView}
          options={[
            { value: "active", label: "Active" },
            { value: "all", label: "All" },
          ]}
        />
      </div>

      <div className="grid gap-8 lg:grid-cols-[1fr_300px]">
        <div>
          {jobs.error && <ErrorNotice error={jobs.error} />}
          {jobs.isPending ? (
            <LoadingRows />
          ) : visible.length === 0 ? (
            <EmptyState title={view === "active" ? "Nothing running or queued" : "No jobs"}>
              Finished jobs from the last {ui.historyHours} hours appear under All.
            </EmptyState>
          ) : (
            <Card className="divide-y overflow-hidden">
              {visible.map((job) => (
                <JobRow key={job.id} job={job} account={accountMap.get(job.account_id)} />
              ))}
            </Card>
          )}
        </div>

        <Section
          title="Recent activity"
          action={
            <Link to="/activity" className="text-xs text-muted-foreground hover:text-foreground">
              View all
            </Link>
          }
        >
          {events.data?.length ? (
            <ul className="space-y-2">
              {events.data.map((e) => (
                <li key={e.id}>
                  <EventItem event={e} account={accountMap.get(e.account_id)} />
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">No events yet.</p>
          )}
        </Section>
      </div>
    </div>
  );
}

function isActive(job: Job): boolean {
  return job.state === "RUNNING" || job.state === "PENDING";
}

function finishedSince(job: Job, since: number): boolean {
  const moment = job.end_time ?? job.submit_time;
  return moment !== null && new Date(moment).getTime() >= since;
}

/** Headline counters; `null` while loading so we never show a misleading 0. */
function Stats({ jobs }: { jobs: Job[] | null }) {
  if (jobs === null)
    return <StatGrid stats={STAT_LABELS.map((label) => ({ label, value: "—" }))} />;
  const running = jobs.filter((j) => j.state === "RUNNING");
  const since = Date.now() - DAY_MS;
  const failed = jobs.filter(
    (j) =>
      (j.state === "FAILED" || j.state === "TIMEOUT") &&
      j.end_time !== null &&
      new Date(j.end_time).getTime() > since,
  );
  const [runningLabel, queuedLabel, gpuLabel, failedLabel] = STAT_LABELS;
  const stats: Stat[] = [
    { label: runningLabel, value: running.length },
    { label: queuedLabel, value: jobs.filter((j) => j.state === "PENDING").length },
    { label: gpuLabel, value: running.reduce((sum, j) => sum + j.gpus, 0) },
    { label: failedLabel, value: failed.length, alert: failed.length > 0 },
  ];
  return <StatGrid stats={stats} />;
}

const STAT_LABELS = ["Running", "Queued", "GPUs in use", "Failed · 24h"] as const;

interface Stat {
  label: string;
  value: number | string;
  alert?: boolean;
}

function StatGrid({ stats }: { stats: Stat[] }) {
  return (
    <section className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border bg-border md:grid-cols-4">
      {stats.map((s) => (
        <div key={s.label} className="bg-surface p-4">
          <div className="text-xs text-muted-foreground">{s.label}</div>
          <div className={cn("mt-1 font-mono text-2xl", s.alert && "text-fail")}>{s.value}</div>
        </div>
      ))}
    </section>
  );
}

function Chip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1 text-xs transition-colors",
        active ? "bg-foreground text-background" : "text-muted-foreground hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}
