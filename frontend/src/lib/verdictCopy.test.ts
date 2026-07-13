import { describe, expect, it } from "vitest";

import { decisionHeadline, aggregateHeadline } from "./verdictCopy";
import { incidentNoun } from "./layerCopy";
import type { BaselineEntry, NeighborhoodPlace } from "../types";

const at = (decision: string) =>
  decisionHeadline({ decision, place_label: "Home" } as never);

describe("decisionHeadline", () => {
  it("maps above_clear to a 'more' headline with a clear chip", () => {
    const v = at("above_clear");
    expect(v.headline).toBe("Home has more reported incidents than its surrounding area.");
    expect(v.chip).toEqual({ label: "✓ statistically clear", tone: "clear" });
  });

  it("maps below_clear to a 'fewer' headline with a clear chip", () => {
    const v = at("below_clear");
    expect(v.headline).toBe("Home has fewer reported incidents than its surrounding area.");
    expect(v.chip).toEqual({ label: "✓ statistically clear", tone: "clear" });
  });

  it("maps not_clear to an 'about the same' headline with a muted chip", () => {
    const v = at("not_clear");
    expect(v.headline).toBe("Home is about the same as its surrounding area.");
    expect(v.chip).toEqual({ label: "~ not statistically clear", tone: "muted" });
  });

  it("maps insufficient_data and model_warning to a 'not enough data' headline", () => {
    expect(at("insufficient_data").headline).toBe("Not enough data to compare Home to its surrounding area.");
    expect(at("model_warning").headline).toBe("Not enough data to compare Home to its surrounding area.");
    expect(at("insufficient_data").chip).toEqual({ label: "too little data", tone: "muted" });
    expect(at("model_warning").chip).toEqual({ label: "too little data", tone: "muted" });
  });

  it("maps baseline_too_small to a 'radius too large' explanation, not 'too little data'", () => {
    const v = decisionHeadline({
      decision: "insufficient_data",
      place_label: "Home",
      minimum_data_status: "baseline_too_small",
      radius_m: 1000,
    } as never);
    expect(v.headline).toBe(
      "Home's 1000 m radius covers nearly all of its surrounding beats — there is no area left to compare against. Try a smaller radius.",
    );
    expect(v.chip).toEqual({ label: "radius too large", tone: "muted" });
  });

  it("maps baseline_unavailable to a 'no baseline' headline", () => {
    const v = at("baseline_unavailable");
    expect(v.headline).toBe("No neighborhood baseline available for Home.");
    expect(v.chip).toEqual({ label: "no baseline", tone: "muted" });
  });

  it("falls back safely for an unknown decision", () => {
    const v = at("something_new");
    expect(v.headline).toBe("Home compared to its surrounding area.");
    expect(v.chip.tone).toBe("muted");
  });

  it("falls back to 'This place' when place_label is empty", () => {
    expect(
      decisionHeadline({ decision: "not_clear", place_label: "" } as never).headline,
    ).toBe("This place is about the same as its surrounding area.");
  });
});

const entry = (kind: BaselineEntry["kind"], label: string, relation: BaselineEntry["relation"]): BaselineEntry => ({
  kind, label, relation,
  area_km2: 1, baseline_incident_count: 10, baseline_rate: 0.02,
  rate_ratio: 1.4, ci_lower: 0.9, ci_upper: 2.2, adjusted_p_value: 0.2, method: "quasi_poisson",
});

const basePlace = (baselines: BaselineEntry[], overrides: Partial<NeighborhoodPlace> = {}): NeighborhoodPlace => ({
  place_id: "p1", place_label: "Cafe", beat: "C2", radius_m: 250,
  baseline_available: true, decision: "not_clear", place_incident_count: 12,
  category_breakdown: [], baselines, ...overrides,
});

describe("aggregateHeadline", () => {
  it("groups relations into one sentence in above/below/similar order", () => {
    const headline = aggregateHeadline(
      basePlace([
        entry("mcpp", "Capitol Hill", "similar"),
        entry("beat", "Beat C2", "similar"),
        entry("sector", "Sector C", "above"),
        entry("city", "Citywide", "above"),
      ]),
      incidentNoun("reported"),
    );
    expect(headline).toBe(
      "Cafe's reported incident rate is above its sector (C) and the citywide rate; similar to Capitol Hill and its beat (C2).",
    );
  });

  it("ignores insufficient entries in the sentence", () => {
    const headline = aggregateHeadline(
      basePlace([entry("city", "Citywide", "above"), entry("sector", "Sector C", "insufficient")]),
      incidentNoun("reported"),
    );
    expect(headline).toBe("Cafe's reported incident rate is above the citywide rate.");
  });

  it("explains the radius-too-large case", () => {
    const headline = aggregateHeadline(
      basePlace([], { minimum_data_status: "baseline_too_small", decision: "insufficient_data" }),
      incidentNoun("reported"),
    );
    expect(headline).toContain("smaller radius");
  });

  it("says when every comparison lacked data", () => {
    const headline = aggregateHeadline(
      basePlace([entry("city", "Citywide", "insufficient")], { decision: "insufficient_data" }),
      incidentNoun("reported"),
    );
    expect(headline).toBe("Not enough data to compare Cafe to its area baselines.");
  });

  it("says when no baseline geography resolved at all", () => {
    const headline = aggregateHeadline(
      basePlace([], { decision: "baseline_unavailable", baseline_available: false }),
      incidentNoun("reported"),
    );
    expect(headline).toBe("No area baseline available for Cafe.");
  });
});
