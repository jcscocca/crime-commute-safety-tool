import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { createSession, getDashboardSummary } from "./api/client";

vi.mock("./api/client", () => ({
  createBulkPlaces: vi.fn(),
  createPlace: vi.fn(),
  createSession: vi.fn(),
  deletePlace: vi.fn(),
  getDashboardSummary: vi.fn(),
}));

const summary = {
  totals: {
    place_count: 0,
    visit_count: 0,
    incident_count: 0,
  },
  privacy: {
    normal: 0,
    home_candidate: 0,
    work_candidate: 0,
    suppressed: 0,
  },
  places: [],
  crime_summaries: [],
  analysis: {
    available_radii_m: [],
  },
  exports: {
    tableau_place_summary_csv: "",
  },
};

afterEach(() => {
  vi.clearAllMocks();
});

describe("App", () => {
  it("renders the dashboard shell copy", () => {
    vi.mocked(createSession).mockResolvedValue({ session_state: "ready" });
    vi.mocked(getDashboardSummary).mockResolvedValue(summary);

    render(<App />);

    expect(screen.getByText("Seattle reported incident context")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Compare places you visit" })
    ).toBeInTheDocument();
    expect(
      screen.getByText(/without uploading personal location history/i)
    ).toBeInTheDocument();
  });
});
