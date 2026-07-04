// @vitest-environment node
import { describe, expect, it } from "vitest";

import { annualIncidentsWithin, formatPerYear } from "./rateFormat";

describe("annualIncidentsWithin", () => {
  it("converts a per-km²-day rate to expected incidents/year within the radius", () => {
    // 0.02876 /km²·day over a 500 m buffer (area π·0.25 km²) × 365.25 ≈ 8.25/yr
    expect(annualIncidentsWithin(0.02876, 500)).toBeCloseTo(8.25, 1);
  });

  it("scales with buffer area — doubling the radius quadruples the count", () => {
    expect(annualIncidentsWithin(0.1, 500) / annualIncidentsWithin(0.1, 250)).toBeCloseTo(4, 5);
  });
});

describe("formatPerYear", () => {
  it("keeps one decimal below 10, rounds at/above 10, and collapses ~0 cleanly", () => {
    expect(formatPerYear(8.26)).toBe("8.3");
    expect(formatPerYear(7.12)).toBe("7.1");
    expect(formatPerYear(11.8)).toBe("12");
    expect(formatPerYear(286)).toBe("286");
    expect(formatPerYear(0)).toBe("0");
    expect(formatPerYear(0.02)).toBe("0");
  });
});
