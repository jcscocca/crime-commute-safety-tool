import type { TemporalProfile } from "../types";

export type TravelWindow = {
  dayset: "weekdays" | "weekends" | "all";
  startHour: number; // 0–23 inclusive
  endHour: number; // 1–24 exclusive
};

export const DAYSET_DAYS: Record<TravelWindow["dayset"], number[]> = {
  weekdays: [0, 1, 2, 3, 4],
  weekends: [5, 6],
  all: [0, 1, 2, 3, 4, 5, 6],
};

export const DAYSET_LABELS: Record<TravelWindow["dayset"], string> = {
  weekdays: "Weekdays",
  weekends: "Weekends",
  all: "Every day",
};

export const DOW_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export const DEFAULT_TRAVEL_WINDOW: TravelWindow = { dayset: "weekdays", startHour: 16, endHour: 19 };

export function clampInt(value: string, min: number, max: number): number {
  const n = Math.trunc(Number(value));
  if (Number.isNaN(n)) return min;
  return Math.min(max, Math.max(min, n));
}

export function windowShare(
  temporal: TemporalProfile,
  window: TravelWindow,
): { count: number; share: number } {
  let count = 0;
  for (const d of DAYSET_DAYS[window.dayset]) {
    const row = temporal.hour_by_dow[d] ?? [];
    for (let h = window.startHour; h < window.endHour; h += 1) {
      count += row[h] ?? 0;
    }
  }
  const share = temporal.total_with_time > 0 ? count / temporal.total_with_time : 0;
  return { count, share };
}
