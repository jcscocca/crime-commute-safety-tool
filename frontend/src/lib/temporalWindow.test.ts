import { describe, expect, it } from "vitest";

import type { TemporalProfile } from "../types";
import { clampInt, DEFAULT_TRAVEL_WINDOW, windowShare } from "./temporalWindow";

function profile(partial: Partial<TemporalProfile> = {}): TemporalProfile {
  return {
    hour_counts: Array(24).fill(0),
    dow_counts: Array(7).fill(0),
    hour_by_dow: Array.from({ length: 7 }, () => Array(24).fill(0)),
    total_with_time: 0,
    without_time: 0,
    ...partial,
  };
}

describe("windowShare", () => {
  it("counts weekday evenings from the joint matrix", () => {
    const hour_by_dow = Array.from({ length: 7 }, (_, d) =>
      Array.from({ length: 24 }, (_, h) => (d <= 4 && h === 17 ? 4 : 0)),
    );
    const { count, share } = windowShare(profile({ hour_by_dow, total_with_time: 40 }), {
      dayset: "weekdays",
      startHour: 16,
      endHour: 19,
    });
    expect(count).toBe(20);
    expect(share).toBeCloseTo(0.5);
  });

  it("returns zero share when nothing has a recorded time", () => {
    const { count, share } = windowShare(profile({ total_with_time: 0 }), DEFAULT_TRAVEL_WINDOW);
    expect(count).toBe(0);
    expect(share).toBe(0);
  });

  it("an all-day window counts every cell", () => {
    const hour_by_dow = Array.from({ length: 7 }, () => Array.from({ length: 24 }, () => 1));
    const { count } = windowShare(profile({ hour_by_dow, total_with_time: 168 }), {
      dayset: "all",
      startHour: 0,
      endHour: 24,
    });
    expect(count).toBe(168);
  });
});

describe("clampInt", () => {
  it("clamps, truncates, and falls back to min on NaN", () => {
    expect(clampInt("99", 0, 23)).toBe(23);
    expect(clampInt("-3", 0, 23)).toBe(0);
    expect(clampInt("8.9", 0, 23)).toBe(8);
    expect(clampInt("abc", 1, 24)).toBe(1);
  });
});
