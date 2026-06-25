// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AnalyzeTab } from "./AnalyzeTab";
import type { AnalysisSettings, DashboardSummary, Place } from "../types";

const home: Place = {
  id: "p1", display_label: "Home", latitude: 47.61, longitude: -122.33, visit_count: 5,
  total_dwell_minutes: null, inferred_place_type: "manual_place", sensitivity_class: "normal",
};
const office: Place = { ...home, id: "p2", display_label: "Office", visit_count: 4 };

const analysis: AnalysisSettings = { startDate: "2026-01-01", endDate: "2026-06-24", radiusM: 250, offenseCategory: "PROPERTY" };
const analyzedSummary: DashboardSummary = {
  totals: { place_count: 2, visit_count: 9, incident_count: 180 },
  privacy: { normal: 2, home_candidate: 0, work_candidate: 0, suppressed: 0 },
  places: [home, office],
  crime_summaries: [
    { place_cluster_id: "p1", radius_m: 250, analysis_start_date: "2026-01-01", analysis_end_date: "2026-06-24", offense_category: "PROPERTY", offense_subcategory: "THEFT", nibrs_group: "A", incident_count: 30, nearest_incident_m: 42, incidents_per_visit: 6, incidents_per_hour_dwell: null },
    { place_cluster_id: "p1", radius_m: 250, analysis_start_date: "2026-01-01", analysis_end_date: "2026-06-24", offense_category: "PERSON", offense_subcategory: "ASSAULT", nibrs_group: "A", incident_count: 8, nearest_incident_m: 71, incidents_per_visit: 1.6, incidents_per_hour_dwell: null },
    { place_cluster_id: "p2", radius_m: 250, analysis_start_date: "2026-01-01", analysis_end_date: "2026-06-24", offense_category: "PROPERTY", offense_subcategory: "THEFT", nibrs_group: "A", incident_count: 120, nearest_incident_m: 18, incidents_per_visit: 30, incidents_per_hour_dwell: null },
    { place_cluster_id: "p2", radius_m: 250, analysis_start_date: "2026-01-01", analysis_end_date: "2026-06-24", offense_category: "PERSON", offense_subcategory: "ASSAULT", nibrs_group: "A", incident_count: 22, nearest_incident_m: 36, incidents_per_visit: 5.5, incidents_per_hour_dwell: null },
  ],
  analysis: { available_radii_m: [250] },
  exports: { tableau_place_summary_csv: "/x.csv" },
};

afterEach(cleanup);

describe("AnalyzeTab", () => {
  it("emits control changes and runs when a place is selected", () => {
    const onChange = vi.fn();
    const onRun = vi.fn();
    render(<AnalyzeTab selected={[home]} analysis={analysis} summary={analyzedSummary} availableRadii={[250, 500, 1000]} running={false} onChange={onChange} onRun={onRun} />);

    fireEvent.change(screen.getByLabelText("Start date"), { target: { value: "2026-02-01" } });
    expect(onChange).toHaveBeenCalledWith({ startDate: "2026-02-01" });

    fireEvent.click(screen.getByRole("button", { name: "500 m" }));
    expect(onChange).toHaveBeenCalledWith({ radiusM: 500 });

    fireEvent.click(screen.getByRole("button", { name: "Person" }));
    expect(onChange).toHaveBeenCalledWith({ offenseCategory: "PERSON" });

    fireEvent.click(screen.getByRole("button", { name: /run analysis/i }));
    expect(onRun).toHaveBeenCalled();
  });

  it("disables run when nothing is selected", () => {
    render(<AnalyzeTab selected={[]} analysis={analysis} summary={analyzedSummary} availableRadii={[250]} running={false} onChange={vi.fn()} onRun={vi.fn()} />);
    expect(screen.getByRole("button", { name: /run analysis/i })).toBeDisabled();
  });

  it("summarizes analyzed findings in plain language", () => {
    render(<AnalyzeTab selected={[home, office]} analysis={{ ...analysis, offenseCategory: "" }} summary={analyzedSummary} availableRadii={[250]} running={false} onChange={vi.fn()} onRun={vi.fn()} />);

    expect(screen.getByText("Findings summary")).toBeInTheDocument();
    expect(screen.getByText("Office has the highest reported incident exposure in the selected radius (142 reported incidents).")).toBeInTheDocument();
    expect(screen.getByText("Property / Theft is the largest reported incident type across the selected places.")).toBeInTheDocument();
    expect(screen.getByText("Person / Assault appears in the selected places; use Compare for side-by-side context.")).toBeInTheDocument();
    expect(screen.getByText(/reported incident patterns do not predict personal risk/i)).toBeInTheDocument();
    expect(screen.queryByText(/more likely to experience/i)).not.toBeInTheDocument();
  });

  it("prompts users to run analysis before showing findings", () => {
    render(<AnalyzeTab selected={[home]} analysis={analysis} summary={{ ...analyzedSummary, crime_summaries: [] }} availableRadii={[250]} running={false} onChange={vi.fn()} onRun={vi.fn()} />);

    expect(screen.getByText("Run analysis to summarize reported incident patterns for the selected places.")).toBeInTheDocument();
  });
});
