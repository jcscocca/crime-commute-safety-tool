// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CompareTab } from "./CompareTab";
import type { GeocodingProvider } from "../lib/geocoding";
import type { ComparePoint } from "../lib/useCompareSet";
import type { AnalysisSettings, SiteComparison, SiteComparisonOption, SitePairwiseResult, SiteDecisionClass } from "../types";

const provider: GeocodingProvider = { search: vi.fn().mockResolvedValue([]) };
const analysis: AnalysisSettings = { startDate: "2026-01-01", endDate: "2026-06-24", radiusM: 250, offenseCategory: "PROPERTY", layer: "reported" };
const setOf = (...labels: string[]): ComparePoint[] => labels.map((l, i) => ({ latitude: 47.6 + i * 0.01, longitude: -122.3 - i * 0.01, label: l }));

function opt(id: string, label: string, count: number, rate: number): SiteComparisonOption {
  return { id, label, geometry_type: "place_buffer", radius_m: 250, incident_count: count, exposure: 1, exposure_unit: "square_km_days", incident_rate: rate };
}
function pair(a: string, b: string, decision: SiteDecisionClass, winner: string | null): SitePairwiseResult {
  return { id: `${a}-${b}`, option_a_id: a, option_a_label: a, option_b_id: b, option_b_label: b, winner_option_id: winner, winner_label: winner, decision_class: decision, method: "quasipoisson", incident_count_a: 0, incident_count_b: 0, exposure_a: 1, exposure_b: 1, exposure_unit: "square_km_days", rate_a: 0, rate_b: 0, rate_ratio: 0.38, ci_lower: 0.2, ci_upper: 0.71, p_value: 0.001, adjusted_p_value: 0.004, overdispersion_phi: 1.1, overdispersion_status: "ok", minimum_data_status: "met", caveat_text: "" };
}
const clearSweep: SiteComparison = {
  id: "c1", comparison_type: "site", geometry_type: "place_buffer", radius_m: 250, analysis_start_date: "2026-01-01", analysis_end_date: "2026-06-24",
  offense_category: null, offense_subcategory: null, nibrs_group: null, created_at: "2026-07-03",
  overview: { label: "Overview", decision_class: "statistically_lower", recommendation_option_id: "a", recommendation_label: "Pike", summary_text: "", caveat_text: "cav", options: [opt("a", "Pike", 12, 3.9), opt("b", "Bell", 44, 14.3)] },
  analytical: { label: "Analytical", source_dataset: "seattle_spd_crime", exposure_unit: "square_km_days", full_caveat_text: "full cav", options: [opt("a", "Pike", 12, 3.9), opt("b", "Bell", 44, 14.3)], pairwise_results: [pair("a", "b", "statistically_lower", "a")] },
};

afterEach(cleanup);

const base = { provider, onAddPoint: vi.fn(), onRemovePoint: vi.fn(), analysis, running: false, onRun: vi.fn() };

describe("CompareTab (editable set)", () => {
  it("empty set: prompts to add addresses and shows the add input", () => {
    render(<CompareTab {...base} set={[]} comparison={null} />);
    expect(screen.getByText(/add at least two addresses/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/add an address/i)).toBeInTheDocument();
  });

  it("one address: nudges to add one more; compare disabled", () => {
    render(<CompareTab {...base} set={setOf("Pike")} comparison={null} />);
    expect(screen.getByText(/add one more address/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /compare addresses/i })).toBeDisabled();
  });

  it("two addresses, not yet run: lists them with remove, invites compare, fires onRun", () => {
    const onRemovePoint = vi.fn();
    const onRun = vi.fn();
    render(<CompareTab {...base} onRemovePoint={onRemovePoint} onRun={onRun} set={setOf("Pike", "Bell")} comparison={null} />);
    const rows = screen.getByLabelText(/addresses to compare/i);
    expect(within(rows).getByText("Pike")).toBeInTheDocument();
    expect(screen.getByText(/rank their reported incident rates/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /remove Pike/i }));
    expect(onRemovePoint).toHaveBeenCalledWith(0);
    fireEvent.click(screen.getByRole("button", { name: /compare addresses/i }));
    expect(onRun).toHaveBeenCalled();
  });

  it("with a comparison: renders the slice-A ranked verdict", () => {
    render(<CompareTab {...base} set={setOf("Pike", "Bell")} comparison={clearSweep} />);
    expect(screen.getByText(/statistically lower than every other/i)).toBeInTheDocument();
    expect(within(screen.getByTestId("compare-ranked")).getByText("Pike")).toBeInTheDocument();
  });

  it("the dynamic verdict region never emits safety-ranking vocabulary", () => {
    render(<CompareTab {...base} set={setOf("Pike", "Bell")} comparison={clearSweep} />);
    const dynamic = `${screen.getByTestId("compare-callout").textContent ?? ""} ${screen.getByTestId("compare-ranked").textContent ?? ""} ${screen.getByTestId("compare-plot").textContent ?? ""}`.toLowerCase();
    for (const banned of ["safe", "unsafe", "safety", "danger", "dangerous", "risk", "risky"]) {
      expect(dynamic).not.toContain(banned);
    }
  });
});
