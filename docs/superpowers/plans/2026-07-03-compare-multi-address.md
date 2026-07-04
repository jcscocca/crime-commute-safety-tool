# Compare-first Flagship — Slice B + Interval Plot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One PR, two ordered parts. Part 1: give the Compare tab an editable, ephemeral compare set (add an address via the reused search, remove a row, re-run) driving the slice-A verdict, decoupled from saved Places. Part 2: add an honest rate-ratio interval plot to the verdict.

**Architecture:** Frontend only, no backend. Part 1 adds a `useCompareSet` hook (owns the editable `points` set, seeded synchronously from the current selection, feeds `useCompare.points`) and a `CompareAddressInput` (wraps the existing `useAddressSearch`); `CompareTab` renders the editor and `MapWorkspace` wires it. Part 2 extends the pure `compareVerdict.ts` to carry each row's plotted multiple + an interval inverted from the pairwise ratio CI, and a `CompareRatioPlot` renders dots + intervals against a "same rate" line.

**Tech Stack:** React + TypeScript + Vite, Vitest (`vitest run --environment jsdom`), `tsc -b` type-check. Run from `frontend/`.

**Working context:** Worktree `/Users/jscocca/Repos/Crime Commute Safety Tool/.worktrees/compare-multi-address`, branch `jcscocca/claude/compare-multi-address` (spec committed at `4d264e4`, off origin/main `19c0afd`). Spec: `docs/superpowers/specs/2026-07-03-compare-multi-address-design.md`. Single PR, gated on `make test-all`.

**Load-bearing facts from the current code (verified):**
- `useCompare` (`frontend/src/lib/useCompare.ts`) takes `points?: {latitude;longitude;label}[]`; `runCompare` uses `points` when `points.length >= 2`, else `place_ids`. Feed the editable set as `points`.
- `useAddressSearch(search)` returns `{ query, setQuery, status, results, recent, runSearch, rememberPlace }`; `GeocodeResult = {label, latitude, longitude, source}`; the Seattle-bbox guard lives in the provider (`createBackendProvider().search` in `geocoding.ts`), so wrapping `provider.search` inherits it. `PlaceSearch.tsx` is the reuse pattern (on select: `rememberPlace(r)` then hand the raw result up).
- `MapWorkspace` computes `selected: Place[]` (lines ~169–184) from `sharedPoints` (synth `shared-*` places) or `data.places` filtered by `selectedIds`; `useCompare` is called at line ~57 with `points: sharedPoints ?? undefined`; a mount effect (lines ~61–66) auto-runs compare for a `?view=` compare link; `buildShareUrl("compare")` (lines ~186–199) serializes `sharedPoints ?? selected.map(...)`. **`sharedPoints` is initialized synchronously** in `useState` (line ~35) from the decoded view — that's why the auto-run works, and why the compare set must also seed synchronously (Task 1/4).
- `compareVerdict.ts` `CompareVerdictRow` already has `multipleOfLowest` and `pairwise`; `SitePairwiseResult` has `rate_ratio`, `ci_lower`, `ci_upper`, `decision_class`. The engine's candidate is the lowest-rate option, so `rate_ratio = lowest/other ≤ 1`.
- `savedView.ts` `ViewPoint = {latitude;longitude;label}` and `encodeView`/`decodeView` are tab-agnostic on points — an N-point compare set round-trips through `buildShareUrl("compare")` unchanged.
- No map rendering of the compare set exists today (MapCanvas only gets `data.places` + `selectedIds`) — Part 1's set stays map-free, matching current behavior.

**Product invariant:** the verdict copy is slice A's (unchanged); Part 2's plot uses a neutral palette only (no red/green) and its text labels are brought under the slice-A banned-word guard.

---

## PART 1 — editable compare set

## Task 1: `useCompareSet` hook

**Files:**
- Create: `frontend/src/lib/useCompareSet.ts`
- Test: `frontend/src/lib/useCompareSet.test.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/lib/useCompareSet.test.ts`:

```ts
// @vitest-environment jsdom
import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useCompareSet, pointsFromPlaces, MAX_COMPARE_POINTS } from "./useCompareSet";
import type { Place } from "../types";

function place(id: string, label: string, lat: number, lon: number): Place {
  return { id, display_label: label, latitude: lat, longitude: lon, visit_count: 0, total_dwell_minutes: null, inferred_place_type: "manual_place", sensitivity_class: "normal" };
}
const A = place("a", "Pike", 47.61, -122.33);
const B = place("b", "Bell", 47.62, -122.34);
const C = place("c", "Yesler", 47.60, -122.32);

describe("pointsFromPlaces", () => {
  it("converts places to points and drops null coords", () => {
    const withNull = { ...A, latitude: null };
    expect(pointsFromPlaces([A, withNull])).toEqual([{ latitude: 47.61, longitude: -122.33, label: "Pike" }]);
  });
  it("de-dupes by rounded coordinate and caps at MAX", () => {
    const dupe = place("a2", "Pike again", 47.61004, -122.33004); // rounds to same 4dp
    expect(pointsFromPlaces([A, dupe])).toHaveLength(1);
    const many = Array.from({ length: 15 }, (_, i) => place(`p${i}`, `P${i}`, 47.6 + i * 0.01, -122.3 - i * 0.01));
    expect(pointsFromPlaces(many)).toHaveLength(MAX_COMPARE_POINTS);
  });
});

describe("useCompareSet", () => {
  it("seeds synchronously from the initial selection (first render, not via effect)", () => {
    const { result } = renderHook(({ seed }) => useCompareSet(seed), { initialProps: { seed: [A, B] } });
    expect(result.current.points.map((p) => p.label)).toEqual(["Pike", "Bell"]);
  });

  it("re-seeds when the selection changes, until the user edits", () => {
    const { result, rerender } = renderHook(({ seed }) => useCompareSet(seed), { initialProps: { seed: [A, B] } });
    rerender({ seed: [A, B, C] });
    expect(result.current.points).toHaveLength(3);
    act(() => result.current.removeAt(0)); // user edit -> decouple
    rerender({ seed: [A, B] });
    expect(result.current.points.map((p) => p.label)).toEqual(["Bell", "Yesler"]); // stayed edited, no reseed
  });

  it("add appends, de-dupes, and caps at MAX", () => {
    const { result } = renderHook(({ seed }) => useCompareSet(seed), { initialProps: { seed: [A] } });
    act(() => result.current.add({ latitude: 47.62, longitude: -122.34, label: "Bell" }));
    expect(result.current.points).toHaveLength(2);
    act(() => result.current.add({ latitude: 47.62, longitude: -122.34, label: "Bell dupe" }));
    expect(result.current.points).toHaveLength(2); // de-duped
  });

  it("removeAt drops the row at the index", () => {
    const { result } = renderHook(({ seed }) => useCompareSet(seed), { initialProps: { seed: [A, B, C] } });
    act(() => result.current.removeAt(1));
    expect(result.current.points.map((p) => p.label)).toEqual(["Pike", "Yesler"]);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npx vitest run src/lib/useCompareSet.test.ts --environment jsdom`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `useCompareSet.ts`**

Create `frontend/src/lib/useCompareSet.ts`:

```ts
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd frontend && npx vitest run src/lib/useCompareSet.test.ts --environment jsdom`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/useCompareSet.ts frontend/src/lib/useCompareSet.test.ts
git commit -m "feat(compare): editable compare-set hook (seed / add / remove / cap / dedup)"
```

---

## Task 2: `CompareAddressInput` component

**Files:**
- Create: `frontend/src/components/CompareAddressInput.tsx`
- Test: `frontend/src/components/CompareAddressInput.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/CompareAddressInput.test.tsx`:

```tsx
// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CompareAddressInput } from "./CompareAddressInput";
import type { GeocodingProvider } from "../lib/geocoding";
import type { GeocodeResult } from "../types";

function providerReturning(results: GeocodeResult[]): GeocodingProvider {
  return { search: vi.fn().mockResolvedValue(results) };
}
const pike: GeocodeResult = { label: "1420 Pike St", latitude: 47.61, longitude: -122.33, source: "test" };

afterEach(cleanup);

describe("CompareAddressInput", () => {
  it("adds the selected search result and clears the query", async () => {
    const onAdd = vi.fn();
    render(<CompareAddressInput provider={providerReturning([pike])} onAdd={onAdd} disabled={false} />);
    fireEvent.change(screen.getByLabelText(/add an address/i), { target: { value: "pike" } });
    fireEvent.submit(screen.getByRole("search"));
    const hit = await screen.findByText("1420 Pike St");
    fireEvent.click(hit);
    expect(onAdd).toHaveBeenCalledWith({ latitude: 47.61, longitude: -122.33, label: "1420 Pike St" });
  });

  it("shows the empty-state message when no matches", async () => {
    render(<CompareAddressInput provider={providerReturning([])} onAdd={vi.fn()} disabled={false} />);
    fireEvent.change(screen.getByLabelText(/add an address/i), { target: { value: "nowhere" } });
    fireEvent.submit(screen.getByRole("search"));
    await waitFor(() => expect(screen.getByText(/no matches/i)).toBeInTheDocument());
  });

  it("disables the input at the max", () => {
    render(<CompareAddressInput provider={providerReturning([pike])} onAdd={vi.fn()} disabled={true} />);
    expect(screen.getByLabelText(/add an address/i)).toBeDisabled();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npx vitest run src/components/CompareAddressInput.test.tsx --environment jsdom`
Expected: FAIL — component not found.

- [ ] **Step 3: Implement `CompareAddressInput.tsx`**

Create `frontend/src/components/CompareAddressInput.tsx` (mirrors `PlaceSearch.tsx`; on select it maps the `GeocodeResult` to a `ComparePoint` and calls `onAdd`, then clears the query):

```tsx
import { type FormEvent } from "react";

import { useAddressSearch, SEARCH_EMPTY_MSG, SEARCH_ERROR_MSG } from "../lib/useAddressSearch";
import type { GeocodingProvider } from "../lib/geocoding";
import type { ComparePoint } from "../lib/useCompareSet";
import type { GeocodeResult } from "../types";

type Props = {
  provider: GeocodingProvider;
  onAdd: (point: ComparePoint) => void;
  disabled: boolean;
};

export function CompareAddressInput({ provider, onAdd, disabled }: Props) {
  const { query, setQuery, status, results, runSearch, rememberPlace } = useAddressSearch(provider.search);

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!disabled) void runSearch();
  }

  function handleSelect(result: GeocodeResult) {
    rememberPlace(result);
    onAdd({ latitude: result.latitude, longitude: result.longitude, label: result.label });
    setQuery("");
  }

  return (
    <div className="mc-search-wrap">
      <form className="mc-search mc-search--sheet" onSubmit={onSubmit} role="search">
        <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" />
        </svg>
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={disabled ? "10 addresses max" : "Add an address to compare"}
          aria-label="Add an address to compare"
          disabled={disabled}
        />
        <button type="submit" className="mc-search-go" disabled={disabled}>Add</button>
      </form>
      {status === "error" ? <p className="mc-search-msg" role="alert">{SEARCH_ERROR_MSG}</p> : null}
      {status === "empty" ? <p className="mc-search-msg">{SEARCH_EMPTY_MSG}</p> : null}
      {!disabled && results.length > 0 ? (
        <ul className="mc-results" aria-label="Address results">
          {results.map((result) => (
            <li key={`${result.latitude},${result.longitude}`}>
              <button type="button" onClick={() => handleSelect(result)}>
                <span className="mc-result-label">{result.label}</span>
                <span className="mc-result-coord">{result.latitude.toFixed(4)}, {result.longitude.toFixed(4)}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
```

(If `GeocodingProvider`'s exact shape differs, read `frontend/src/lib/geocoding.ts` — it exports `GeocodingProvider` with a `search(query, signal?)` method and `createBackendProvider()`. Use the type as declared.)

- [ ] **Step 4: Run to verify it passes**

Run: `cd frontend && npx vitest run src/components/CompareAddressInput.test.tsx --environment jsdom`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/CompareAddressInput.tsx frontend/src/components/CompareAddressInput.test.tsx
git commit -m "feat(compare): address-search add control for the compare set"
```

---

## Task 3: `CompareTab` — render the editor (Part 1)

**Files:**
- Modify: `frontend/src/components/CompareTab.tsx`
- Modify: `frontend/src/components/CompareTab.test.tsx`
- Modify: `frontend/src/styles/mapWorkspace.css`

- [ ] **Step 1: Rewrite `CompareTab.tsx`**

The tab now drives off the editable `set` (points) rather than `selected`. Replace the entire file:

```tsx
import { toCompareVerdict } from "../lib/compareVerdict";
import { incidentNoun } from "../lib/layerCopy";
import type { GeocodingProvider } from "../lib/geocoding";
import type { ComparePoint } from "../lib/useCompareSet";
import { MAX_COMPARE_POINTS } from "../lib/useCompareSet";
import type { AnalysisSettings, SiteComparison } from "../types";
import { CompareAddressInput } from "./CompareAddressInput";
import { CompareRankedList } from "./CompareRankedList";
import { CompareVerdict } from "./CompareVerdict";
import { MethodsAppendix } from "./MethodsAppendix";

type Props = {
  set: ComparePoint[];
  provider: GeocodingProvider;
  onAddPoint: (point: ComparePoint) => void;
  onRemovePoint: (index: number) => void;
  analysis: AnalysisSettings;
  comparison: SiteComparison | null;
  running: boolean;
  onRun: () => void;
  onCopyLink?: () => string | null;
};

const REVISED_CAVEAT =
  "Reported incident context, not a personal risk prediction. Results use reported Seattle incident data, which can be incomplete, delayed, corrected, or geographically generalized.";

export function CompareTab({ set, provider, onAddPoint, onRemovePoint, analysis, comparison, running, onRun, onCopyLink }: Props) {
  const noun = incidentNoun(analysis.layer);
  const canRun = set.length >= 2 && !running;
  const verdict = comparison ? toCompareVerdict(comparison) : null;

  return (
    <div className="mc-panel is-active" role="tabpanel" aria-label="Compare">
      <div className="mc-panel-head"><h4>Compare addresses</h4></div>

      <div className="mc-cmpset">
        <div className="mc-cmpset-head"><span className="mc-label">Addresses to compare · {set.length} of {MAX_COMPARE_POINTS}</span></div>
        <CompareAddressInput provider={provider} onAdd={onAddPoint} disabled={set.length >= MAX_COMPARE_POINTS} />
        {set.length === 0 ? (
          <p className="mc-empty-list">Add at least two addresses to compare {noun.singular} context.</p>
        ) : (
          <ul className="mc-cmpset-rows" aria-label="Addresses to compare">
            {set.map((point, index) => (
              <li key={`${point.latitude},${point.longitude}`} className="mc-cmpset-row">
                <span className="idx">{index + 1}</span>
                <span className="lbl">{point.label}</span>
                <button type="button" className="rm" aria-label={`Remove ${point.label}`} onClick={() => onRemovePoint(index)}>✕</button>
              </li>
            ))}
          </ul>
        )}
        {set.length === 1 ? <p className="mc-search-msg">Add one more address to compare.</p> : null}
      </div>

      {onCopyLink && comparison && (
        <button type="button" className="mc-link-copy" onClick={async () => { const url = onCopyLink(); if (url) await navigator.clipboard.writeText(url); }}>
          Copy link to this view
        </button>
      )}

      {verdict ? (
        <>
          <CompareVerdict callout={verdict.callout} noun={noun} />
          <p className="mc-ranked-title">Ranked by {noun.singular} rate — lowest first</p>
          <CompareRankedList rows={verdict.rows} noun={noun} />
        </>
      ) : set.length >= 2 ? (
        <p className="mc-empty-list">Compare these {set.length} addresses to rank their {noun.singular} rates.</p>
      ) : null}

      <div className="mc-caveat">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="12" cy="12" r="9" /><path d="M12 8h.01M11 12h1v4h1" /></svg>
        {REVISED_CAVEAT}
      </div>

      <MethodsAppendix />

      <div className="mc-compare-actions">
        <span className="note">{set.length} address{set.length === 1 ? "" : "es"} · {analysis.radiusM} m</span>
        <button type="button" className="mc-cta" disabled={!canRun} onClick={onRun}>{running ? "Comparing…" : "Compare addresses"}</button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Add CSS**

Append to `frontend/src/styles/mapWorkspace.css`:

```css
.mc-cmpset{display:grid;gap:9px;margin:0 0 14px;}
.mc-cmpset-head{display:flex;align-items:center;justify-content:space-between;}
.mc-label{font-size:11.5px;font-weight:600;letter-spacing:.05em;text-transform:uppercase;color:var(--faint);}
.mc-cmpset-rows{display:grid;gap:6px;margin:0;padding:0;list-style:none;}
.mc-cmpset-row{display:flex;align-items:center;gap:11px;padding:8px 11px;border-radius:9px;background:var(--ink-raise);border:1px solid var(--line);}
.mc-cmpset-row .idx{width:18px;font-family:var(--f-mono,ui-monospace);font-size:11px;color:var(--faint);}
.mc-cmpset-row .lbl{flex:1;font-size:13px;color:var(--text);overflow-wrap:anywhere;}
.mc-cmpset-row .rm{flex:none;border:0;background:transparent;color:var(--faint);font-size:13px;cursor:pointer;padding:2px 4px;border-radius:6px;}
.mc-cmpset-row .rm:hover{color:var(--text);background:rgba(255,255,255,.06);}
```

- [ ] **Step 3: Rewrite `CompareTab.test.tsx`**

Replace the entire file (drives off `set` + a stub provider):

```tsx
// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CompareTab } from "./CompareTab";
import type { GeocodingProvider } from "../lib/geocoding";
import type { ComparePoint } from "../lib/useCompareSet";
import type { AnalysisSettings, SiteComparison, SiteComparisonOption, SitePairwiseResult, SiteDecisionClass } from "../types";

const provider: GeocodingProvider = { search: vi.fn().mockResolvedValue([]) };
const analysis: AnalysisSettings = { startDate: "2026-01-01", endDate: "2026-06-24", radiusM: 250, offenseCategory: "PROPERTY", layer: "reported" };
const setOf = (...labels: string[]): ComparePoint[] => labels.map((l, i) => ({ latitude: 47.6 + i * 0.01, longitude: -122.3 - i * 0.01, label: l }));

function opt(id: string, label: string, count: number, rate: number): SiteComparisonOption {
  return { id, label, geometry_type: "place_buffer", radius_m: 250, incident_count: count, exposure: 1, exposure_unit: "square_km_days", incident_rate: rate };
}
function pair(a: string, b: string, decision: SiteDecisionClass, winner: string | null): SitePairwiseResult {
  return { id: `${a}-${b}`, option_a_id: a, option_a_label: a, option_b_id: b, option_b_label: b, winner_option_id: winner, winner_label: winner, decision_class: decision, method: "quasipoisson", incident_count_a: 0, incident_count_b: 0, exposure_a: 1, exposure_b: 1, exposure_unit: "square_km_days", rate_a: 0, rate_b: 0, rate_ratio: 0.38, ci_lower: 0.2, ci_upper: 0.71, p_value: 0.001, adjusted_p_value: 0.004, overdispersion_phi: 1.1, overdispersion_status: "ok", minimum_data_status: "met", caveat_text: "" };
}
const clearSweep: SiteComparison = {
  id: "c1", comparison_type: "site", geometry_type: "place_buffer", radius_m: 250, analysis_start_date: "2026-01-01", analysis_end_date: "2026-06-24",
  offense_category: null, offense_subcategory: null, nibrs_group: null, created_at: "2026-07-03",
  overview: { label: "Overview", decision_class: "statistically_lower", recommendation_option_id: "a", recommendation_label: "Pike", summary_text: "", caveat_text: "cav", options: [opt("a", "Pike", 12, 3.9), opt("b", "Bell", 44, 14.3)] },
  analytical: { label: "Analytical", source_dataset: "seattle_spd_crime", exposure_unit: "square_km_days", full_caveat_text: "full cav", options: [opt("a", "Pike", 12, 3.9), opt("b", "Bell", 44, 14.3)], pairwise_results: [pair("a", "b", "statistically_lower", "a")] },
};

afterEach(cleanup);

const base = { provider, onAddPoint: vi.fn(), onRemovePoint: vi.fn(), analysis, running: false, onRun: vi.fn() };

describe("CompareTab (editable set)", () => {
  it("empty set: prompts to add addresses and shows the add input", () => {
    render(<CompareTab {...base} set={[]} comparison={null} />);
    expect(screen.getByText(/add at least two addresses/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/add an address/i)).toBeInTheDocument();
  });

  it("one address: nudges to add one more; compare disabled", () => {
    render(<CompareTab {...base} set={setOf("Pike")} comparison={null} />);
    expect(screen.getByText(/add one more address/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /compare addresses/i })).toBeDisabled();
  });

  it("two addresses, not yet run: lists them with remove, invites compare, fires onRun", () => {
    const onRemovePoint = vi.fn();
    const onRun = vi.fn();
    render(<CompareTab {...base} onRemovePoint={onRemovePoint} onRun={onRun} set={setOf("Pike", "Bell")} comparison={null} />);
    const rows = screen.getByLabelText(/addresses to compare/i);
    expect(within(rows).getByText("Pike")).toBeInTheDocument();
    expect(screen.getByText(/rank their reported incident rates/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /remove Pike/i }));
    expect(onRemovePoint).toHaveBeenCalledWith(0);
    fireEvent.click(screen.getByRole("button", { name: /compare addresses/i }));
    expect(onRun).toHaveBeenCalled();
  });

  it("with a comparison: renders the slice-A ranked verdict", () => {
    render(<CompareTab {...base} set={setOf("Pike", "Bell")} comparison={clearSweep} />);
    expect(screen.getByText(/statistically lower than every other/i)).toBeInTheDocument();
    expect(within(screen.getByTestId("compare-ranked")).getByText("Pike")).toBeInTheDocument();
  });

  it("the dynamic verdict region never emits safety-ranking vocabulary", () => {
    render(<CompareTab {...base} set={setOf("Pike", "Bell")} comparison={clearSweep} />);
    const dynamic = `${screen.getByTestId("compare-callout").textContent ?? ""} ${screen.getByTestId("compare-ranked").textContent ?? ""}`.toLowerCase();
    for (const banned of ["safe", "unsafe", "safety", "danger", "dangerous", "risk", "risky"]) {
      expect(dynamic).not.toContain(banned);
    }
  });
});
```

- [ ] **Step 4: Run to verify (component in isolation)**

Run: `cd frontend && npx vitest run src/components/CompareTab.test.tsx --environment jsdom`
Expected: PASS (5 tests). (`npm run lint` will still fail repo-wide until Task 4 updates the `<CompareTab>` mount — that's expected here.)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/CompareTab.tsx frontend/src/components/CompareTab.test.tsx frontend/src/styles/mapWorkspace.css
git commit -m "feat(compare): CompareTab renders the editable address set"
```

---

## Task 4: wire the compare set into `MapWorkspace`

**Files:**
- Modify: `frontend/src/components/MapWorkspace.tsx`
- Modify: `frontend/src/components/MapWorkspace.test.tsx` (if the compare tests need the new props/flow)

- [ ] **Step 1: Reorder + wire**

In `frontend/src/components/MapWorkspace.tsx`:

1. Add imports at the top with the other hook/component imports:
```tsx
import { useCompareSet } from "../lib/useCompareSet";
import { createBackendProvider } from "../lib/geocoding";
```

2. **Move the `selected` useMemo up.** It currently sits at ~lines 169–184; its only deps are `sharedPoints`, `data.places`, `selectedIds` — all defined earlier (sharedPoints ~35, data ~54, selectedIds is state). Cut the whole `const selected = useMemo(... , [sharedPoints, data.places, selectedIds]);` block and paste it immediately BEFORE the `useAnalyze`/`useCompare` calls (~line 56). Nothing between lines 57–169 references `selected` (first other use is `buildShareUrl` ~186), so the move is behavior-preserving.

3. Immediately after the moved `selected` memo, add:
```tsx
  const compareSet = useCompareSet(selected);
  const geocoder = useMemo(() => createBackendProvider(), []);
```
(If a `GeocodingProvider` is already constructed in this file for `PlaceSearch`, reuse that instead of a second `createBackendProvider()` — grep `createBackendProvider` / `PlaceSearch` in this file first; only add `geocoder` if none exists.)

4. Change the `useCompare` call's points arg from `points: sharedPoints ?? undefined` to:
```tsx
  const compare = useCompare({ selectedIds, analysis, setError: data.setError, points: compareSet.points });
```
(Leave the `useAnalyze` call's `points: sharedPoints ?? undefined` unchanged — Analyze is out of scope.)

5. In `buildShareUrl` (~186–199), make the compare branch serialize the edited set. Change the `points` computation to:
```tsx
    const points = tab === "compare"
      ? compareSet.points.map((p) => ({ latitude: Number(p.latitude.toFixed(3)), longitude: Number(p.longitude.toFixed(3)), label: p.label }))
      : (sharedPoints ?? selected.map((p) => ({ latitude: Number((p.latitude ?? 0).toFixed(3)), longitude: Number((p.longitude ?? 0).toFixed(3)), label: p.display_label })));
```
and add `compareSet` to the `useCallback` dependency array.

6. Update the `<CompareTab>` mount (~339–341):
```tsx
          {activeTab === "compare" ? (
            <CompareTab
              set={compareSet.points}
              provider={geocoder}
              onAddPoint={compareSet.add}
              onRemovePoint={compareSet.removeAt}
              analysis={analysis}
              comparison={compare.comparison}
              running={compare.running}
              onRun={compare.runCompare}
              onCopyLink={() => buildShareUrl("compare")}
            />
          ) : null}
```

- [ ] **Step 2: Full verification gate**

Run: `cd .. && make test-all` (from the worktree root)
Expected: pytest green (backend untouched), ruff clean, `npm test` green, `npm run build` succeeds. The likely fallout is in `MapWorkspace.test.tsx`'s compare cases (they render `<CompareTab>` through MapWorkspace): the shared-view auto-run still works because `useCompareSet` seeds synchronously from `selected` (which is seeded from `sharedPoints`), so `compareSet.points` has the 2 shared points on first render and the auto-run's `runCompare` sees them. If a compare test asserts old copy (e.g. "Select at least two places"), update it to the new editor copy ("Add at least two addresses" / the address rows). Fix minimally, deletion/retarget only — do not weaken the shared-view or assistant-bridge assertions (they should still `findByTestId("compare-ranked")`).

- [ ] **Step 3: Commit**

```bash
git add frontend/src
git commit -m "feat(compare): wire the editable set through MapWorkspace (points-driven compare)"
```

---

## PART 2 — rate-ratio interval plot

## Task 5: extend `compareVerdict.ts` with the plotted interval

**Files:**
- Modify: `frontend/src/lib/compareVerdict.ts`
- Modify: `frontend/src/lib/compareVerdict.test.ts`

- [ ] **Step 1: Write the failing test**

Append to `frontend/src/lib/compareVerdict.test.ts` (reuse the file's existing `opt`/`pair`/`comparison` builders; the `pair` builder there takes `(a, b, decision, winner, ratio)` — pass an explicit `ratio` and note the builder sets `ci_lower = ratio*0.6`, `ci_upper = ratio*1.4`):

```ts
describe("toCompareVerdict — plot interval (Part 2)", () => {
  it("inverts the ratio CI onto the multiple-of-lowest axis for each non-lowest row", () => {
    // candidate 'a' is lowest; pair a-vs-b has rate_ratio 0.4 (=lowest/other), ci 0.24–0.56
    const c = comparison("statistically_lower",
      [opt("a", "Pike", 12, 3.9), opt("b", "Bell", 31, 10.1)],
      [pair("a", "b", "statistically_lower", "a", 0.4)], "a");
    const m = toCompareVerdict(c);
    const lowest = m.rows.find((r) => r.label === "Pike")!;
    const other = m.rows.find((r) => r.label === "Bell")!;
    expect(lowest.plotCiLow).toBeNull();
    expect(lowest.plotCiHigh).toBeNull();
    // multiple axis: interval = [1/ci_upper, 1/ci_lower] = [1/0.56, 1/0.24]
    expect(other.plotCiLow).toBeCloseTo(1 / 0.56, 4);
    expect(other.plotCiHigh).toBeCloseTo(1 / 0.24, 4);
  });

  it("computes the inverted bounds from any present pairwise (the component decides whether to draw)", () => {
    const c = comparison("not_statistically_clear",
      [opt("a", "Pike", 12, 3.9), opt("z", "Zed", 3, 9.0)],
      [pair("a", "z", "insufficient_data", null, 0.43)], null);
    const m = toCompareVerdict(c);
    const zed = m.rows.find((r) => r.label === "Zed")!;
    // relationship is 'limited' (insufficient) — still expose the inverted interval bounds if a pair exists
    expect(zed.plotCiLow).toBeCloseTo(1 / (0.43 * 1.4), 4);
    expect(zed.plotCiHigh).toBeCloseTo(1 / (0.43 * 0.6), 4);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npx vitest run src/lib/compareVerdict.test.ts`
Expected: FAIL — `plotCiLow`/`plotCiHigh` undefined on the row.

- [ ] **Step 3: Extend `compareVerdict.ts`**

In `frontend/src/lib/compareVerdict.ts`, add two **optional** fields to `CompareVerdictRow` (after `multipleOfLowest`). Optional so slice A's existing `CompareRankedList.test.tsx` row fixtures — which don't set them — still type-check; the component treats missing the same as null via `!= null`:

```ts
  /** 95% interval on the "×the lowest" axis: inverted+swapped from the pairwise ratio CI. Null/absent for the lowest row or when there is no pairwise. */
  plotCiLow?: number | null;
  plotCiHigh?: number | null;
```

And in the `rows` map, compute them from the row's `pair` (the pairwise ratio CI is on `rate_ratio = lowest/other ≤ 1`; the multiple axis is the inverse, so the interval inverts and swaps):

```ts
  const rows: CompareVerdictRow[] = sorted.map((o, i) => {
    const isLowest = candidate ? o.id === candidate.id : false;
    const pair = isLowest ? null : pairByOther.get(o.id) ?? null;
    return {
      rank: i + 1,
      optionId: o.id,
      label: o.label,
      incidentCount: o.incident_count,
      rate: o.incident_rate,
      barFraction: maxRate > 0 ? o.incident_rate / maxRate : 0,
      multipleOfLowest: isLowest || lowestRate <= 0 ? null : o.incident_rate / lowestRate,
      plotCiLow: pair && pair.ci_upper > 0 ? 1 / pair.ci_upper : null,
      plotCiHigh: pair && pair.ci_lower > 0 ? 1 / pair.ci_lower : null,
      relationship: isLowest ? "lowest" : relationshipFor(pair),
      pairwise: pair,
    };
  });
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd frontend && npx vitest run src/lib/compareVerdict.test.ts`
Expected: PASS (existing tests + 2 new).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/compareVerdict.ts frontend/src/lib/compareVerdict.test.ts
git commit -m "feat(compare): derive the inverted ratio-CI interval for the plot"
```

---

## Task 6: `CompareRatioPlot` component

**Files:**
- Create: `frontend/src/components/CompareRatioPlot.tsx`
- Test: `frontend/src/components/CompareRatioPlot.test.tsx`
- Modify: `frontend/src/styles/mapWorkspace.css`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/CompareRatioPlot.test.tsx`:

```tsx
// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { CompareRatioPlot } from "./CompareRatioPlot";
import type { CompareVerdictRow } from "../lib/compareVerdict";

function row(label: string, rel: CompareVerdictRow["relationship"], mult: number | null, lo: number | null, hi: number | null, rank: number): CompareVerdictRow {
  return { rank, optionId: label, label, incidentCount: 10, rate: mult ?? 1, barFraction: 0.5, multipleOfLowest: mult, plotCiLow: lo, plotCiHigh: hi, relationship: rel, pairwise: null };
}
const rows: CompareVerdictRow[] = [
  row("Pike", "lowest", null, null, null, 1),
  row("Bell", "higher", 2.6, 1.4, 4.9, 2),
  row("Yesler", "higher", 3.7, 2.0, 6.8, 3),
];

afterEach(cleanup);

describe("CompareRatioPlot", () => {
  it("renders a reference and a marked row per non-lowest address", () => {
    render(<CompareRatioPlot rows={rows} />);
    const plot = screen.getByTestId("compare-plot");
    expect(within(plot).getByText("Bell")).toBeInTheDocument();
    expect(within(plot).getByText("Yesler")).toBeInTheDocument();
    expect(within(plot).getByText("Pike")).toBeInTheDocument();
    expect(within(plot).getByText(/same rate/i)).toBeInTheDocument();
  });

  it("draws no interval bar for a limited-data row (dot only)", () => {
    const limitedRows: CompareVerdictRow[] = [
      row("Pike", "lowest", null, null, null, 1),
      row("Zed", "limited", 2.3, 1.2, 4.4, 2),
    ];
    render(<CompareRatioPlot rows={limitedRows} />);
    expect(screen.getByTestId("compare-plot").querySelectorAll(".mc-plot-row .bar")).toHaveLength(0);
  });

  it("carries the raw-bar / corrected-label honesty footnote", () => {
    render(<CompareRatioPlot rows={rows} />);
    expect(within(screen.getByTestId("compare-plot")).getByText(/label is the corrected verdict/i)).toBeInTheDocument();
  });

  it("never emits safety-ranking vocabulary", () => {
    render(<CompareRatioPlot rows={rows} />);
    const text = (screen.getByTestId("compare-plot").textContent ?? "").toLowerCase();
    for (const banned of ["safe", "unsafe", "safety", "danger", "dangerous", "risk", "risky"]) {
      expect(text).not.toContain(banned);
    }
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npx vitest run src/components/CompareRatioPlot.test.tsx --environment jsdom`
Expected: FAIL — component not found.

- [ ] **Step 3: Implement `CompareRatioPlot.tsx`**

Create `frontend/src/components/CompareRatioPlot.tsx`. It maps the "×the lowest" axis (domain 1 → max interval) to percent positions; the lowest is the reference at 1×; each other row draws a bar from `plotCiLow`→`plotCiHigh` with a dot at `multipleOfLowest`; a faint guide sits at 1.25× (the 0.80 effect-floor on this axis). Neutral palette only.

```tsx
import type { CompareVerdictRow } from "../lib/compareVerdict";

// Positions on the "× the lowest" axis. Domain starts at the same-rate line (1×) with a small
// left margin so a marker at ~1× is visible, up to the largest interval end (padded).
function makeScale(rows: CompareVerdictRow[]) {
  const highs = rows.map((r) => r.plotCiHigh).filter((v): v is number => v != null);
  const mults = rows.map((r) => r.multipleOfLowest).filter((v): v is number => v != null);
  const domainMax = Math.max(1.5, ...highs, ...mults) * 1.05;
  const domainMin = 0.9;
  const pos = (v: number) => Math.max(0, Math.min(100, ((v - domainMin) / (domainMax - domainMin)) * 100));
  return { pos };
}

export function CompareRatioPlot({ rows }: { rows: CompareVerdictRow[] }) {
  const lowest = rows.find((r) => r.relationship === "lowest");
  const others = rows.filter((r) => r.relationship !== "lowest");
  const { pos } = makeScale(rows);
  const onePct = pos(1);
  const floorPct = pos(1.25);

  return (
    <div className="mc-plot" data-testid="compare-plot">
      <p className="mc-label">Each address vs the lowest rate — 95% interval</p>
      <div className="mc-plot-chart">
        <span className="mc-plot-line same" style={{ left: `${onePct}%` }} aria-hidden />
        <span className="mc-plot-line floor" style={{ left: `${floorPct}%` }} aria-hidden />
        <div className="mc-plot-row ref">
          <span className="name">{lowest ? lowest.label : "lowest"}</span>
          <div className="track"><span className="dot ref" style={{ left: `${onePct}%` }} /></div>
          <span className="val">1× · same rate</span>
        </div>
        {others.map((r) => {
          const hasBar = r.relationship !== "limited" && r.plotCiLow != null && r.plotCiHigh != null;
          const left = hasBar ? pos(r.plotCiLow as number) : 0;
          const width = hasBar ? Math.max(1, pos(r.plotCiHigh as number) - left) : 0;
          const dot = r.multipleOfLowest != null ? pos(r.multipleOfLowest) : onePct;
          return (
            <div className={`mc-plot-row ${r.relationship}`} key={r.optionId}>
              <span className="name">{r.label}</span>
              <div className="track">
                {hasBar ? <span className="bar" style={{ left: `${left}%`, width: `${width}%` }} /> : null}
                <span className="dot" style={{ left: `${dot}%` }} />
              </div>
              <span className="val">{r.multipleOfLowest != null ? `${r.multipleOfLowest.toFixed(1)}×` : "—"}</span>
            </div>
          );
        })}
      </div>
      <p className="mc-plot-foot">Bar is the raw 95% interval; the “clearly higher / similar” label is the corrected verdict and is authoritative. Dashed line = same rate as the lowest.</p>
    </div>
  );
}
```

- [ ] **Step 4: Add CSS**

Append to `frontend/src/styles/mapWorkspace.css` (neutral palette; no safety colors):

```css
.mc-plot{display:grid;gap:7px;margin:2px 0 14px;}
.mc-plot-chart{position:relative;display:grid;gap:4px;padding:4px 0;}
.mc-plot-line{position:absolute;top:0;bottom:0;border-left:1px dashed rgba(255,255,255,.28);}
.mc-plot-line.floor{border-left-color:rgba(255,255,255,.12);}
.mc-plot-row{display:grid;grid-template-columns:96px 1fr 74px;align-items:center;gap:10px;height:26px;}
.mc-plot-row .name{font-size:12px;color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.mc-plot-row .track{position:relative;height:100%;}
.mc-plot-row .bar{position:absolute;top:50%;transform:translateY(-50%);height:5px;border-radius:3px;background:rgba(116,133,142,.5);}
.mc-plot-row .dot{position:absolute;top:50%;transform:translate(-50%,-50%);width:10px;height:10px;border-radius:50%;background:var(--slate);}
.mc-plot-row .dot.ref{background:var(--clay);}
.mc-plot-row.similar .bar{background:rgba(150,150,150,.35);}
.mc-plot-row .val{font-family:var(--f-mono,ui-monospace);font-size:11px;color:var(--dim);text-align:right;white-space:nowrap;}
.mc-plot-foot{font-size:10.5px;line-height:1.5;color:var(--faint);margin:0;}
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd frontend && npx vitest run src/components/CompareRatioPlot.test.tsx --environment jsdom`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/CompareRatioPlot.tsx frontend/src/components/CompareRatioPlot.test.tsx frontend/src/styles/mapWorkspace.css
git commit -m "feat(compare): rate-ratio interval plot component"
```

---

## Task 7: mount the plot in `CompareTab` + extend the invariant scan

**Files:**
- Modify: `frontend/src/components/CompareTab.tsx`
- Modify: `frontend/src/components/CompareTab.test.tsx`

- [ ] **Step 1: Mount the plot**

In `frontend/src/components/CompareTab.tsx`, add the import:
```tsx
import { CompareRatioPlot } from "./CompareRatioPlot";
```
and render it inside the `verdict ?` block, immediately after `<CompareRankedList .../>`:
```tsx
          <CompareRankedList rows={verdict.rows} noun={noun} />
          <CompareRatioPlot rows={verdict.rows} />
```

- [ ] **Step 2: Extend the invariant scan to the plot**

In `frontend/src/components/CompareTab.test.tsx`, update the "dynamic verdict region" test to also scan the plot region:
```tsx
    const dynamic = `${screen.getByTestId("compare-callout").textContent ?? ""} ${screen.getByTestId("compare-ranked").textContent ?? ""} ${screen.getByTestId("compare-plot").textContent ?? ""}`.toLowerCase();
```

- [ ] **Step 3: Verify**

Run: `cd frontend && npx vitest run src/components/CompareTab.test.tsx --environment jsdom`
Expected: PASS — the plot renders under a verdict and the banned-word scan covers its labels.

- [ ] **Step 4: Full gate**

Run: `cd .. && make test-all`
Expected: all green (pytest + ruff + npm test + build).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/CompareTab.tsx frontend/src/components/CompareTab.test.tsx
git commit -m "feat(compare): mount the rate-ratio interval plot in the verdict"
```

---

## Task 8: ROADMAP tick, gate, PR

**Files:**
- Modify: `docs/ROADMAP.md`

- [ ] **Step 1: Tick slice B in the Phase 5 decomposition**

In `docs/ROADMAP.md`, under the Phase 5 decomposition block (the `- [ ] **Slice B — multi-address compare UX**` line added by slice A), change slice B's checkbox to `[x]` and update its note:

```markdown
- [x] **Slice B — multi-address compare UX** — shipped: a Compare-owned editable address set
  (add via the reused address search, remove, seeded-from-selection, decoupled, 2–10) driving
  the verdict, plus an honest rate-ratio interval plot in the verdict (the payload-ready
  visualization; overlapping bell curves were rejected as statistically dishonest here).
  Frontend-only. Spec/plan: `docs/superpowers/{specs,plans}/2026-07-03-compare-multi-address*`.
```

- [ ] **Step 2: Final gate**

Run: `cd frontend && npm run lint && npm test && cd .. && make test-all`
Expected: all green.

- [ ] **Step 3: Commit, push, open PR**

```bash
git add docs/ROADMAP.md
git commit -m "docs(roadmap): tick Phase 5 slice B (multi-address compare + interval plot)"
git push -u origin jcscocca/claude/compare-multi-address
gh pr create --title "feat(compare): multi-address compare set + rate-ratio interval plot (Phase 5 slice B)" --body "$(cat <<'EOF'
Phase 5 slice B of the compare-first flagship (spec: docs/superpowers/specs/2026-07-03-compare-multi-address-design.md). One PR, two parts, frontend-only.

Part 1 — multi-address compare UX: a Compare-owned editable, ephemeral address set (add via the reused address search, removable rows, seeded from the current selection, decoupled from saved Places, 2–10, Seattle-bbox), driving the slice-A verdict via the inline-points path. Shareable via the existing ?view= link.

Part 2 — honest rate-ratio interval plot in the verdict: each address vs the lowest on a "×the lowest" axis with its 95% interval and a same-rate reference line — the payload-ready visualization that gives the "how big / is it real" intuition without the overlapping-bell-curve fallacy (overlap ≠ non-significance; no per-address CI in the payload; Poisson asymmetry). Honesty rules baked in: coded to the real ≤1 rate_ratio (inverted to the multiple axis), and the BH-corrected label stays authoritative over the raw interval bar. Neutral palette; the safety-vocabulary guard extends to the plot's labels.

make test-all green.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Out of scope (do not do here)

- Any backend/`app/` change (the per-address "rate ± margin of error" number-line would need a backend per-address Poisson CI — deferred fast-follow).
- Rendering the compare set on the map (MapCanvas gets no compare state today; net-new wiring).
- Persisting a compare address to Places; auto-run on edit; slice C (comparison-first landing).
- Overlapping bell curves (rejected — statistically dishonest for this model).
