import { createFileRoute } from "@tanstack/react-router";

import { useAccountMap, useEvents } from "@/api/queries";
import type { PulseEvent } from "@/api/types";
import { EventItem } from "@/components/EventItem";
import { Card, EmptyState, ErrorNotice, LoadingRows, Section } from "@/components/Section";

export const Route = createFileRoute("/activity")({
  head: () => ({ meta: [{ title: "Activity — Pulse" }] }),
  component: ActivityPage,
});

function ActivityPage() {
  const { data, error, isPending } = useEvents(200);
  const accounts = useAccountMap();

  if (isPending) return <LoadingRows rows={5} />;
  if (error) return <ErrorNotice error={error} />;
  if (data.length === 0) {
    return (
      <EmptyState title="No activity yet">
        Job starts, completions and failures across all accounts show up here.
      </EmptyState>
    );
  }

  return (
    <div className="space-y-8">
      {groupByDay(data).map(([day, events]) => (
        <Section key={day} title={day}>
          <Card className="space-y-1 p-3">
            {events.map((e) => (
              <EventItem key={e.id} event={e} account={accounts.get(e.account_id)} />
            ))}
          </Card>
        </Section>
      ))}
    </div>
  );
}

function groupByDay(events: PulseEvent[]): [string, PulseEvent[]][] {
  const groups = new Map<string, PulseEvent[]>();
  for (const event of events) {
    const day = new Date(event.created_at).toLocaleDateString(undefined, {
      weekday: "long",
      month: "short",
      day: "numeric",
    });
    groups.set(day, [...(groups.get(day) ?? []), event]);
  }
  return [...groups];
}
