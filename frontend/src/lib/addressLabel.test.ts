// @vitest-environment node
import { describe, expect, it } from "vitest";

import { compactGeocodeLabel, formatIncidentAddress } from "./addressLabel";

describe("formatIncidentAddress", () => {
  it("collapses the same intersection regardless of cross-street order", () => {
    const a = formatIncidentAddress("PIKE ST / 3RD AVE");
    const b = formatIncidentAddress("3RD AVE / PIKE ST");
    expect(a).toBe(b);
    expect(a).toBe("3rd Ave & Pike St");
  });

  it("preserves directional prefixes and suffixes while collapsing order", () => {
    const a = formatIncidentAddress("S JACKSON ST / 12TH AVE S");
    const b = formatIncidentAddress("12TH AVE S / S JACKSON ST");
    expect(a).toBe(b);
    expect(a).toBe("12th Ave S & S Jackson St");
  });

  it("humanizes an anonymized block-face (XX -> 00)", () => {
    expect(formatIncidentAddress("14XX BLOCK OF 2ND AVE")).toBe("1400 block of 2nd Ave");
  });

  it("humanizes a plain block-face without XX or 'OF'", () => {
    expect(formatIncidentAddress("100 BLOCK MAIN ST")).toBe("100 block of Main St");
  });

  it("renders the redaction sentinel as withheld, not the raw token", () => {
    expect(formatIncidentAddress("REDACTED")).toBe("Address withheld");
  });

  it("treats blank/placeholder/unknown sentinels as unavailable", () => {
    expect(formatIncidentAddress(null)).toBe("Unavailable");
    expect(formatIncidentAddress("-")).toBe("Unavailable");
    expect(formatIncidentAddress("UNKNOWN")).toBe("Unavailable");
    expect(formatIncidentAddress("")).toBe("Unavailable");
  });

  it("title-cases a full street address it does not otherwise recognize", () => {
    expect(formatIncidentAddress("12018 NORTH PARK AVE N")).toBe("12018 North Park Ave N");
    expect(formatIncidentAddress("SEATTLE AREA")).toBe("Seattle Area");
  });
});

describe("compactGeocodeLabel", () => {
  it("merges the house number with the street and keeps the Seattle segment", () => {
    const raw =
      "4500, University Way Northeast, Greek Row, University Heights, University District, Seattle, King County, Washington, 98105, United States";
    expect(raw.length).toBeGreaterThan(120);
    expect(compactGeocodeLabel(raw)).toBe("4500 University Way Northeast, Seattle");
  });

  it("keeps a venue-first label as its own base plus Seattle", () => {
    const raw = "Space Needle, 400, Broad Street, Belltown, Seattle, King County, Washington, 98109, United States";
    expect(compactGeocodeLabel(raw)).toBe("Space Needle, Seattle");
  });

  it("falls back to the base segment when there is no Seattle segment", () => {
    const raw = "500, Main Street, Portland, Oregon, USA";
    expect(compactGeocodeLabel(raw)).toBe("500 Main Street");
  });

  it("is safe on an empty string", () => {
    expect(compactGeocodeLabel("")).toBe("");
  });

  it("still slices a >120-char base with no comma segments to 120 chars", () => {
    const raw = "a".repeat(150);
    const result = compactGeocodeLabel(raw);
    expect(result.length).toBe(120);
    expect(result).toBe(raw.slice(0, 120));
  });
});
