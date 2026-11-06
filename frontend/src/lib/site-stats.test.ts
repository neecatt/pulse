import { describe, expect, it } from "vitest";

import { sumLastDays } from "./site-stats";

const day = (d: string, visitors: number, demos = 0) => ({
  day: d,
  views: visitors * 2,
  visitors,
  demos,
  signups: 0,
  signups_after_demo: 0,
});

describe("sumLastDays", () => {
  it("adds up the most recent days only", () => {
    const days = [day("2026-11-01", 9), day("2026-11-02", 3, 1), day("2026-11-03", 4, 2)];
    expect(sumLastDays(days, 2)).toEqual({
      views: 14,
      visitors: 7,
      demos: 3,
      signups: 0,
      signups_after_demo: 0,
    });
  });

  it("copes with fewer days than asked for", () => {
    expect(sumLastDays([day("2026-11-03", 1)], 7).visitors).toBe(1);
  });
});
