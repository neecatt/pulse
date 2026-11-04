import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";

import { useAccountMap, useJob, useJobMetrics } from "@/api/queries";
import type { JobDetail } from "@/api/types";
import { HparamsTable } from "@/components/HparamsTable";
import { JobNotes } from "@/components/JobNotes";
import { MetricChart } from "@/components/MetricChart";
import { MetricsPanel } from "@/components/MetricsPanel";
import { Meter } from "@/components/Meter";
import { Card, ErrorNotice, LoadingRows, Section } from "@/components/Section";
import { StateBadge } from "@/components/StateBadge";
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
  const running = job.state === "RUNNING";

  const details: [string, string | number][] = [
    ["Account", account ? `${account.username}@${account.cluster}` : "—"],
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

      <JobNotes key={job.id} job={job} />

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
        {[
          ["Epoch", job.epoch ?? "—"],
          [job.primary_metric ?? "Loss", formatNumber(job.last_loss, 4)],
          ["GPU util", running ? formatPercent(job.gpu_util) : "—"],
          ["GPU memory", running ? formatPercent(job.gpu_mem) : "—"],
        ].map(([label, value]) => (
          <div key={label} className="bg-surface p-4">
            <div className="text-xs text-muted-foreground">{label}</div>
            <div className="mt-1 font-mono text-xl">{value}</div>
          </div>
        ))}
      </section>

      <Section title="Training metrics">
        <JobMetricsSection job={job} />
      </Section>

      <SystemMetrics job={job} />

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
    </>
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

function SystemMetrics({ job }: { job: JobDetail }) {
  const charts = [
    { key: "gpu_util", title: "GPU utilisation" },
    { key: "gpu_mem", title: "GPU memory" },
  ] as const;
  if (!charts.some((c) => job.series[c.key]?.length)) return null;
  return (
    <Section title="System">
      <div className="grid gap-4 lg:grid-cols-2">
        {charts.map((c) => (
          <Card key={c.key} className="p-4">
            <div className="mb-3 font-mono text-xs">{c.title}</div>
            <MetricChart
              xAxis="time"
              domain={[0, 100]}
              unit="%"
              series={[
                {
                  key: c.key,
                  label: c.title,
                  color: "var(--foreground)",
                  points: (job.series[c.key] ?? []).map((p) => ({ x: Date.parse(p.t), y: p.v })),
                },
              ]}
            />
          </Card>
        ))}
      </div>
    </Section>
  );
}
