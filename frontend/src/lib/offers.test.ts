import { describe, expect, it } from "vitest";

import { offerForPlaces, type SavedPlaceRef } from "./offers";
import type { AnalysisSettings } from "../types";

const analysis: AnalysisSettings = {
  startDate: "2026-01-01",
  endDate: "2026-07-19",
  radiusM: 250,
  offenseCategory: "",
  layer: "reported",
};

const home: SavedPlaceRef = { id: "p1", display_label: "Home" };
const work: SavedPlaceRef = { id: "p2", display_label: "Work" };

describe("offerForPlaces", () => {
  it("returns null for an empty add", () => {
    expect(offerForPlaces([], analysis, 0)).toBeNull();
  });

  it("offers a single-place pull with the place label, no compare chip when it's the only saved place", () => {
    const offer = offerForPlaces([home], analysis, 1);
    expect(offer).not.toBeNull();
    expect(offer!.text).toBe("Saved Home. Want me to pull what's on file nearby?");
    expect(offer!.chips.map((c) => c.label)).toEqual(["Pull reports near Home"]);
    expect(offer!.chips[0]).toMatchObject({
      command: "analyze_places",
      argsPatch: {},
      settingsPatch: {},
      args: {
        place_ids: ["p1"],
        radii_m: [250],
        analysis_start_date: "2026-01-01",
        analysis_end_date: "2026-07-19",
        layer: "reported",
      },
    });
    // No offense_category filter → the arg is omitted, not carried as null.
    expect(offer!.chips[0].args).not.toHaveProperty("offense_category");
  });

  it("adds a 'Compare with my places' chip when other saved places already exist", () => {
    const offer = offerForPlaces([work], analysis, 2);
    expect(offer!.chips.map((c) => c.label)).toEqual([
      "Pull reports near Work",
      "Compare with my places",
    ]);
    const compare = offer!.chips[1];
    expect(compare).toMatchObject({
      command: "compare_places",
      args: {
        radius_m: 250,
        analysis_start_date: "2026-01-01",
        analysis_end_date: "2026-07-19",
        layer: "reported",
      },
    });
    // place_ids is left for the caller to fill with the full saved set.
    expect(compare.args).not.toHaveProperty("place_ids");
  });

  it("offers a multi-place compare for a bulk import", () => {
    const offer = offerForPlaces([home, work], analysis, 2);
    expect(offer!.text).toBe("Saved 2 places. Want me to compare them?");
    expect(offer!.chips.map((c) => c.label)).toEqual(["Compare these 2 places"]);
    expect(offer!.chips[0]).toMatchObject({
      command: "compare_places",
      args: {
        place_ids: ["p1", "p2"],
        radius_m: 250,
        analysis_start_date: "2026-01-01",
        analysis_end_date: "2026-07-19",
        layer: "reported",
      },
    });
  });

  it("freezes the window args from the passed analysis, carrying an offense category when set", () => {
    const filtered: AnalysisSettings = {
      ...analysis,
      startDate: "2025-03-04",
      endDate: "2025-09-09",
      radiusM: 500,
      offenseCategory: "PROPERTY",
      layer: "calls",
    };
    const single = offerForPlaces([home], filtered, 1);
    expect(single!.chips[0].args).toMatchObject({
      radii_m: [500],
      analysis_start_date: "2025-03-04",
      analysis_end_date: "2025-09-09",
      layer: "calls",
      offense_category: "PROPERTY",
    });
    const multi = offerForPlaces([home, work], filtered, 2);
    expect(multi!.chips[0].args).toMatchObject({
      radius_m: 500,
      offense_category: "PROPERTY",
      layer: "calls",
    });
  });

  it("passes an empty analysis window through as null (not undefined)", () => {
    const emptyWindow: AnalysisSettings = { ...analysis, startDate: "", endDate: "" };
    const offer = offerForPlaces([home], emptyWindow, 1);
    expect(offer!.chips[0].args).toMatchObject({
      analysis_start_date: null,
      analysis_end_date: null,
    });
  });
});
