// @vitest-environment jsdom
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useTrends } from "./useTrends";
import type { TrendsResponse } from "../types";

const fetchTrends = vi.fn();

vi.mock("../api/client", () => ({
  getTrends: (...args: unknown[]) => fetchTrends(...args),
}));

function response(over: Partial<TrendsResponse> = {}): TrendsResponse {
  return {
    layer: "reported",
    mcpp: "TEST HILL",
    mcpp_label: "Test Hill",
    category: null,
    months: ["2026-05", "2026-06"],
    area_counts: [3, 4],
    citywide_counts: [300, 400],
    ...over,
  };
}

beforeEach(() => {
  vi.useFakeTimers();
  fetchTrends.mockReset().mockResolvedValue(response());
});
afterEach(() => {
  vi.runAllTimers();
  vi.useRealTimers();
});

describe("useTrends", () => {
  it("does not fetch while mcpp is null and keeps data null", () => {
    const { result } = renderHook(() => useTrends(null, "reported", null));
    expect(fetchTrends).not.toHaveBeenCalled();
    expect(result.current.data).toBeNull();
  });

  it("fetches after the debounce with the right params", async () => {
    const { result } = renderHook(() => useTrends("TEST HILL", "reported", "PROPERTY"));
    expect(fetchTrends).not.toHaveBeenCalled(); // still inside debounce window
    await act(async () => {
      vi.advanceTimersByTime(300);
    });
    expect(fetchTrends).toHaveBeenCalledTimes(1);
    expect(fetchTrends.mock.calls[0][0]).toEqual({
      mcpp: "TEST HILL",
      layer: "reported",
      category: "PROPERTY",
    });
    expect(result.current.data?.mcpp).toBe("TEST HILL");
  });

  it("aborts the in-flight request when a param changes", async () => {
    let firstSignal: AbortSignal | undefined;
    fetchTrends.mockImplementationOnce((_params, signal: AbortSignal) => {
      firstSignal = signal;
      return new Promise(() => {});
    });
    const { rerender } = renderHook(({ mcpp }) => useTrends(mcpp, "reported", null), {
      initialProps: { mcpp: "TEST HILL" },
    });
    await act(async () => {
      vi.advanceTimersByTime(300);
    });
    expect(firstSignal?.aborted).toBe(false);
    rerender({ mcpp: "BALLARD" });
    expect(firstSignal?.aborted).toBe(true);
  });

  it("sets error and clears data when a fetch fails", async () => {
    fetchTrends.mockRejectedValueOnce(new Error("boom"));
    const { result } = renderHook(() => useTrends("TEST HILL", "reported", null));
    await act(async () => {
      vi.advanceTimersByTime(300);
    });
    expect(result.current.error).toBe("boom");
    expect(result.current.data).toBeNull();
  });
});
