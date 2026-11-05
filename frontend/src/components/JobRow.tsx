import { Link } from "@tanstack/react-router";
import { Check } from "lucide-react";
import type { ReactNode } from "react";

import type { Account, Job } from "@/api/types";
import { formatDuration } from "@/lib/format";
import { useUiSettings } from "@/lib/ui-settings";
import { cn } from "@/lib/utils";

import { AccountDot } from "./AccountDot";
import { Meter } from "./Meter";
import { Sparkline } from "./Sparkline";
import { StateBadge } from "./StateBadge";

interface JobRowProps {
  job: Job;
  account: Account | undefined;
  /** When set, the row toggles selection (compare mode) instead of opening the job. */
  selection?: { selected: boolean; onToggle: () => void };
}

const rowClass =
  "grid w-full grid-cols-[1fr_auto] items-center gap-x-4 gap-y-2 p-4 text-left transition-colors hover:bg-muted/50 compact:py-2.5 md:grid-cols-[1fr_140px_100px]";

export function JobRow({ job, account, selection }: JobRowProps) {
  const content = <RowContent job={job} account={account} selected={selection?.selected} />;
  if (selection) {
    return (
      <button
        type="button"
        role="checkbox"
        aria-checked={selection.selected}
        onClick={selection.onToggle}
        className={cn(rowClass, selection.selected && "bg-muted/60")}
      >
        {content}
      </button>
    );
  }
  return (
    <Link to="/jobs/$jobId" params={{ jobId: String(job.id) }} className={rowClass}>
      {content}
    </Link>
  );
}

function RowContent({
  job,
  account,
  selected,
}: {
  job: Job;
  account: Account | undefined;
  selected: boolean | undefined;
}): ReactNode {
  const { showSparklines } = useUiSettings();
  const active = job.state === "RUNNING";
  return (
    <>
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          {selected !== undefined && (
            <span
              className={cn(
                "grid size-4 shrink-0 place-items-center rounded border",
                selected && "border-foreground bg-foreground text-background",
              )}
            >
              {selected && <Check className="size-3" strokeWidth={3} />}
            </span>
          )}
          {account && <AccountDot color={account.color} />}
          <span className="truncate font-medium">{job.name}</span>
          <span className="hidden font-mono text-xs text-muted-foreground sm:inline">
            #{job.slurm_id}
          </span>
          {job.tags.slice(0, 3).map((tag) => (
            <span
              key={tag}
              className="hidden shrink-0 rounded-full border px-1.5 text-[10px] text-muted-foreground sm:inline"
            >
              {tag}
            </span>
          ))}
        </div>
        <div className="mt-1 truncate font-mono text-xs text-muted-foreground">
          {[
            account?.owner ? `${account.owner} · ${account.cluster}` : account?.cluster,
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
    </>
  );
}
