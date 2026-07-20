import { describe, expect, it } from "vitest";
import { incidentNoun, layerDisclosure } from "./layerCopy";

describe("incidentNoun arrests", () => {
  it("uses arrest nouns for the arrests layer", () => {
    expect(incidentNoun("arrests")).toEqual({ singular: "arrest", plural: "arrests", pluralCap: "Arrests" });
  });
});

describe("layerDisclosure", () => {
  it("has no disclosure for the reported layer", () => {
    expect(layerDisclosure("reported")).toBeNull();
  });

  it("returns the retired calls-layer disclosure verbatim", () => {
    expect(layerDisclosure("calls")).toBe(
      "911 calls are requests for service, not confirmed incidents. The same event can generate several calls, many are proactive officer activity, and a call does not mean a crime occurred. Counts below are call volume, not reported crime.",
    );
  });

  it("returns the retired arrests-layer disclosure verbatim", () => {
    expect(layerDisclosure("arrests")).toBe(
      "Arrests are enforcement activity, not reported incidents. An arrest is logged where the arrest was made — which may differ from where an offense occurred — and most reported crimes never result in one. Categories are a best-effort NIBRS crosswalk from the arrest offense.",
    );
  });
});
