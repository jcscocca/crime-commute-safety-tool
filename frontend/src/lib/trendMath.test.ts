import { describe, expect, it } from "vitest";
import { anchorFactor, indexCitywide, rollingMean12 } from "./trendMath";

describe("anchorFactor", () => {
  it("is the pooled sum ratio over the first 12 months", () => {
    const area = [...Array(12).fill(3), 9, 9]; // ΣA(anchor)=36
    const city = [...Array(12).fill(300), 1, 1]; // ΣC(anchor)=3600
    expect(anchorFactor(area, city)).toBeCloseTo(0.01);
  });
  it("is null when the anchor area sum is zero", () => {
    expect(anchorFactor(Array(14).fill(0), Array(14).fill(100))).toBeNull();
  });
  it("is null when fewer than 13 months exist", () => {
    expect(anchorFactor(Array(12).fill(1), Array(12).fill(10))).toBeNull();
  });
});

describe("rollingMean12", () => {
  it("is null before month 12 and a trailing mean after", () => {
    const out = rollingMean12([...Array(11).fill(0), 12, 24]);
    expect(out[10]).toBeNull();
    expect(out[11]).toBeCloseTo(1); // (0×11 + 12)/12
    expect(out[12]).toBeCloseTo(3); // (0×10 + 12 + 24)/12
  });
});

describe("indexCitywide", () => {
  it("rescales by k", () => {
    expect(indexCitywide([100, 200], 0.01)).toEqual([1, 2]);
  });
});
