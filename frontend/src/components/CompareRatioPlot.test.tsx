// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { CompareRatioPlot } from "./CompareRatioPlot";
import type { CompareVerdictRow } from "../lib/compareVerdict";

function row(label: string, rel: CompareVerdictRow["relationship"], mult: number | null, lo: number | null, hi: number | null, rank: number): CompareVerdictRow {
  return { rank, optionId: label, label, incidentCount: 10, rate: mult ?? 1, barFraction: 0.5, multipleOfLowest: mult, plotCiLow: lo, plotCiHigh: hi, relationship: rel, pairwise: null };
}
const rows: CompareVerdictRow[] = [
  row("Pike", "lowest", null, null, null, 1),
  row("Bell", "higher", 2.6, 1.4, 4.9, 2),
  row("Yesler", "higher", 3.7, 2.0, 6.8, 3),
];

afterEach(cleanup);

describe("CompareRatioPlot", () => {
  it("renders a reference and a marked row per non-lowest address", () => {
    render(<CompareRatioPlot rows={rows} />);
    const plot = screen.getByTestId("compare-plot");
    expect(within(plot).getByText("Bell")).toBeInTheDocument();
    expect(within(plot).getByText("Yesler")).toBeInTheDocument();
    expect(within(plot).getByText("Pike")).toBeInTheDocument();
    expect(within(plot).getByText(/same rate/i)).toBeInTheDocument();
  });

  it("draws no interval bar for a limited-data row (dot only)", () => {
    const limitedRows: CompareVerdictRow[] = [
      row("Pike", "lowest", null, null, null, 1),
      row("Zed", "limited", 2.3, 1.2, 4.4, 2),
    ];
    render(<CompareRatioPlot rows={limitedRows} />);
    expect(screen.getByTestId("compare-plot").querySelectorAll(".mc-plot-row .bar")).toHaveLength(0);
  });

  it("carries the raw-bar / corrected-label honesty footnote", () => {
    render(<CompareRatioPlot rows={rows} />);
    expect(within(screen.getByTestId("compare-plot")).getByText(/label is the corrected verdict/i)).toBeInTheDocument();
  });

  it("never emits safety-ranking vocabulary", () => {
    render(<CompareRatioPlot rows={rows} />);
    const text = (screen.getByTestId("compare-plot").textContent ?? "").toLowerCase();
    for (const banned of ["safe", "unsafe", "safety", "danger", "dangerous", "risk", "risky"]) {
      expect(text).not.toContain(banned);
    }
  });
});
