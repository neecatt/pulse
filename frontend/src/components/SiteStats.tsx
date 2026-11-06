import { useMe, useSiteStats } from "@/api/queries";
import type { DayStats } from "@/api/types";
import { sumLastDays } from "@/lib/site-stats";

import { Card, Section } from "./Section";

const WEEK = 7;

/** Who's using this server: visitors, demos, sign-ups and active users. Admins only. */
export function SiteStats() {
  const { data: me } = useMe();
  const isAdmin = me?.is_admin ?? false;
  const { data } = useSiteStats(isAdmin);
  if (!isAdmin || !data) return null;

  const week = sumLastDays(data.days, WEEK);
  const tiles: [string, number, string][] = [
    ["Visitors", week.visitors, `${week.views} page views`],
    ["Demos started", week.demos, `${data.guests} running now`],
    [
      "Sign-ups",
      week.signups,
      week.signups_after_demo ? `${week.signups_after_demo} after a demo` : "",
    ],
    ["Active users", data.active_users, `of ${data.users} accounts`],
  ];

  return (
    <Section title="Site · last 7 days">
      <Card>
        <div className="grid grid-cols-2 gap-px overflow-hidden rounded-t-lg bg-border md:grid-cols-4">
          {tiles.map(([label, value, hint]) => (
            <div key={label} className="bg-surface p-4">
              <div className="text-xs text-muted-foreground">{label}</div>
              <div className="mt-1 font-mono text-2xl">{value}</div>
              <div className="mt-0.5 min-h-4 text-[11px] text-muted-foreground">{hint}</div>
            </div>
          ))}
        </div>
        <div className="border-t p-4">
          <div className="mb-2 flex justify-between text-xs text-muted-foreground">
            <span>Visitors per day</span>
            <span>{data.days.length} days</span>
          </div>
          <VisitorBars days={data.days} />
          <p className="mt-3 text-[11px] text-muted-foreground">
            Counted on this server, without cookies or third parties. Visitors are told apart within
            a day only; no addresses are stored.
          </p>
        </div>
      </Card>
    </Section>
  );
}

/** Daily visitors as bars, today on the right; hover a bar for its numbers. */
function VisitorBars({ days }: { days: DayStats[] }) {
  const peak = Math.max(1, ...days.map((d) => d.visitors));
  return (
    <div>
      <div className="flex h-20 items-end gap-[2px]">
        {days.map((d) => (
          <div
            key={d.day}
            title={`${d.day}: ${d.visitors} visitors, ${d.demos} demos, ${d.signups} sign-ups`}
            className="flex h-full flex-1 items-end"
          >
            <div
              className="w-full rounded-t-[2px] bg-muted-foreground/40 hover:bg-muted-foreground/70"
              style={{ height: `${Math.max(2, (d.visitors / peak) * 100)}%` }}
            />
          </div>
        ))}
      </div>
      <div className="mt-1 flex justify-between font-mono text-[10px] text-muted-foreground">
        <span>{days[0]?.day.slice(5)}</span>
        <span>today</span>
      </div>
    </div>
  );
}
