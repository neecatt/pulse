import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowLeft, X } from "lucide-react";

import { useJobs, useJobsMetrics } from "@/api/queries";
import { HparamsTable } from "@/components/HparamsTable";
import { MetricsPanel } from "@/components/MetricsPanel";
import { EmptyState, LoadingRows, Section } from "@/components/Section";
import { MAX_COMPARE, RUN_COLORS } from "@/lib/labels";

export const Route = createFileRoute("/compare")({
  validateSearch: (search: Record<string, unknown>): { ids: string } => ({
    ids: typeof search["ids"] === "string" ? search["ids"] : String(search["ids"] ?? ""),
  }),
  head: () => ({ meta: [{ title: "Compare — Pulse" }] }),
  component: ComparePage,
});

function ComparePage() {
  const { ids: raw } = Route.useSearch();
  const parsed = raw.split(",").map(Number);
  const ids: number[] = [...new Set(parsed.filter((n) => Number.isInteger(n) && n > 0))].slice(
    0,
    MAX_COMPARE,
  );
  const { data: jobs = [] } = useJobs();
  const { data: metrics, isPending } = useJobsMetrics(ids);

  const runs = ids.map((id, i) => {
    const job = jobs.find((j) => j.id === id);
    return {
      id,
      label: job ? `${job.name} #${job.slurm_id}` : `job ${id}`,
      color: RUN_COLORS[i] ?? "var(--foreground)",
      metrics: metrics[i]?.metrics ?? {},
      hparams: metrics[i]?.hparams ?? {},
    };
  });

  return (
    <div className="space-y-8">
      <Link
        to="/"
        className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-3.5" /> All jobs
      </Link>
      <header className="space-y-3">
        <h1 className="text-2xl font-medium tracking-tight">Compare runs</h1>
        <div className="flex flex-wrap gap-2">
          {runs.map((run) => (
            <span
              key={run.id}
              className="inline-flex items-center gap-1.5 rounded-full border py-0.5 pr-1 pl-2.5 text-xs"
            >
              <span className="size-2 rounded-full" style={{ background: run.color }} />
              <Link
                to="/jobs/$jobId"
                params={{ jobId: String(run.id) }}
                className="hover:underline"
              >
                {run.label}
              </Link>
              <Link
                to="/compare"
                search={{ ids: ids.filter((id) => id !== run.id).join(",") }}
                aria-label={`Remove ${run.label}`}
                className="rounded-full p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                <X className="size-3" />
              </Link>
            </span>
          ))}
        </div>
      </header>

      {ids.length < 2 ? (
        <EmptyState title="Pick at least two jobs">
          On the{" "}
          <Link to="/" className="text-foreground underline underline-offset-4">
            jobs list
          </Link>
          , tap Compare and select the runs you want to see side by side.
        </EmptyState>
      ) : isPending ? (
        <LoadingRows rows={3} />
      ) : (
        <>
          <Section title="Metrics">
            <MetricsPanel runs={runs} />
          </Section>
          <Section title="Hyperparameters">
            <HparamsTable runs={runs} />
          </Section>
        </>
      )}
    </div>
  );
}
