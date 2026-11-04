import { Link } from "@tanstack/react-router";

import type { Account, Job } from "@/api/types";
import { formatDuration } from "@/lib/format";
import { useUiSettings } from "@/lib/ui-settings";

import { AccountDot } from "./AccountDot";
import { Meter } from "./Meter";
import { Sparkline } from "./Sparkline";
import { StateBadge } from "./StateBadge";

export function JobRow({ job, account }: { job: Job; account: Account | undefined }) {
  const { showSparklines } = useUiSettings();
  const active = job.state === "RUNNING";
  return (
    <Link
      to="/jobs/$jobId"
      params={{ jobId: String(job.id) }}
      className="grid grid-cols-[1fr_auto] items-center gap-x-4 gap-y-2 p-4 transition-colors compact:py-2.5 hover:bg-muted/50 md:grid-cols-[1fr_140px_100px]"
    >
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          {account && <AccountDot color={account.color} />}
          <span className="truncate font-medium">{job.name}</span>
          <span className="hidden font-mono text-xs text-muted-foreground sm:inline">
            #{job.slurm_id}
          </span>
        </div>
        <div className="mt-1 truncate font-mono text-xs text-muted-foreground">
          {[
            account?.cluster,
            job.partition,
            `${job.nodes}n${job.gpus ? `/${job.gpus}g` : ""}`,
            job.state === "PENDING" ? job.reason : formatDuration(job.elapsed_s),
            job.epoch && `ep ${job.epoch}`,
          ]
            .filter(Boolean)
            .join(" · ")}
        </div>
      </div>
      <div className="hidden text-run md:block">
        {active && showSparklines && <Sparkline data={job.loss_trend} />}
      </div>
      <div className="text-right">
        <StateBadge state={job.state} />
      </div>
      {active && job.time_used !== null && (
        <Meter value={job.time_used} className="col-span-2 md:hidden" />
      )}
    </Link>
  );
}
