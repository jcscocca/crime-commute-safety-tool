import { useEffect, useRef, useState } from "react";

import type { Place } from "../types";

export type ComparePoint = { latitude: number; longitude: number; label: string };

export const MAX_COMPARE_POINTS = 10;

export interface CompareSet {
  points: ComparePoint[];
  add: (point: ComparePoint) => void;
  removeAt: (index: number) => void;
}

function keyOf(p: ComparePoint): string {
  return `${p.latitude.toFixed(4)},${p.longitude.toFixed(4)}`;
}

function dedupeCap(points: ComparePoint[]): ComparePoint[] {
  const seen = new Set<string>();
  const out: ComparePoint[] = [];
  for (const p of points) {
    const k = keyOf(p);
    if (seen.has(k)) continue;
    seen.add(k);
    out.push(p);
    if (out.length >= MAX_COMPARE_POINTS) break;
  }
  return out;
}

/** Convert selected places to compare points, dropping null coords, de-duped and capped. */
export function pointsFromPlaces(places: Place[]): ComparePoint[] {
  const points: ComparePoint[] = [];
  for (const place of places) {
    if (place.latitude == null || place.longitude == null) continue;
    points.push({ latitude: place.latitude, longitude: place.longitude, label: place.display_label });
  }
  return dedupeCap(points);
}

/**
 * Owns the editable, ephemeral compare set. Seeds SYNCHRONOUSLY from the current selection
 * (so the first render already has the points the shared-view auto-run reads), and re-seeds
 * when the selection changes — but only until the user's first manual edit, after which the
 * set is theirs (decoupled scratchpad).
 */
export function useCompareSet(seed: Place[]): CompareSet {
  const editedRef = useRef(false);
  const [points, setPoints] = useState<ComparePoint[]>(() => pointsFromPlaces(seed));

  useEffect(() => {
    if (editedRef.current) return;
    setPoints(pointsFromPlaces(seed));
  }, [seed]);

  function add(point: ComparePoint) {
    editedRef.current = true;
    setPoints((cur) => dedupeCap([...cur, point]));
  }

  function removeAt(index: number) {
    editedRef.current = true;
    setPoints((cur) => cur.filter((_, i) => i !== index));
  }

  return { points, add, removeAt };
}
