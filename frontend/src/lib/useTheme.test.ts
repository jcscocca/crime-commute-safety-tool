// @vitest-environment jsdom
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useTheme } from "./useTheme";

function mockMatchMedia(dark: boolean) {
  const listeners: Array<(e: { matches: boolean }) => void> = [];
  vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({
    matches: dark,
    addEventListener: (_: string, cb: (e: { matches: boolean }) => void) => listeners.push(cb),
    removeEventListener: vi.fn(),
  }));
  return { fire: (matches: boolean) => listeners.forEach((cb) => cb({ matches })) };
}

beforeEach(() => localStorage.clear());
afterEach(() => {
  vi.unstubAllGlobals();
  document.documentElement.removeAttribute("data-theme");
});

describe("useTheme", () => {
  it("defaults to the OS scheme when nothing is stored", () => {
    mockMatchMedia(true);
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("prefers the stored explicit choice over the OS scheme", () => {
    mockMatchMedia(true);
    localStorage.setItem("wp-theme", "light");
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe("light");
  });

  it("persists an explicit choice and applies the attribute", () => {
    mockMatchMedia(false);
    const { result } = renderHook(() => useTheme());
    act(() => result.current.setTheme("dark"));
    expect(localStorage.getItem("wp-theme")).toBe("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("follows OS changes only while no explicit choice is stored", () => {
    const media = mockMatchMedia(false);
    const { result } = renderHook(() => useTheme());
    act(() => media.fire(true));
    expect(result.current.theme).toBe("dark");
    act(() => result.current.setTheme("light"));
    act(() => media.fire(true));
    expect(result.current.theme).toBe("light"); // explicit choice wins
  });
});
