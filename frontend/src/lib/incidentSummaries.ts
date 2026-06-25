import type { DashboardSummary } from "../types";

export function incidentCountForPlace(
  summary: DashboardSummary | null,
  placeId: string,
  radiusM: number,
): number | null {
  if (!summary) {
    return null;
  }
  const matches = summary.crime_summaries.filter(
    (entry) => entry.place_cluster_id === placeId && entry.radius_m === radiusM,
  );
  if (matches.length === 0) {
    return null;
  }
  return matches.reduce((total, entry) => total + entry.incident_count, 0);
}
