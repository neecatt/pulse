import { Link } from "@tanstack/react-router";

import type { Account, PulseEvent } from "@/api/types";
import { formatAgo } from "@/lib/format";
import { EVENT_LABELS, EVENT_STATE, stateTone } from "@/lib/labels";

import { AccountDot } from "./AccountDot";

export function EventItem({ event, account }: { event: PulseEvent; account: Account | undefined }) {
  const body = (
    <div className="flex gap-3 text-sm">
      <AccountDot color={account?.color ?? 0} className="mt-1.5" />
      <div className="min-w-0 flex-1">
        <div className="break-words">{event.message}</div>
        <div className="mt-0.5 flex flex-wrap items-center gap-x-2 font-mono text-[11px] text-muted-foreground">
          <span className={stateTone[EVENT_STATE[event.kind]]}>{EVENT_LABELS[event.kind]}</span>
          {account && (
            <span>
              · {account.username}@{account.cluster}
            </span>
          )}
          <span>· {formatAgo(event.created_at)}</span>
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
