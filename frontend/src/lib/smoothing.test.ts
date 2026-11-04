import { describe, expect, it } from "vitest";

import { smooth } from "./smoothing";

describe("smooth", () => {
  it("is a no-op at weight 0", () => {
    expect(smooth([1, 5, 3], 0)).toEqual([1, 5, 3]);
  });

  it("starts at the first value instead of being biased towards zero", () => {
    expect(smooth([10, 10, 10], 0.9)).toEqual([10, 10, 10].map(() => expect.closeTo(10, 9)));
  });

  it("damps noise", () => {
    const noisy = [1, 3, 1, 3, 1, 3, 1, 3];
    const smoothed = smooth(noisy, 0.8);
    const spread = (xs: number[]) => Math.max(...xs.slice(4)) - Math.min(...xs.slice(4));
    expect(spread(smoothed)).toBeLessThan(spread(noisy) / 2);
  });
});
