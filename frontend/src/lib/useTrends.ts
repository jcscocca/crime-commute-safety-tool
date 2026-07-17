import { useEffect, useRef, useState } from "react";

import { getTrends } from "../api/client";
import type { TrendsResponse } from "../types";

const DEBOUNCE_MS = 300;

/**
 * Debounced, abortable fetch of the monthly trend series for one MCPP. Mirrors
 * useIncidentPoints' mechanics: a ~300 ms trailing debounce on mcpp/layer/category
 * changes, an AbortController per request, and signal.aborted guards so a superseded
 * request never writes its result. mcpp === null clears state and holds off any fetch —
 * the section only renders under a non-null neighborhood, which the caller already nulls.
 */
export function useTrends(
  mcpp: string | null,
  layer: string,
  category: string | null,
): { data: TrendsResponse | null; loading: boolean; error: string | null } {
  const [data, setData] = useState<TrendsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }
    abortRef.current?.abort();
    if (mcpp === null) {
      setData(null);
      setError(null);
      setLoading(false);
      return undefined;
    }
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    timerRef.current = setTimeout(() => {
      getTrends({ mcpp, layer, category }, controller.signal)
        .then((response: TrendsResponse) => {
          if (controller.signal.aborted) return;
          setData(response);
          setError(null);
          setLoading(false);
        })
        .catch((cause: unknown) => {
          if (controller.signal.aborted) return;
          setError(cause instanceof Error ? cause.message : "trends failed");
          setData(null);
          setLoading(false);
        });
    }, DEBOUNCE_MS);
    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
      }
      controller.abort();
    };
  }, [mcpp, layer, category]);

  useEffect(() => () => abortRef.current?.abort(), []);

  return { data, loading, error };
}
