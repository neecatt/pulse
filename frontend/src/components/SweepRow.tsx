import { Link } from "@tanstack/react-router";
import { ChevronRight } from "lucide-react";
import { useState } from "react";

import type { Account, JobState } from "@/api/types";
import { stateTone } from "@/lib/labels";
import type { Sweep } from "@/lib/runs";
import { cn } from "@/lib/utils";

import { AccountDot } from "./AccountDot";
import { JobRow } from "./JobRow";

const STATE_WORDS: Partial<Record<JobState, string>> = {
  RUNNING: "running",
  PENDING: "queued",
  COMPLETED: "done",
  FAILED: "failed",
  TIMEOUT: "at time limit",
  CANCELLED: "cancelled",
};

/** A job array shown as one collapsible row, with its tasks inside. */
export function SweepRow({ sweep, account }: { sweep: Sweep; account: Account | undefined }) {
  const [open, setOpen] = useState(false);
  const counts = new Map<JobState, number>();
  for (const task of sweep.tasks) counts.set(task.state, (counts.get(task.state) ?? 0) + 1);

  return (
    <div>
      <div className="flex items-center gap-3 p-4 compact:py-2.5">
        <button
          type="button"
          aria-expanded={open}
          aria-label={open ? "Collapse sweep" : "Expand sweep"}
          onClick={() => setOpen(!open)}
          className="flex min-w-0 flex-1 items-center gap-2 text-left"
        >
          <ChevronRight
            className={cn(
              "size-4 shrink-0 text-muted-foreground transition-transform",
              open && "rotate-90",
            )}
          />
          {account && <AccountDot color={account.color} />}
          <span className="min-w-0">
            <span className="flex items-center gap-2">
              <span className="truncate font-medium">{sweep.name}</span>
              <span className="font-mono text-xs text-muted-foreground">[{sweep.arrayId}]</span>
            </span>
            <span className="mt-1 flex flex-wrap gap-x-2 font-mono text-xs">
              <span className="text-muted-foreground">sweep · {sweep.tasks.length} tasks</span>
              {[...counts].map(([state, n]) => (
                <span key={state} className={stateTone[state]}>
                  {n} {STATE_WORDS[state] ?? state.toLowerCase()}
                </span>
              ))}
            </span>
          </span>
        </button>
        <Link
          to="/runs"
          search={{ sweep: Number(sweep.arrayId) }}
          className="shrink-0 text-xs text-muted-foreground hover:text-foreground"
        >
          Analyse →
        </Link>
      </div>
      {open && (
        <div className="divide-y border-t bg-muted/20 pl-6">
          {sweep.tasks.map((task) => (
            <JobRow key={task.id} job={task} account={account} />
          ))}
        </div>
      )}
    </div>
  );
}
