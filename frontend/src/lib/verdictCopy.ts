import type { NeighborhoodPlace } from "../types";
import { incidentNoun, type IncidentNoun } from "./layerCopy";

export type VerdictChip = { label: string; tone: "clear" | "muted" };
export type VerdictCopy = { headline: string; chip: VerdictChip };

const CLEAR: VerdictChip = { label: "✓ statistically clear", tone: "clear" };
const MUTED = (label: string): VerdictChip => ({ label, tone: "muted" });

// Plain-language verdict for one neighborhood place. The chip encodes statistical CLARITY
// (clear vs not), never a safety judgement — the product reports incident context. The noun
// adapts to the active layer (reported incidents vs 911 calls); defaults to reported. The
// baseline is the pooled "surrounding area" (every beat the radius touches), so the copy says
// "surrounding area", not "beat".
export function decisionHeadline(
  place: Pick<NeighborhoodPlace, "decision" | "place_label" | "minimum_data_status" | "radius_m">,
  noun: IncidentNoun = incidentNoun("reported"),
): VerdictCopy {
  const label = place.place_label || "This place";
  switch (place.decision) {
    case "above_clear":
      return { headline: `${label} has more ${noun.plural} than its surrounding area.`, chip: CLEAR };
    case "below_clear":
      return { headline: `${label} has fewer ${noun.plural} than its surrounding area.`, chip: CLEAR };
    case "not_clear":
      return {
        headline: `${label} is about the same as its surrounding area.`,
        chip: MUTED("~ not statistically clear"),
      };
    case "insufficient_data":
    case "model_warning":
      // Distinguish "your radius swallowed the whole surrounding area" (a geometry problem the
      // user can fix by shrinking the radius) from a genuine shortage of incident data.
      if (place.minimum_data_status === "baseline_too_small") {
        return {
          headline: `${label}'s ${place.radius_m} m radius covers nearly all of its surrounding beats — there is no area left to compare against. Try a smaller radius.`,
          chip: MUTED("radius too large"),
        };
      }
      return {
        headline: `Not enough data to compare ${label} to its surrounding area.`,
        chip: MUTED("too little data"),
      };
    case "baseline_unavailable":
      return {
        headline: `No neighborhood baseline available for ${label}.`,
        chip: MUTED("no baseline"),
      };
    default:
      return { headline: `${label} compared to its surrounding area.`, chip: MUTED("—") };
  }
}
