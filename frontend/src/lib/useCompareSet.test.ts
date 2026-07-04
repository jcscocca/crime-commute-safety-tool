// @vitest-environment jsdom
import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useCompareSet, pointsFromPlaces, MAX_COMPARE_POINTS } from "./useCompareSet";
import type { Place } from "../types";

function place(id: string, label: string, lat: number, lon: number): Place {
  return { id, display_label: label, latitude: lat, longitude: lon, visit_count: 0, total_dwell_minutes: null, inferred_place_type: "manual_place", sensitivity_class: "normal" };
}
const A = place("a", "Pike", 47.61, -122.33);
const B = place("b", "Bell", 47.62, -122.34);
const C = place("c", "Yesler", 47.60, -122.32);

describe("pointsFromPlaces", () => {
  it("converts places to points and drops null coords", () => {
    const withNull = { ...A, latitude: null };
    expect(pointsFromPlaces([A, withNull])).toEqual([{ latitude: 47.61, longitude: -122.33, label: "Pike" }]);
  });
  it("de-dupes by rounded coordinate and caps at MAX", () => {
    const dupe = place("a2", "Pike again", 47.61004, -122.33004); // rounds to same 4dp
    expect(pointsFromPlaces([A, dupe])).toHaveLength(1);
    const many = Array.from({ length: 15 }, (_, i) => place(`p${i}`, `P${i}`, 47.6 + i * 0.01, -122.3 - i * 0.01));
    expect(pointsFromPlaces(many)).toHaveLength(MAX_COMPARE_POINTS);
  });
});

describe("useCompareSet", () => {
  it("seeds synchronously from the initial selection (first render, not via effect)", () => {
    const { result } = renderHook(({ seed }) => useCompareSet(seed), { initialProps: { seed: [A, B] } });
    expect(result.current.points.map((p) => p.label)).toEqual(["Pike", "Bell"]);
  });

  it("re-seeds when the selection changes, until the user edits", () => {
    const { result, rerender } = renderHook(({ seed }) => useCompareSet(seed), { initialProps: { seed: [A, B] } });
    rerender({ seed: [A, B, C] });
    expect(result.current.points).toHaveLength(3);
    act(() => result.current.removeAt(0)); // user edit -> decouple
    rerender({ seed: [A, B] });
    expect(result.current.points.map((p) => p.label)).toEqual(["Bell", "Yesler"]); // stayed edited, no reseed
  });

  it("add appends, de-dupes, and caps at MAX", () => {
    const { result } = renderHook(({ seed }) => useCompareSet(seed), { initialProps: { seed: [A] } });
    act(() => result.current.add({ latitude: 47.62, longitude: -122.34, label: "Bell" }));
    expect(result.current.points).toHaveLength(2);
    act(() => result.current.add({ latitude: 47.62, longitude: -122.34, label: "Bell dupe" }));
    expect(result.current.points).toHaveLength(2); // de-duped
  });

  it("removeAt drops the row at the index", () => {
    const { result } = renderHook(({ seed }) => useCompareSet(seed), { initialProps: { seed: [A, B, C] } });
    act(() => result.current.removeAt(1));
    expect(result.current.points.map((p) => p.label)).toEqual(["Pike", "Yesler"]);
  });
});
