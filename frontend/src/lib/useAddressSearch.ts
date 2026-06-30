import { useState } from "react";

import type { GeocodeResult } from "../types";

export type AddressSearchStatus = "idle" | "loading" | "done" | "empty" | "error";

export const SEARCH_EMPTY_MSG = "No matches. Drop a pin on the map instead.";
export const SEARCH_ERROR_MSG = "Search is unavailable. Drop a pin on the map instead.";

export interface AddressSearch {
  query: string;
  setQuery: (value: string) => void;
  status: AddressSearchStatus;
  results: GeocodeResult[];
  runSearch: () => Promise<void>;
}

/**
 * Shared address-search state machine for the geocode box used by both the Places map
 * search (PlaceSearch) and the Routes endpoint search (RoutesTab). Owns the query, the
 * trimmed geocode call, and the loading/done/empty/error status; callers render the input and
 * the results however they need (a clickable list for Places, endpoint options for Routes).
 */
export function useAddressSearch(
  search: (query: string, signal?: AbortSignal) => Promise<GeocodeResult[]>,
): AddressSearch {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<GeocodeResult[]>([]);
  const [status, setStatus] = useState<AddressSearchStatus>("idle");

  async function runSearch() {
    const trimmed = query.trim();
    if (!trimmed) {
      return;
    }
    setStatus("loading");
    try {
      const found = await search(trimmed);
      setResults(found);
      setStatus(found.length === 0 ? "empty" : "done");
    } catch {
      setResults([]);
      setStatus("error");
    }
  }

  return { query, setQuery, status, results, runSearch };
}
