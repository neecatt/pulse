import type { DayStats } from "@/api/types";

type Totals = Omit<DayStats, "day">;

/** Totals over the last `n` days (the days come oldest first). */
export function sumLastDays(days: DayStats[], n: number): Totals {
  const totals: Totals = { views: 0, visitors: 0, demos: 0, signups: 0, signups_after_demo: 0 };
  for (const day of days.slice(-n)) {
    totals.views += day.views;
    totals.visitors += day.visitors;
    totals.demos += day.demos;
    totals.signups += day.signups;
    totals.signups_after_demo += day.signups_after_demo;
  }
  return totals;
}
