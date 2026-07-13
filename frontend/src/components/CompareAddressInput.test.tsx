// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CompareAddressInput } from "./CompareAddressInput";
import type { GeocodingProvider } from "../lib/geocoding";
import type { GeocodeResult } from "../types";

function providerReturning(results: GeocodeResult[]): GeocodingProvider {
  return { search: vi.fn().mockResolvedValue(results) };
}
const pike: GeocodeResult = { label: "1420 Pike St", latitude: 47.61, longitude: -122.33, source: "test" };

afterEach(cleanup);

describe("CompareAddressInput", () => {
  it("adds the selected search result and clears the query", async () => {
    const onAdd = vi.fn();
    render(<CompareAddressInput provider={providerReturning([pike])} onAdd={onAdd} disabled={false} />);
    fireEvent.change(screen.getByLabelText(/add an address/i), { target: { value: "pike" } });
    fireEvent.submit(screen.getByRole("search"));
    const hit = await screen.findByText("1420 Pike St");
    fireEvent.click(hit);
    expect(onAdd).toHaveBeenCalledWith({ latitude: 47.61, longitude: -122.33, label: "1420 Pike St" });
  });

  it("compacts a long geocoder label before adding it", async () => {
    const onAdd = vi.fn();
    const longResult: GeocodeResult = {
      label:
        "4500, University Way Northeast, Greek Row, University Heights, University District, Seattle, King County, Washington, 98105, United States",
      latitude: 47.66,
      longitude: -122.31,
      source: "test",
    };
    render(<CompareAddressInput provider={providerReturning([longResult])} onAdd={onAdd} disabled={false} />);
    fireEvent.change(screen.getByLabelText(/add an address/i), { target: { value: "university way" } });
    fireEvent.submit(screen.getByRole("search"));
    const hit = await screen.findByText(longResult.label);
    fireEvent.click(hit);
    expect(onAdd).toHaveBeenCalledWith({
      latitude: 47.66,
      longitude: -122.31,
      label: "4500 University Way Northeast, Seattle",
    });
  });

  it("shows the empty-state message when no matches", async () => {
    render(<CompareAddressInput provider={providerReturning([])} onAdd={vi.fn()} disabled={false} />);
    fireEvent.change(screen.getByLabelText(/add an address/i), { target: { value: "nowhere" } });
    fireEvent.submit(screen.getByRole("search"));
    await waitFor(() => expect(screen.getByText(/no matches/i)).toBeInTheDocument());
  });

  it("disables the input at the max", () => {
    render(<CompareAddressInput provider={providerReturning([pike])} onAdd={vi.fn()} disabled={true} />);
    expect(screen.getByLabelText(/add an address/i)).toBeDisabled();
  });
});
