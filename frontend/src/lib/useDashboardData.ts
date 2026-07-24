import { useEffect, useMemo, useState } from "react";

import {
  createSession,
  getDashboardFreshness,
  getDashboardSummary,
  getInputModes,
} from "../api/client";
import type { DashboardFreshness, DashboardSummary, Place } from "../types";

const DEFAULT_EXPORT = "/exports/tableau/place-summary.csv";

export interface DashboardData {
  sessionReady: boolean;
  summary: DashboardSummary | null;
  freshness: DashboardFreshness | null;
  freshnessLoaded: boolean;
  personalUploadsEnabled: boolean;
  error: string;
  setError: (message: string) => void;
  refresh: () => Promise<void>;
  refreshWithFallback: (fallbackMessage: string) => Promise<void>;
  places: Place[];
  availableRadii: number[];
  exportHref: string;
}

/**
 * Owns the core dashboard data layer: bootstraps the session, loads the dashboard
 * summary, the crime-data freshness window, and the available input modes, and exposes
 * the `refresh`/`refreshWithFallback` helpers plus the derived places/radii/export-href
 * the rest of the workspace reads.
 */
export function useDashboardData(): DashboardData {
  const [sessionReady, setSessionReady] = useState(false);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [freshness, setFreshness] = useState<DashboardFreshness | null>(null);
  const [freshnessLoaded, setFreshnessLoaded] = useState(false);
  const [personalUploadsEnabled, setPersonalUploadsEnabled] = useState(false);
  const [error, setError] = useState("");

  const refresh = async () => {
    setSummary(await getDashboardSummary());
  };
  const refreshWithFallback = async (fallbackMessage: string) => {
    try {
      await refresh();
    } catch {
      setError(fallbackMessage);
    }
  };

  useEffect(() => {
    let isMounted = true;
    setError("");
    createSession()
      .then(() => {
        if (!isMounted) return;
        setSessionReady(true);
        void getDashboardSummary()
          .then((value) => {
            if (!isMounted) return;
            setError("");
            setSummary(value);
          })
          .catch(() => {
            if (isMounted) setError("Unable to load dashboard data. Try again shortly.");
          });
        void getDashboardFreshness()
          .then((value) => {
            if (isMounted) setFreshness(value);
          })
          .catch(() => {
            if (isMounted) setFreshness(null);
          })
          .finally(() => {
            if (isMounted) setFreshnessLoaded(true);
          });
      })
      .catch(() => {
        if (isMounted) {
          setFreshnessLoaded(true);
          setError("Unable to start a dashboard session. Try again shortly.");
        }
      });
    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    getInputModes()
      .then((data) => {
        if (active) setPersonalUploadsEnabled(data.modes.some((mode) => mode.id === "personal_timeline"));
      })
      .catch(() => {
        if (active) setPersonalUploadsEnabled(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const places: Place[] = useMemo(() => summary?.places ?? [], [summary]);
  const availableRadii = summary?.analysis.available_radii_m ?? [];
  const exportHref = summary?.exports.tableau_place_summary_csv || DEFAULT_EXPORT;

  return {
    sessionReady,
    summary,
    freshness,
    freshnessLoaded,
    personalUploadsEnabled,
    error,
    setError,
    refresh,
    refreshWithFallback,
    places,
    availableRadii,
    exportHref,
  };
}
