import type { AnalysisSettings } from "../types";
import type { FollowupChip } from "./followupChips";

/** Callers pass full Place objects; coords let selectPlaceIds link a just-saved place to
 * its pre-existing ad-hoc list entry (same coordinate key) instead of dedup-adding. */
export type SavedPlaceRef = { id: string; display_label: string; latitude?: number | null; longitude?: number | null };

/** Deterministic post-add offer. No LLM — must work in degraded mode. */
export function offerForPlaces(
  saved: SavedPlaceRef[],
  analysis: AnalysisSettings,
  savedIdCount: number,
): { text: string; chips: FollowupChip[] } | null {
  if (saved.length === 0) return null;
  const windowArgs = {
    analysis_start_date: analysis.startDate || null,
    analysis_end_date: analysis.endDate || null,
    layer: analysis.layer,
    ...(analysis.offenseCategory ? { offense_category: analysis.offenseCategory } : {}),
  };
  const ids = saved.map((p) => p.id);
  if (saved.length === 1) {
    const label = saved[0].display_label;
    const chips: FollowupChip[] = [
      {
        label: `Pull reports near ${label}`,
        command: "analyze_places",
        argsPatch: {},
        settingsPatch: {},
        args: { place_ids: ids, radii_m: [analysis.radiusM], ...windowArgs },
      },
    ];
    if (savedIdCount > 1) {
      chips.push({
        label: "Compare with my places",
        command: "compare_places",
        argsPatch: {},
        settingsPatch: {},
        args: { radius_m: analysis.radiusM, ...windowArgs }, // place_ids filled by the caller (all saved)
      });
    }
    return { text: `Saved ${label}. Want me to pull what's on file nearby?`, chips };
  }
  return {
    text: `Saved ${saved.length} places. Want me to compare them?`,
    chips: [
      {
        label: `Compare these ${saved.length} places`,
        command: "compare_places",
        argsPatch: {},
        settingsPatch: {},
        args: { place_ids: ids, radius_m: analysis.radiusM, ...windowArgs },
      },
    ],
  };
}
