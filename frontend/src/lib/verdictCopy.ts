import type { NeighborhoodPlace } from "../types";

export type VerdictChip = { label: string; tone: "clear" | "muted" };
export type VerdictCopy = { headline: string; chip: VerdictChip };

const CLEAR: VerdictChip = { label: "✓ statistically clear", tone: "clear" };
const MUTED = (label: string): VerdictChip => ({ label, tone: "muted" });

// Plain-language verdict for one neighborhood place. The chip encodes statistical CLARITY
// (clear vs not), never a safety judgement — the product reports reported-incident context.
export function decisionHeadline(
  place: Pick<NeighborhoodPlace, "decision" | "place_label">,
): VerdictCopy {
  const label = place.place_label || "This place";
  switch (place.decision) {
    case "above_clear":
      return { headline: `${label} has more reported incidents than its surrounding beat.`, chip: CLEAR };
    case "below_clear":
      return { headline: `${label} has fewer reported incidents than its surrounding beat.`, chip: CLEAR };
    case "not_clear":
      return {
        headline: `${label} is about the same as its surrounding beat.`,
        chip: MUTED("~ not statistically clear"),
      };
    case "insufficient_data":
    case "model_warning":
      return {
        headline: `Not enough data to compare ${label} to its beat.`,
        chip: MUTED("too little data"),
      };
    case "baseline_unavailable":
      return {
        headline: `No neighborhood baseline available for ${label}.`,
        chip: MUTED("no baseline"),
      };
    default:
      return { headline: `${label} compared to its surrounding beat.`, chip: MUTED("—") };
  }
}
