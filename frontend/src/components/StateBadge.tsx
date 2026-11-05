import type { JobState } from "@/api/types";
import { STATE_LABELS, stateTone } from "@/lib/labels";
import { cn } from "@/lib/utils";

export function StateBadge({ state, className }: { state: JobState; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 font-mono text-[11px] tracking-wider",
        stateTone[state],
        className,
      )}
    >
      <span
        className={cn("size-1.5 rounded-full bg-current", state === "RUNNING" && "animate-pulse")}
      />
      {STATE_LABELS[state]}
    </span>
  );
}
