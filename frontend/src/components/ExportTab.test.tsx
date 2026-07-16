// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ExportTab } from "./ExportTab";
import type { Place } from "../types";

afterEach(cleanup);

function place(overrides: Partial<Place>): Place {
  return { id: "p1", display_label: "Home", sensitivity_class: "normal", ...overrides } as Place;
}

describe("ExportTab", () => {
  it("links to the place-summary CSV and states data limitations", () => {
    render(<ExportTab href="/exports/current.csv" places={[]} onToggleExport={() => {}} />);
    expect(screen.getByRole("link", { name: /place summary csv/i })).toHaveAttribute("href", "/exports/current.csv");
    expect(screen.getByText(/does not claim safety, risk, or recommended places/i)).toBeInTheDocument();
  });

  it("checks included places, unchecks excluded ones, and reports toggles", () => {
    const onToggleExport = vi.fn();
    render(
      <ExportTab
        href="/x.csv"
        places={[
          place({ id: "a", display_label: "Home", sensitivity_class: "normal" }),
          place({ id: "b", display_label: "Clinic", sensitivity_class: "suppress_from_public_export" }),
        ]}
        onToggleExport={onToggleExport}
      />,
    );

    expect(screen.getByRole("checkbox", { name: /home/i })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /clinic/i })).not.toBeChecked();

    fireEvent.click(screen.getByRole("checkbox", { name: /home/i }));
    expect(onToggleExport).toHaveBeenCalledWith("a", false);
  });
});
