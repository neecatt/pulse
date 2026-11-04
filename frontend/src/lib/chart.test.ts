import { describe, expect, it } from "vitest";

import { nearestIndex } from "./chart";

describe("nearestIndex", () => {
  const xs = [0, 10, 20, 40];

  it.each([
    [-5, 0],
    [4, 0],
    [6, 1],
    [29, 2],
    [31, 3],
    [99, 3],
  ])("%d -> %d", (target, index) => {
    expect(nearestIndex(xs, target)).toBe(index);
  });

  it("handles empty input", () => {
    expect(nearestIndex([], 3)).toBeNull();
  });
});
