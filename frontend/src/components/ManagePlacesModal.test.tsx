// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ManagePlacesModal } from "./ManagePlacesModal";
import type { Place } from "../types";

afterEach(cleanup);

function place(id: string, label: string): Place {
  return {
    id,
    display_label: label,
    latitude: 47.6,
    longitude: -122.3,
    visit_count: 1,
    total_dwell_minutes: null,
    inferred_place_type: "manual",
    sensitivity_class: "normal",
  } as Place;
}

const baseProps = {
  places: [place("p1", "Home"), place("p2", "Work")],
  selectedIds: new Set(["p1"]),
  summary: null,
  radiusM: 400,
  addPinMode: false,
  search: <div data-testid="search-slot" />,
  onStartAddPin: vi.fn(),
  onToggleSelect: vi.fn(),
  onDelete: vi.fn(),
  onManualSubmit: vi.fn().mockResolvedValue(undefined),
  onImportSubmit: vi.fn().mockResolvedValue(undefined),
  onUploaded: undefined,
  onClose: vi.fn(),
};

describe("ManagePlacesModal", () => {
  it("opens on the Manage view with the place list, search slot, and privacy note", () => {
    render(<ManagePlacesModal {...baseProps} initialView="manage" />);
    expect(screen.getByRole("dialog", { name: "Manage places" })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Select Home" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("checkbox", { name: "Select Work" })).toHaveAttribute("aria-checked", "false");
    expect(screen.getByTestId("search-slot")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove Work" })).toBeInTheDocument();
  });

  it("switches to the Manual view and submits a place", async () => {
    render(<ManagePlacesModal {...baseProps} initialView="manage" />);
    fireEvent.click(screen.getByRole("button", { name: "Manual" }));
    expect(screen.getByRole("dialog", { name: "Add a place manually" })).toBeInTheDocument();
  });

  it("opens directly on a non-manage view when asked", () => {
    render(<ManagePlacesModal {...baseProps} initialView="manual" />);
    expect(screen.getByRole("dialog", { name: "Add a place manually" })).toBeInTheDocument();
  });

  it("delegates delete, toggle, drop-pin, and close", () => {
    render(<ManagePlacesModal {...baseProps} initialView="manage" />);
    fireEvent.click(screen.getByRole("checkbox", { name: "Select Work" }));
    expect(baseProps.onToggleSelect).toHaveBeenCalledWith("p2");
    fireEvent.click(screen.getByRole("button", { name: "Remove Home" }));
    expect(baseProps.onDelete).toHaveBeenCalledWith("p1");
    fireEvent.click(screen.getByRole("button", { name: /drop pin/i }));
    expect(baseProps.onStartAddPin).toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(baseProps.onClose).toHaveBeenCalled();
  });
});
