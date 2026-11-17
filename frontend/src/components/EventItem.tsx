import { Link } from "@tanstack/react-router";
import { ChevronRight } from "lucide-react";
import { useState } from "react";

import type { Account, PulseEvent } from "@/api/types";
import { formatAgo, formatClock } from "@/lib/format";
import { EVENT_LABELS, EVENT_STATE, stateTone } from "@/lib/labels";
import { useUiSettings } from "@/lib/ui-settings";
import { cn } from "@/lib/utils";

import { accountLabel } from "@/lib/accounts";

import { AccountDot } from "./AccountDot";

export function EventItem({ event, account }: { event: PulseEvent; account: Account | undefined }) {
  const { timeFormat } = useUiSettings();
  const body = (
    <div className="flex gap-3 text-sm">
      <AccountDot color={account?.color ?? 0} className="mt-1.5" />
      <div className="min-w-0 flex-1">
        <div className="break-words">{event.message}</div>
        <div className="mt-0.5 flex flex-wrap items-center gap-x-2 font-mono text-[11px] text-muted-foreground">
          <span className={stateTone[EVENT_STATE[event.kind]]}>{EVENT_LABELS[event.kind]}</span>
          {account && <span>· {accountLabel(account)}</span>}
          <span>
            · {timeFormat === "clock" ? formatClock(event.created_at) : formatAgo(event.created_at)}
          </span>
        </div>
      </div>
    </div>
  );
  if (event.job_id === null) return body;
  return (
    <Link
      to="/jobs/$jobId"
      params={{ jobId: String(event.job_id) }}
      className="-mx-2 block rounded-md px-2 py-1 hover:bg-muted/50"
    >
      {body}
    </Link>
  );
}

/**
 * Events stacked by stackEvents: one row ("qe_sel × 8 · Job completed") that
 * expands to the single events. A stack of one is just the event.
 */
export function EventStack({
  events,
  name,
  account,
}: {
  events: PulseEvent[];
  name: string | undefined;
  account: Account | undefined;
}) {
  const { timeFormat } = useUiSettings();
  const [open, setOpen] = useState(false);
  const [newest] = events;
  if (!newest) return null;
  if (events.length === 1) return <EventItem event={newest} account={account} />;
  return (
    <div>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="-mx-2 flex w-[calc(100%+1rem)] gap-3 rounded-md px-2 py-1 text-left text-sm hover:bg-muted/50"
      >
        <AccountDot color={account?.color ?? 0} className="mt-1.5" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <span className="truncate">{name}</span>
            <span className="shrink-0 font-mono text-xs text-muted-foreground">
              × {events.length}
            </span>
            <ChevronRight
              className={cn(
                "size-3.5 shrink-0 text-muted-foreground transition-transform",
                open && "rotate-90",
              )}
            />
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-2 font-mono text-[11px] text-muted-foreground">
            <span className={stateTone[EVENT_STATE[newest.kind]]}>{EVENT_LABELS[newest.kind]}</span>
            {account && <span>· {accountLabel(account)}</span>}
            <span>
              ·{" "}
              {timeFormat === "clock"
                ? formatClock(newest.created_at)
                : formatAgo(newest.created_at)}
            </span>
          </div>
        </div>
      </button>
      {open && (
        <div className="mt-1 ml-1 space-y-1 border-l pl-3">
          {events.map((e) => (
            <EventItem key={e.id} event={e} account={account} />
          ))}
        </div>
      )}
    </div>
  );
}
