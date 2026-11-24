import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";

import { useAccountMap, useJob, useJobMetrics, useMyTeams, useShareJob } from "@/api/queries";
import type { Account, JobDetail } from "@/api/types";
import { HparamsTable } from "@/components/HparamsTable";
import { JobNotes, SharedJobNotes } from "@/components/JobNotes";
import { MetricsPanel } from "@/components/MetricsPanel";
import { NodeUsage } from "@/components/NodeUsage";
import { ShareSwitches } from "@/components/ShareSwitches";
import { Meter } from "@/components/Meter";
import { ErrorNotice, LoadingRows, Section } from "@/components/Section";
import { accountLabel } from "@/lib/accounts";
import { FAILURE_REASONS } from "@/lib/labels";
import { latestStep, usageSummary } from "@/lib/metrics";
import { StateBadge } from "@/components/StateBadge";
import { cn } from "@/lib/utils";
import {
  formatAgo,
  formatDateTime,
  formatDuration,
  formatNumber,
  formatPercent,
} from "@/lib/format";

export const Route = createFileRoute("/jobs/$jobId")({
  head: () => ({ meta: [{ title: "Job — Pulse" }] }),
  component: JobPage,
});

function JobPage() {
  const { jobId } = Route.useParams();
  const { data: job, error, isPending } = useJob(Number(jobId));

  return (
    <div className="space-y-8">
      <Link
        to="/"
        className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-3.5" /> All jobs
      </Link>
      {error && <ErrorNotice error={error} />}
      {isPending ? <LoadingRows rows={2} /> : job && <JobDetailView job={job} />}
    </div>
  );
}

function JobDetailView({ job }: { job: JobDetail }) {
  const account = useAccountMap().get(job.account_id);
  const { data: metrics } = useJobMetrics(job.id);
  const running = job.state === "RUNNING";
  // Jobs that count iterations instead of epochs show how far training got.
  const step = job.epoch ? null : latestStep(metrics?.metrics ?? {});
  // A finished job shows how it used its GPUs over the whole run.
  const util = usageSummary(job.series["gpu_util"] ?? []);
  const memory = usageSummary(job.series["gpu_mem"] ?? []);
  const stats: [string, string][] = [
    step === null ? ["Epoch", job.epoch ?? "—"] : ["Step", step.toLocaleString()],
    [job.primary_metric ?? "Loss", formatNumber(job.last_loss, 4)],
    running || !util
      ? ["GPU util", formatPercent(running ? job.gpu_util : null)]
      : ["GPU util · avg", formatPercent(util.avg)],
    running || !memory
      ? ["GPU memory", formatPercent(running ? job.gpu_mem : null)]
      : ["GPU memory · peak", formatPercent(memory.peak)],
  ];

  const details: [string, string | number][] = [
    ["Account", account ? accountLabel(account) : "—"],
    ["Partition", job.partition],
    ["Nodes", job.nodes],
    ["GPUs", job.gpus],
    ["Node list", job.node_list ?? "—"],
    ["Submitted", formatDateTime(job.submit_time)],
    ["Started", formatDateTime(job.start_time)],
    ["Ended", formatDateTime(job.end_time)],
    ["Elapsed", formatDuration(job.elapsed_s)],
    ["Time limit", job.time_limit_s ? formatDuration(job.time_limit_s) : "—"],
    ["Exit code", job.exit_code ?? "—"],
    ["Reason", job.reason ?? "—"],
  ];

  return (
    <>
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <div className="font-mono text-xs text-muted-foreground">#{job.slurm_id}</div>
          <h1 className="truncate text-2xl font-medium tracking-tight">{job.name}</h1>
        </div>
        <StateBadge state={job.state} />
      </header>

      {job.state === "FAILED" && <FailureCard job={job} />}

      {account?.owner ? <SharedJobNotes job={job} /> : <JobNotes key={job.id} job={job} />}
      {account && !account.owner && <ShareJob job={job} account={account} />}

      {job.time_used !== null && (
        <div className="space-y-1.5">
          <div className="flex justify-between font-mono text-xs text-muted-foreground">
            <span>Time used</span>
            <span>
              {formatDuration(job.elapsed_s)} / {formatDuration(job.time_limit_s ?? 0)}
            </span>
          </div>
          <Meter value={job.time_used} />
        </div>
      )}

      <section className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border bg-border md:grid-cols-4">
        {stats.map(([label, value]) => (
          <div key={label} className="min-w-0 bg-surface p-4">
            <div className="truncate text-xs text-muted-foreground" title={label}>
              {label}
            </div>
            <div className="mt-1 font-mono text-xl">{value}</div>
          </div>
        ))}
      </section>

      <Section title="Training metrics">
        <JobMetricsSection job={job} />
      </Section>

      {Object.keys(job.node_stats).length > 0 && (
        <Section title="System">
          <NodeUsage job={job} />
        </Section>
      )}

      <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border bg-border md:grid-cols-4">
        {details.map(([label, value]) => (
          <div key={label} className="min-w-0 bg-surface p-3">
            <dt className="text-xs text-muted-foreground">{label}</dt>
            <dd className="mt-0.5 truncate font-mono text-sm">{value}</dd>
          </div>
        ))}
      </dl>

      <Section
        title="Output · tail"
        action={
          job.log_updated_at && (
            <span className="font-mono text-[11px] text-muted-foreground">
              updated {formatAgo(job.log_updated_at)}
            </span>
          )
        }
      >
        <pre className="overflow-x-auto rounded-lg border bg-muted/40 p-4 font-mono text-xs leading-relaxed text-muted-foreground">
          {job.log_tail.length ? job.log_tail.join("\n") : "No output captured yet."}
        </pre>
      </Section>

      {job.err_tail.length > 0 && (
        <Section title="Errors · tail">
          <pre className="overflow-x-auto rounded-lg border bg-muted/40 p-4 font-mono text-xs leading-relaxed text-muted-foreground">
            {job.err_tail.join("\n")}
          </pre>
        </Section>
      )}
    </>
  );
}

// Lines of output shown around the error in the failure card.
const FAILURE_CONTEXT_LINES = 8;

/** Why a job failed, first: the error from its output, else what Slurm says. */
function FailureCard({ job }: { job: JobDetail }) {
  const fallback =
    (job.reason && FAILURE_REASONS[job.reason]) ??
    job.reason ??
    (job.exit_code ? `Exited with code ${job.exit_code}` : "Failed");
  const output = job.err_tail.length ? job.err_tail : job.log_tail;
  // The lines leading up to the error. The summary may be shortened or have a
  // launcher prefix removed, so match on its start.
  const needle = job.error?.slice(0, 40);
  let end = output.length;
  while (needle && end > 0 && !output[end - 1]?.includes(needle)) end--;
  const context = end > 0 ? output.slice(Math.max(0, end - FAILURE_CONTEXT_LINES), end) : [];
  return (
    <section className="space-y-3 rounded-lg border border-fail/40 bg-fail/5 p-4">
      <div>
        <h2 className="text-xs tracking-wider text-fail uppercase">Why it failed</h2>
        <p className="mt-1 font-mono text-sm wrap-anywhere">{job.error ?? fallback}</p>
        {job.error && fallback !== "Failed" && (
          <p className="mt-1 text-xs text-muted-foreground">{fallback}</p>
        )}
        {!job.error && (
          <p className="mt-1 text-xs text-muted-foreground">
            The end of its output doesn't say why.
          </p>
        )}
      </div>
      {context.length > 0 && (
        <pre className="overflow-x-auto rounded-md border bg-background/60 p-3 font-mono text-xs leading-relaxed text-muted-foreground">
          {context.map((line, i) => (
            <div key={i} className={cn(i === context.length - 1 && "text-fail")}>
              {line || " "}
            </div>
          ))}
        </pre>
      )}
    </section>
  );
}

/** Share just this job with teams that don't already see its whole account. */
function ShareJob({ job, account }: { job: JobDetail; account: Account }) {
  const share = useShareJob(job.id);
  const teams = useMyTeams().filter((t) => !t.shareAll && !account.shared_with.includes(t.id));
  if (!teams.length) return null;
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-muted-foreground">
      <span>Share this job</span>
      <ShareSwitches
        teams={teams}
        shared={job.shared_with}
        what={job.name}
        onChange={(teamId, shared) => share.mutate({ teamId, shared })}
        disabled={share.isPending}
      />
      {share.error && <span className="text-fail">{share.error.message}</span>}
    </div>
  );
}

function JobMetricsSection({ job }: { job: JobDetail }) {
  const { data, isPending } = useJobMetrics(job.id);
  if (isPending) return <LoadingRows rows={2} />;
  const run = { id: job.id, label: job.name, color: "var(--run)" };
  return (
    <div className="space-y-8">
      <MetricsPanel
        runs={[{ ...run, metrics: data?.metrics ?? {} }]}
        primary={data?.primary ?? null}
      />
      <div>
        <h3 className="mb-2 text-xs tracking-wider text-muted-foreground uppercase">
          Hyperparameters
        </h3>
        <HparamsTable runs={[{ ...run, hparams: data?.hparams ?? job.hparams }]} />
      </div>
    </div>
  );
}
