import { describe, expect, it } from "vitest";

import { formatAgo, formatDuration, formatNumber, formatPercent } from "./format";

describe("formatDuration", () => {
  it.each([
    [0, "0m"],
    [59, "0m"],
    [3725, "1h 02m"],
    [90_000, "1d 1h"],
    [-5, "0m"],
  ])("%i s -> %s", (seconds, expected) => {
    expect(formatDuration(seconds)).toBe(expected);
  });
});

describe("formatAgo", () => {
  const now = Date.parse("2026-01-01T12:00:00Z");

  it.each([
    ["2026-01-01T11:59:30Z", "now"],
    ["2026-01-01T11:55:00Z", "5m"],
    ["2026-01-01T09:00:00Z", "3h"],
    ["2025-12-30T12:00:00Z", "2d"],
  ])("%s -> %s", (iso, expected) => {
    expect(formatAgo(iso, now)).toBe(expected);
  });
});

describe("number formatting", () => {
  it("handles missing values", () => {
    expect(formatNumber(null)).toBe("—");
    expect(formatPercent(null)).toBe("—");
  });

  it("rounds", () => {
    expect(formatNumber(0.123456, 3)).toBe("0.123");
    expect(formatPercent(87.6)).toBe("88%");
  });
});
