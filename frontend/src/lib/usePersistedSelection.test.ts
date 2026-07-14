// @vitest-environment jsdom
import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { usePersistedSelection } from "./usePersistedSelection";
import type { Place } from "../types";

const KEY = "compcat.selection";

function place(id: string): Place {
  return {
    id,
    display_label: id,
    latitude: 47.6,
    longitude: -122.3,
    visit_count: 1,
    total_dwell_minutes: null,
    inferred_place_type: "manual",
    sensitivity_class: "normal",
  } as Place;
}

beforeEach(() => localStorage.clear());

describe("usePersistedSelection", () => {
  it("stays empty and unrestored while places have not loaded", () => {
    const { result } = renderHook(() => usePersistedSelection([]));
    expect(result.current.selectedIds.size).toBe(0);
    expect(result.current.restored).toBe(false);
  });

  it("restores the stored selection filtered to existing places", () => {
    localStorage.setItem(KEY, JSON.stringify(["p1", "gone"]));
    const { result } = renderHook(() => usePersistedSelection([place("p1"), place("p2")]));
    expect(result.current.restored).toBe(true);
    expect(Array.from(result.current.selectedIds)).toEqual(["p1"]);
  });

  it("falls back to all places when nothing stored is valid", () => {
    localStorage.setItem(KEY, JSON.stringify(["gone"]));
    const { result } = renderHook(() => usePersistedSelection([place("p1"), place("p2")]));
    expect(Array.from(result.current.selectedIds).sort()).toEqual(["p1", "p2"]);
  });

  it("falls back to all places when the key is absent or unparseable", () => {
    localStorage.setItem(KEY, "{not json");
    const { result } = renderHook(() => usePersistedSelection([place("p1")]));
    expect(Array.from(result.current.selectedIds)).toEqual(["p1"]);
  });

  it("persists changes made after restore", () => {
    const { result } = renderHook(() => usePersistedSelection([place("p1"), place("p2")]));
    act(() => result.current.setSelectedIds(new Set(["p2"])));
    expect(JSON.parse(localStorage.getItem(KEY) ?? "[]")).toEqual(["p2"]);
  });

  it("does not clobber storage before restore happens", () => {
    localStorage.setItem(KEY, JSON.stringify(["p1"]));
    renderHook(() => usePersistedSelection([]));
    expect(JSON.parse(localStorage.getItem(KEY) ?? "[]")).toEqual(["p1"]);
  });

  it("keeps a pre-restore selection change instead of clobbering it on restore", () => {
    localStorage.setItem(KEY, JSON.stringify(["p1"]));
    const { result, rerender } = renderHook(({ places }) => usePersistedSelection(places), {
      initialProps: { places: [] as Place[] },
    });
    act(() => result.current.setSelectedIds(new Set<string>()));
    rerender({ places: [place("p1"), place("p2")] });
    expect(result.current.selectedIds.size).toBe(0);
    expect(result.current.restored).toBe(true);
  });

  it("restores only once even as places refresh", () => {
    localStorage.setItem(KEY, JSON.stringify(["p1"]));
    const { result, rerender } = renderHook(({ places }) => usePersistedSelection(places), {
      initialProps: { places: [place("p1"), place("p2")] },
    });
    act(() => result.current.setSelectedIds(new Set(["p2"])));
    rerender({ places: [place("p1"), place("p2"), place("p3")] });
    expect(Array.from(result.current.selectedIds)).toEqual(["p2"]);
  });
});
