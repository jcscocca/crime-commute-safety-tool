import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Place } from "../types";
import { PlaceTable } from "./PlaceTable";

const samplePlace: Place = {
  id: "p1",
  display_label: "Library",
  latitude: 47.621,
  longitude: -122.321,
  visit_count: 6,
  total_dwell_minutes: null,
  inferred_place_type: "manual_place",
  sensitivity_class: "normal",
};

describe("PlaceTable", () => {
  it("calls onToggle with the place id when a row checkbox is clicked", async () => {
    const onToggle = vi.fn();

    render(
      <PlaceTable
        places={[samplePlace]}
        selectedIds={new Set()}
        onToggle={onToggle}
        onDelete={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("checkbox", { name: "Select Library" }));

    expect(onToggle).toHaveBeenCalledWith("p1");
  });
});
