// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SearchPill } from "./SearchPill";
import type { GeocodeResult } from "../types";

const RESULT: GeocodeResult = { label: "8800 Delridge Way SW", latitude: 47.52, longitude: -122.36, source: "nominatim" };
const search = vi.fn();

beforeEach(() => {
  vi.useFakeTimers();
  search.mockReset().mockResolvedValue([RESULT]);
  localStorage.clear();
});
afterEach(() => {
  vi.runAllTimers();
  vi.useRealTimers();
  cleanup();
});

describe("SearchPill", () => {
  it("searches after the debounce and reports the selected result", async () => {
    const onSelect = vi.fn();
    render(<SearchPill search={search} onSelect={onSelect} addPinMode={false} onToggleAddPin={vi.fn()} />);
    fireEvent.change(screen.getByRole("combobox", { name: /search address/i }), { target: { value: "8800 Del" } });
    // Fake timers freeze findBy*'s waitFor polling; act + advancing past the debounce flushes
    // the search promise and its state update, so the option is in the DOM synchronously.
    await act(async () => { await vi.advanceTimersByTimeAsync(300); });
    fireEvent.click(screen.getByRole("option", { name: /8800 Delridge/i }));
    expect(onSelect).toHaveBeenCalledWith(RESULT);
  });

  it("carries a stable id for external focus requests", () => {
    render(<SearchPill search={search} onSelect={vi.fn()} addPinMode={false} onToggleAddPin={vi.fn()} />);
    expect(screen.getByRole("combobox", { name: /search address/i })).toHaveAttribute("id", "mc-search-input");
  });

  it("arms pin-drop mode via the pin button", () => {
    const onToggleAddPin = vi.fn();
    render(<SearchPill search={search} onSelect={vi.fn()} addPinMode={false} onToggleAddPin={onToggleAddPin} />);
    fireEvent.click(screen.getByRole("button", { name: "Drop a pin on the map" }));
    expect(onToggleAddPin).toHaveBeenCalled();
    // pressed state reflects armed mode
    cleanup();
    render(<SearchPill search={search} onSelect={vi.fn()} addPinMode onToggleAddPin={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Drop a pin on the map" })).toHaveAttribute("aria-pressed", "true");
  });
});
