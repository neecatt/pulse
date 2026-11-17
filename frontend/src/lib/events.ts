import type { PulseEvent } from "@/api/types";
import { MINUTE_MS } from "@/config/constants";

// Events of one kind for same-named jobs stack while each is this close to the next.
const STACK_GAP_MS = 30 * MINUTE_MS;

/**
 * Newest-first events with repeats stacked: "qe_sel completed" for eight
 * parallel jobs becomes one stack of eight, placed where its newest event is.
 * Events whose job name is unknown stay on their own.
 */
export function stackEvents(
  events: PulseEvent[],
  jobName: (jobId: number) => string | undefined,
): PulseEvent[][] {
  const stacks: PulseEvent[][] = [];
  const open = new Map<string, PulseEvent[]>();
  for (const event of events) {
    const name = event.job_id === null ? undefined : jobName(event.job_id);
    const key = `${event.account_id}:${event.kind}:${name}`;
    const stack = name === undefined ? undefined : open.get(key);
    const last = stack?.at(-1);
    if (
      stack &&
      last &&
      Date.parse(last.created_at) - Date.parse(event.created_at) <= STACK_GAP_MS
    ) {
      stack.push(event);
    } else {
      const fresh = [event];
      stacks.push(fresh);
      open.set(key, fresh);
    }
  }
  return stacks;
}
