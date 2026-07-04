# Slice C — single-address entry → context → optional compare — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lead a fresh session with a single-address lookup that flies the map, shows that address's reported-incident context on the reused Analyze tab (ephemeral — no DB write), and offers a one-click bridge into the multi-address Compare flow.

**Architecture:** Frontend only. A new thin `AddressLookup` component becomes the drawer's fresh-session landing. `MapWorkspace` gains a `lookupPoint` state that drives Analyze through the existing inline-`points` path (the one shared-view links already use) and seeds the existing `useCompareSet`. The looked-up address is drawn on the map by reusing the existing draft pin + fly-to. No backend, no new API, no new tab.

**Tech Stack:** React 18 + TypeScript, Vite, Vitest + Testing Library (jsdom). Spec: `docs/superpowers/specs/2026-07-03-compare-single-address-entry-design.md`.

---

## File Structure

- **Create** `frontend/src/components/AddressLookup.tsx` — the fresh-session landing: framing copy + reused `PlaceSearch` + "Add places manually" escape. One responsibility: capture the first address.
- **Create** `frontend/src/components/AddressLookup.test.tsx` — unit tests for the landing.
- **Modify** `frontend/src/lib/usePinDraft.ts` — extract a `previewSearch(result)` method (draft + fly-to, no tab switch) so the lookup can reuse the map marker without forcing the Places tab.
- **Modify** `frontend/src/components/MapWorkspace.tsx` — `lookupPoint`/`manualEntry` state, landing gate (replacing the `mc-empty` overlay), lookup → Analyze wiring, compare bridge, save-to-places.
- **Modify** `frontend/src/components/MapWorkspace.test.tsx` — mock `../lib/geocoding`; update 4 existing empty-session waits; add landing/lookup/bridge/save integration tests.
- **Modify** `frontend/src/components/AnalyzeTab.tsx` — optional `onCompareWith` / `onSave` props + their buttons.
- **Modify** `frontend/src/components/AnalyzeTab.test.tsx` — unit tests for the two new props.
- **Modify** `frontend/src/styles/mapWorkspace.css` — minimal landing styles.
- **Modify** `docs/ROADMAP.md` — tick slice C (and slice A bookkeeping).

All commands run from the worktree root `/Users/jscocca/Repos/Crime Commute Safety Tool/.worktrees/compare-single-address-entry` unless noted. Frontend commands run from `frontend/`.

---

### Task 1: `AddressLookup` component

**Files:**
- Create: `frontend/src/components/AddressLookup.tsx`
- Create: `frontend/src/components/AddressLookup.test.tsx`
- Modify: `frontend/src/styles/mapWorkspace.css` (append landing styles)

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/AddressLookup.test.tsx`:

```tsx
// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AddressLookup } from "./AddressLookup";
import type { GeocodingProvider } from "../lib/geocoding";
import type { GeocodeResult } from "../types";

const result: GeocodeResult = { label: "123 Main St, Seattle", latitude: 47.61, longitude: -122.34, source: "test" };

function stubProvider(results: GeocodeResult[] = [result]): GeocodingProvider {
  return { search: vi.fn().mockResolvedValue(results) };
}

afterEach(() => { cleanup(); vi.clearAllMocks(); localStorage.clear(); });

describe("AddressLookup", () => {
  it("renders the look-up framing", () => {
    render(<AddressLookup provider={stubProvider()} onSelect={vi.fn()} onManual={vi.fn()} />);
    expect(screen.getByRole("heading", { name: /look up an address/i })).toBeInTheDocument();
  });

  it("calls onManual when 'Add places manually' is clicked", () => {
    const onManual = vi.fn();
    render(<AddressLookup provider={stubProvider()} onSelect={vi.fn()} onManual={onManual} />);
    fireEvent.click(screen.getByRole("button", { name: /add places manually/i }));
    expect(onManual).toHaveBeenCalledTimes(1);
  });

  it("calls onSelect with the chosen address", async () => {
    const onSelect = vi.fn();
    render(<AddressLookup provider={stubProvider()} onSelect={onSelect} onManual={vi.fn()} />);
    fireEvent.change(screen.getByLabelText(/search an address/i), { target: { value: "123 Main" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    fireEvent.click(await screen.findByText("123 Main St, Seattle"));
    expect(onSelect).toHaveBeenCalledWith(result);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/components/AddressLookup.test.tsx`
Expected: FAIL — `Failed to resolve import "./AddressLookup"`.

- [ ] **Step 3: Write the component**

Create `frontend/src/components/AddressLookup.tsx`:

```tsx
import { PlaceSearch } from "./PlaceSearch";
import type { GeocodingProvider } from "../lib/geocoding";
import type { GeocodeResult } from "../types";

type Props = {
  provider: GeocodingProvider;
  onSelect: (result: GeocodeResult) => void;
  onManual: () => void;
};

/**
 * Fresh-session landing for the side drawer. Leads with a single-address lookup (the
 * reused PlaceSearch box, which already carries recent searches) so the first action is
 * "which place?", and offers a secondary escape into manual place management.
 */
export function AddressLookup({ provider, onSelect, onManual }: Props) {
  return (
    <div className="mc-panel is-active mc-lookup" role="tabpanel" aria-label="Look up an address">
      <div className="mc-lookup-head">
        <h4>Look up an address</h4>
        <p>See the reported-incident context around a place — then compare it with others if you like.</p>
      </div>
      <PlaceSearch provider={provider} onSelectResult={onSelect} />
      <button type="button" className="mc-link-copy mc-lookup-manual" onClick={onManual}>
        Add places manually
      </button>
    </div>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npx vitest run src/components/AddressLookup.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 5: Add landing styles**

Append to `frontend/src/styles/mapWorkspace.css` (end of file):

```css
.mc-lookup-head{padding:2px 2px 12px;}
.mc-lookup-head h4{margin:0 0 5px;font-size:15px;color:var(--text);}
.mc-lookup-head p{margin:0;font-size:13px;color:var(--dim);line-height:1.5;}
.mc-lookup-manual{margin-top:14px;}
```

- [ ] **Step 6: Commit**

```bash
cd frontend && npx vitest run src/components/AddressLookup.test.tsx && cd ..
git add frontend/src/components/AddressLookup.tsx frontend/src/components/AddressLookup.test.tsx frontend/src/styles/mapWorkspace.css
git commit -m "feat(compare): AddressLookup landing component (slice C)"
```

---

### Task 2: `usePinDraft` — extract `previewSearch`

Behavior-preserving refactor so the lookup can set the draft marker + fly-to **without** switching to the Places tab (which `handleSearchSelect` does for the save popover).

**Files:**
- Modify: `frontend/src/lib/usePinDraft.ts`

- [ ] **Step 1: Add `previewSearch` to the interface**

In `frontend/src/lib/usePinDraft.ts`, in `interface PinDraftController`, add the method after `handleSearchSelect`:

```ts
  handleSearchSelect: (result: GeocodeResult) => void;
  previewSearch: (result: GeocodeResult) => void;
```

- [ ] **Step 2: Extract the draft+fly-to assignment**

Replace the existing `handleSearchSelect` function:

```ts
  function handleSearchSelect(result: GeocodeResult) {
    setDraft({
      latitude: result.latitude,
      longitude: result.longitude,
      display_label: result.label,
      visit_count: 1,
      sensitivity_class: "normal",
      source: "search",
    });
    setFlyTo({ lat: result.latitude, lng: result.longitude });
    setDraftError("");
    setActiveTab("places");
  }
```

with:

```ts
  // Sets the draft pin + flies the map to a searched address, WITHOUT changing the active
  // tab. handleSearchSelect adds the Places-tab switch (to show the save popover); the
  // single-address lookup reuses previewSearch alone and routes to Analyze itself.
  function previewSearch(result: GeocodeResult) {
    setDraft({
      latitude: result.latitude,
      longitude: result.longitude,
      display_label: result.label,
      visit_count: 1,
      sensitivity_class: "normal",
      source: "search",
    });
    setFlyTo({ lat: result.latitude, lng: result.longitude });
    setDraftError("");
  }

  function handleSearchSelect(result: GeocodeResult) {
    previewSearch(result);
    setActiveTab("places");
  }
```

- [ ] **Step 3: Return `previewSearch`**

In the returned object at the bottom of `usePinDraft`, add `previewSearch` next to `handleSearchSelect`:

```ts
    handleSearchSelect,
    previewSearch,
```

- [ ] **Step 4: Run the full frontend suite (refactor is behavior-preserving)**

Run: `cd frontend && npm test`
Expected: PASS — same 219 tests as baseline, 0 failures.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/usePinDraft.ts
git commit -m "refactor(compare): extract usePinDraft.previewSearch (draft+flyTo, no tab switch)"
```

---

### Task 3: `MapWorkspace` — entry landing + ephemeral lookup → Analyze

**Files:**
- Modify: `frontend/src/components/MapWorkspace.tsx`
- Modify: `frontend/src/components/MapWorkspace.test.tsx`

- [ ] **Step 1: Add the geocoding mock + update the 4 existing empty-session waits (failing setup)**

At the TOP of `frontend/src/components/MapWorkspace.test.tsx`, directly under the existing `vi.mock("../api/client", ...)` block, add the geocoding mock so search resolves controllable results (real exports preserved via `importOriginal`):

```tsx
const geocodeSearch = vi.hoisted(() => vi.fn());
vi.mock("../lib/geocoding", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../lib/geocoding")>()),
  geocodingProvider: { search: geocodeSearch },
}));
```

Then change every `await screen.findByText(/Map your places/i);` (4 occurrences — currently lines ~128, ~155, ~189, ~220) to:

```tsx
    await screen.findByRole("heading", { name: /look up an address/i });
```

In the **bulk import** test ("selects bulk imported places so analysis can run without manual selection"), after that wait and BEFORE `fireEvent.click(screen.getByRole("button", { name: "Import" }))`, add a step to leave the landing for the full Places tab:

```tsx
    fireEvent.click(screen.getByRole("button", { name: /add places manually/i }));
```

- [ ] **Step 2: Run to verify the suite fails (landing not implemented yet)**

Run: `cd frontend && npx vitest run src/components/MapWorkspace.test.tsx`
Expected: FAIL — the `look up an address` heading does not render yet.

- [ ] **Step 3: Wire the lookup state + landing into `MapWorkspace`**

In `frontend/src/components/MapWorkspace.tsx`:

**(3a)** Add imports. Add to the component imports:

```tsx
import { AddressLookup } from "./AddressLookup";
```

and add `ComparePoint` and `GeocodeResult` to the type imports (extend the existing `import type { ... } from "../types"` and add the compare-set type):

```tsx
import type { ComparePoint } from "../lib/useCompareSet";
import type { AnalysisSettings, AssistantDashboardState, GeocodeResult, PlaceCreate, TabKey } from "../types";
```

**(3b)** Add state. Directly after the existing `const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());`:

```tsx
  const [lookupPoint, setLookupPoint] = useState<ComparePoint | null>(null);
  const [manualEntry, setManualEntry] = useState(false);
```

**(3c)** Extend the `selected` synthesis. Replace the existing `const selected = useMemo(...)` block with:

```tsx
  const selected = useMemo(() => {
    if (sharedPoints) {
      return sharedPoints.map((point, index) => ({
        id: `shared-${index}`,
        display_label: point.label,
        latitude: point.latitude,
        longitude: point.longitude,
        visit_count: 0,
        total_dwell_minutes: null,
        inferred_place_type: "shared_place",
        sensitivity_class: "normal",
      }));
    }
    if (lookupPoint) {
      return [{
        id: "lookup-0",
        display_label: lookupPoint.label,
        latitude: lookupPoint.latitude,
        longitude: lookupPoint.longitude,
        visit_count: 0,
        total_dwell_minutes: null,
        inferred_place_type: "lookup_place",
        sensitivity_class: "normal",
      }];
    }
    return data.places.filter((place) => selectedIds.has(place.id));
  }, [sharedPoints, lookupPoint, data.places, selectedIds]);
```

**(3d)** Extend the analyze points source. Replace the `points:` argument in the `useAnalyze({...})` call:

```tsx
  const analyze = useAnalyze({ selectedIds, analysis, refreshWithFallback: data.refreshWithFallback, setError: data.setError, points: sharedPoints ?? (lookupPoint ? [lookupPoint] : undefined) });
```

**(3e)** Clear the lookup when a saved place becomes the subject. In `selectPlaceIds`, add `setLookupPoint(null);` right after `invalidateAnalysisContext();`:

```tsx
  function selectPlaceIds(ids: string[]) {
    if (ids.length === 0) return;
    invalidateAnalysisContext();
    setLookupPoint(null);
    setSelectedIds((current) => {
      const next = new Set(current);
      ids.forEach((id) => next.add(id));
      return next;
    });
  }
```

In `handleToggleSelect`, add the same clear (and drop the ephemeral draft marker) right after `invalidateAnalysisContext();`:

```tsx
  function handleToggleSelect(id: string) {
    invalidateAnalysisContext();
    setLookupPoint(null);
    pinDraft.setDraft(null);
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }
```

**(3f)** Add the lookup handler + auto-run effect. Directly AFTER the `const pinDraft = usePinDraft({...});` declaration, add:

```tsx
  function handleLookup(result: GeocodeResult) {
    pinDraft.previewSearch(result);
    invalidateAnalysisContext();
    setSelectedIds(new Set());
    setManualEntry(false);
    setLookupPoint({ latitude: result.latitude, longitude: result.longitude, label: result.label });
    setActiveTab("analyze");
  }

  // Auto-run analysis for a just-looked-up address (mirrors the shared-view auto-run) so the
  // user sees its context without a second click. Guarded on lookupPoint; the analyze hook has
  // already re-rendered with the new points by the time this effect fires.
  useEffect(() => {
    if (lookupPoint) void analyze.runAnalyze();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lookupPoint]);
```

**(3g)** Compute the landing gate. Just before the `return (` of the component (near the other derived values), add:

```tsx
  const showLanding =
    data.places.length === 0 && !lookupPoint && !sharedPoints && !manualEntry && activeTab === "places" && !pinDraft.draft;
```

**(3h)** Remove the `mc-empty` overlay. Delete this block entirely (currently ~lines 269–274):

```tsx
        {data.places.length === 0 && !pinDraft.draft ? (
          <div className="mc-empty">
            <h3>Map your places</h3>
            <p>Choose <strong>Add pin</strong> then click the map, or search for an address in the Places tab.</p>
          </div>
        ) : null}
```

**(3i)** Render the landing in the drawer. Replace the four `{activeTab === "..." ? <...Tab/> : null}` children of `<BottomSheet>` by wrapping them in the landing gate. The `<BottomSheet ...>` opening tag and its `tabBadges`/other props stay unchanged; only its children change:

```tsx
          {showLanding ? (
            <AddressLookup provider={geocodingProvider} onSelect={handleLookup} onManual={() => setManualEntry(true)} />
          ) : (
            <>
              {activeTab === "places" ? (
                <PlacesTab
                  places={data.places}
                  selectedIds={selectedIds}
                  summary={data.summary}
                  radiusM={analysis.radiusM}
                  addPinMode={pinDraft.addPinMode}
                  search={<PlaceSearch provider={geocodingProvider} onSelectResult={pinDraft.handleSearchSelect} />}
                  draftPopover={pinDraft.draft ? (
                    <PinDraftPopover
                      draft={pinDraft.draft}
                      saving={pinDraft.draftSaving}
                      error={pinDraft.draftError}
                      onChange={(patch) => pinDraft.setDraft((current) => (current ? { ...current, ...patch } : current))}
                      onSave={pinDraft.saveDraft}
                      onCancel={() => pinDraft.setDraft(null)}
                    />
                  ) : null}
                  onStartAddPin={pinDraft.startAddPin}
                  onToggleSelect={handleToggleSelect}
                  onDelete={handleDelete}
                  onManualSubmit={handleManualSubmit}
                  onImportSubmit={handleImport}
                  onUploaded={data.personalUploadsEnabled ? () => data.refreshWithFallback("Uploaded, but dashboard totals could not refresh.") : undefined}
                />
              ) : null}
              {activeTab === "analyze" ? (
                <AnalyzeTab
                  selected={selected}
                  analysis={analysis}
                  availableRadii={data.availableRadii}
                  running={analyze.running}
                  incidentDetails={analyze.incidentDetails}
                  neighborhood={analyze.neighborhood}
                  error={data.error}
                  panelWidthPx={drawer.widthPx}
                  onChange={handleAnalysisChange}
                  onRun={analyze.runAnalyze}
                  onCopyLink={() => buildShareUrl("analyze")}
                />
              ) : null}
              {activeTab === "compare" ? (
                <CompareTab
                  set={compareSet.points}
                  provider={geocodingProvider}
                  onAddPoint={compareSet.add}
                  onRemovePoint={compareSet.removeAt}
                  analysis={analysis}
                  comparison={compare.comparison}
                  running={compare.running}
                  onRun={compare.runCompare}
                  onCopyLink={() => buildShareUrl("compare")}
                />
              ) : null}
              {activeTab === "export" ? <ExportTab href={data.exportHref} /> : null}
            </>
          )}
```

> Note: `useEffect` is already imported in `MapWorkspace.tsx` (line 1). No import change needed for the effect.

- [ ] **Step 4: Add the landing + lookup integration tests**

In `frontend/src/components/MapWorkspace.test.tsx`, inside the `describe("MapWorkspace", ...)` block, add:

```tsx
  it("leads a fresh session with the look-up landing", async () => {
    vi.mocked(createSession).mockResolvedValue({ session_state: "ready" });
    vi.mocked(getDashboardSummary).mockResolvedValue(makeSummary());
    render(<MapWorkspace />);
    expect(await screen.findByRole("heading", { name: /look up an address/i })).toBeInTheDocument();
    expect(screen.queryByText(/Map your places/i)).not.toBeInTheDocument();
  });

  it("looks up an address and analyzes it via the points path without saving a place", async () => {
    vi.mocked(createSession).mockResolvedValue({ session_state: "ready" });
    vi.mocked(getDashboardSummary).mockResolvedValue(makeSummary());
    vi.mocked(analyzePlaces).mockResolvedValue({ summary_count: 1 });
    vi.mocked(getIncidentDetails).mockResolvedValue(makeIncidentDetails());
    vi.mocked(getNeighborhoodAnalysis).mockResolvedValue(makeNeighborhoodAnalysis());
    geocodeSearch.mockResolvedValue([{ label: "123 Main St", latitude: 47.61, longitude: -122.34, source: "test" }]);

    render(<MapWorkspace />);
    await screen.findByRole("heading", { name: /look up an address/i });
    fireEvent.change(screen.getByLabelText(/search an address/i), { target: { value: "123 Main" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    fireEvent.click(await screen.findByText("123 Main St"));

    await waitFor(() => {
      expect(analyzePlaces).toHaveBeenCalledWith(expect.objectContaining({
        points: [{ latitude: 47.61, longitude: -122.34, label: "123 Main St" }],
        radii_m: [250],
        layer: "reported",
      }));
    });
    expect(createPlace).not.toHaveBeenCalled();
    expect(await screen.findByText("100 BLOCK MAIN ST")).toBeInTheDocument();
  });
```

- [ ] **Step 5: Run the MapWorkspace tests**

Run: `cd frontend && npx vitest run src/components/MapWorkspace.test.tsx`
Expected: PASS — all existing tests (with updated waits) plus the 2 new tests.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/MapWorkspace.tsx frontend/src/components/MapWorkspace.test.tsx
git commit -m "feat(compare): single-address lookup landing + Analyze via points path (slice C)"
```

---

### Task 4: Compare bridge (Analyze → Compare, anchor carried)

**Files:**
- Modify: `frontend/src/components/AnalyzeTab.tsx`
- Modify: `frontend/src/components/AnalyzeTab.test.tsx`
- Modify: `frontend/src/components/MapWorkspace.tsx`
- Modify: `frontend/src/components/MapWorkspace.test.tsx`

- [ ] **Step 1: Write the failing AnalyzeTab unit test**

In `frontend/src/components/AnalyzeTab.test.tsx`, add a test that the bridge button renders and fires when `onCompareWith` + `neighborhood` are provided. (Use the file's existing render helpers/fixtures; this test constructs the minimal props inline.)

```tsx
  it("renders a compare bridge that calls onCompareWith", () => {
    const onCompareWith = vi.fn();
    render(
      <AnalyzeTab
        selected={[]}
        analysis={{ startDate: "2026-01-01", endDate: "2026-06-30", radiusM: 250, offenseCategory: "", layer: "reported" }}
        availableRadii={[250]}
        running={false}
        neighborhood={{ radius_m: 250, analysis_start_date: "2026-01-01", analysis_end_date: "2026-06-30", offense_category: null, places: [], pairwise: [] }}
        onChange={vi.fn()}
        onRun={vi.fn()}
        onCompareWith={onCompareWith}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /compare with another address/i }));
    expect(onCompareWith).toHaveBeenCalledTimes(1);
  });
```

> If `AnalyzeTab.test.tsx` does not already import `fireEvent`/`vi`, add them to its existing `@testing-library/react` and `vitest` imports.

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npx vitest run src/components/AnalyzeTab.test.tsx`
Expected: FAIL — `onCompareWith` is not a prop; no such button.

- [ ] **Step 3: Add the prop + button to `AnalyzeTab`**

In `frontend/src/components/AnalyzeTab.tsx`, add to the `type Props`:

```tsx
  onRun: () => void;
  onCopyLink?: () => string | null;
  onCompareWith?: () => void;
```

Add `onCompareWith` to the destructured params of `export function AnalyzeTab({ ... })`.

Then, inside the `) : (` non-running branch, immediately after the existing `onCopyLink && neighborhood && (...)` "Copy link to this view" button block, add:

```tsx
          {onCompareWith && neighborhood && (
            <button type="button" className="mc-link-copy mc-compare-bridge" onClick={onCompareWith}>
              + Compare with another address
            </button>
          )}
```

- [ ] **Step 4: Run to verify the AnalyzeTab test passes**

Run: `cd frontend && npx vitest run src/components/AnalyzeTab.test.tsx`
Expected: PASS.

- [ ] **Step 5: Wire the handler in `MapWorkspace` + add the integration test**

In `frontend/src/components/MapWorkspace.tsx`, add `onCompareWith` to the `<AnalyzeTab ... />` props (both this task's Analyze render — inside the landing gate's `else` branch from Task 3):

```tsx
                  onCopyLink={() => buildShareUrl("analyze")}
                  onCompareWith={() => setActiveTab("compare")}
```

In `frontend/src/components/MapWorkspace.test.tsx`, add `within` to the testing-library import:

```tsx
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
```

and add the integration test:

```tsx
  it("bridges a looked-up address into the Compare tab as the anchor", async () => {
    vi.mocked(createSession).mockResolvedValue({ session_state: "ready" });
    vi.mocked(getDashboardSummary).mockResolvedValue(makeSummary());
    vi.mocked(analyzePlaces).mockResolvedValue({ summary_count: 1 });
    vi.mocked(getIncidentDetails).mockResolvedValue(makeIncidentDetails());
    vi.mocked(getNeighborhoodAnalysis).mockResolvedValue(makeNeighborhoodAnalysis());
    geocodeSearch.mockResolvedValue([{ label: "123 Main St", latitude: 47.61, longitude: -122.34, source: "test" }]);

    render(<MapWorkspace />);
    await screen.findByRole("heading", { name: /look up an address/i });
    fireEvent.change(screen.getByLabelText(/search an address/i), { target: { value: "123 Main" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    fireEvent.click(await screen.findByText("123 Main St"));

    fireEvent.click(await screen.findByRole("button", { name: /compare with another address/i }));

    expect(await screen.findByText("Compare addresses")).toBeInTheDocument();
    const list = screen.getByRole("list", { name: /addresses to compare/i });
    expect(within(list).getByText("123 Main St")).toBeInTheDocument();
  });
```

- [ ] **Step 6: Run both test files**

Run: `cd frontend && npx vitest run src/components/AnalyzeTab.test.tsx src/components/MapWorkspace.test.tsx`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/AnalyzeTab.tsx frontend/src/components/AnalyzeTab.test.tsx frontend/src/components/MapWorkspace.tsx frontend/src/components/MapWorkspace.test.tsx
git commit -m "feat(compare): compare bridge from single-address Analyze into Compare (slice C)"
```

---

### Task 5: Save a looked-up address to places

**Files:**
- Modify: `frontend/src/components/AnalyzeTab.tsx`
- Modify: `frontend/src/components/AnalyzeTab.test.tsx`
- Modify: `frontend/src/components/MapWorkspace.tsx`
- Modify: `frontend/src/components/MapWorkspace.test.tsx`

- [ ] **Step 1: Write the failing AnalyzeTab unit test**

In `frontend/src/components/AnalyzeTab.test.tsx`, add:

```tsx
  it("renders a save button that calls onSave", () => {
    const onSave = vi.fn();
    render(
      <AnalyzeTab
        selected={[]}
        analysis={{ startDate: "2026-01-01", endDate: "2026-06-30", radiusM: 250, offenseCategory: "", layer: "reported" }}
        availableRadii={[250]}
        running={false}
        neighborhood={{ radius_m: 250, analysis_start_date: "2026-01-01", analysis_end_date: "2026-06-30", offense_category: null, places: [], pairwise: [] }}
        onChange={vi.fn()}
        onRun={vi.fn()}
        onSave={onSave}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /save to my places/i }));
    expect(onSave).toHaveBeenCalledTimes(1);
  });
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npx vitest run src/components/AnalyzeTab.test.tsx`
Expected: FAIL — no `onSave` prop / button.

- [ ] **Step 3: Add the prop + button to `AnalyzeTab`**

In `frontend/src/components/AnalyzeTab.tsx`, add to `type Props`:

```tsx
  onCompareWith?: () => void;
  onSave?: () => void;
```

Add `onSave` to the destructured params. Then, immediately after the compare-bridge button block from Task 4, add:

```tsx
          {onSave && neighborhood && (
            <button type="button" className="mc-link-copy mc-compare-bridge" onClick={onSave}>
              Save to my places
            </button>
          )}
```

- [ ] **Step 4: Run to verify the AnalyzeTab test passes**

Run: `cd frontend && npx vitest run src/components/AnalyzeTab.test.tsx`
Expected: PASS.

- [ ] **Step 5: Add the handler in `MapWorkspace` + integration test**

In `frontend/src/components/MapWorkspace.tsx`, add the handler after `handleLookup` (from Task 3):

```tsx
  async function handleSaveLookup() {
    if (!lookupPoint) return;
    data.setError("");
    try {
      const created = await createPlace({
        display_label: lookupPoint.label,
        latitude: lookupPoint.latitude,
        longitude: lookupPoint.longitude,
        visit_count: 1,
        sensitivity_class: "normal",
      });
      // Set the selection directly (NOT selectPlaceIds) so the analysis context is NOT
      // invalidated — the saved place shares the looked-up coordinates, so the verdict on
      // screen stays valid. Then drop the ephemeral lookup + its draft marker.
      setSelectedIds(new Set([created.id]));
      setLookupPoint(null);
      pinDraft.setDraft(null);
      await data.refreshWithFallback("Saved, but dashboard totals could not refresh.");
    } catch {
      data.setError("Unable to save place. Try again.");
    }
  }
```

Pass it to `<AnalyzeTab ... />` (in the landing gate's `else` branch), only when a lookup is active:

```tsx
                  onCompareWith={() => setActiveTab("compare")}
                  onSave={lookupPoint ? handleSaveLookup : undefined}
```

In `frontend/src/components/MapWorkspace.test.tsx`, add:

```tsx
  it("saves a looked-up address to places on request", async () => {
    const saved: Place = { ...home, id: "s1", display_label: "123 Main St", latitude: 47.61, longitude: -122.34 };
    vi.mocked(createSession).mockResolvedValue({ session_state: "ready" });
    vi.mocked(getDashboardSummary).mockResolvedValueOnce(makeSummary()).mockResolvedValue(makeSummary([saved]));
    vi.mocked(analyzePlaces).mockResolvedValue({ summary_count: 1 });
    vi.mocked(getIncidentDetails).mockResolvedValue(makeIncidentDetails());
    vi.mocked(getNeighborhoodAnalysis).mockResolvedValue(makeNeighborhoodAnalysis());
    vi.mocked(createPlace).mockResolvedValue(saved);
    geocodeSearch.mockResolvedValue([{ label: "123 Main St", latitude: 47.61, longitude: -122.34, source: "test" }]);

    render(<MapWorkspace />);
    await screen.findByRole("heading", { name: /look up an address/i });
    fireEvent.change(screen.getByLabelText(/search an address/i), { target: { value: "123 Main" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    fireEvent.click(await screen.findByText("123 Main St"));

    fireEvent.click(await screen.findByRole("button", { name: /save to my places/i }));

    await waitFor(() => {
      expect(createPlace).toHaveBeenCalledWith({
        display_label: "123 Main St",
        latitude: 47.61,
        longitude: -122.34,
        visit_count: 1,
        sensitivity_class: "normal",
      });
    });
  });
```

- [ ] **Step 6: Run both test files**

Run: `cd frontend && npx vitest run src/components/AnalyzeTab.test.tsx src/components/MapWorkspace.test.tsx`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/AnalyzeTab.tsx frontend/src/components/AnalyzeTab.test.tsx frontend/src/components/MapWorkspace.tsx frontend/src/components/MapWorkspace.test.tsx
git commit -m "feat(compare): save a looked-up address to places (slice C)"
```

---

### Task 6: Full verification gate + roadmap tick

**Files:**
- Modify: `docs/ROADMAP.md`

- [ ] **Step 1: Run the full gate**

Run (from the worktree root): `make test-all`
Expected: PASS — `pytest` + `ruff check .` + frontend `npm test` (now 219 + new tests) + `npm run build` all green.

If `ruff` flags the frontend-only branch as touching Python (it should not — no `.py` changed), no action needed. If the frontend build surfaces an unused-import or type error, fix it inline and re-run.

- [ ] **Step 2: Tick the roadmap**

In `docs/ROADMAP.md`, in the Phase 5 decomposition list:

Change slice A's checkbox from `- [ ]` to `- [x]` (bookkeeping — it shipped in #94/#95). Change slice C's line from:

```markdown
- [ ] **Slice C — comparison-first landing** — lead the app with the compare flow. Not yet
  specced.
```

to:

```markdown
- [x] **Slice C — single-address entry → context → optional compare** — shipped: a fresh
  session leads with a single-address lookup (ephemeral inline-`points` path, no DB write)
  that flies the map and shows the address's reported-incident context on the reused Analyze
  tab, plus a one-click compare bridge that carries the looked-up address in as the anchor and
  an optional "Save to my places". Frontend-only; invariant untouched. Spec/plan:
  `docs/superpowers/{specs,plans}/2026-07-03-compare-single-address-entry*`.
```

- [ ] **Step 3: Commit**

```bash
git add docs/ROADMAP.md
git commit -m "docs(roadmap): tick Phase 5 slice C (single-address entry) + slice A bookkeeping"
```

- [ ] **Step 4: Hand off to finishing-a-development-branch**

The branch `feat/compare-single-address-entry` is ready for PR. Use the superpowers:finishing-a-development-branch skill to open the PR (or push + `gh pr create`) once the user confirms.

---

## Self-Review

**Spec coverage** (each spec section → task):
- §2 entry view `AddressLookup` → Task 1. ✓
- §3 ephemeral point + reuse Analyze via points + draft-pin map marker + auto-run → Tasks 2–3. ✓
- §4 compare bridge (anchor carried via `useCompareSet` seed) → Task 4. ✓
- §Decision 2 "Save to my places" (reuses `createPlace`, non-invalidating) → Task 5. ✓
- §Decision 3 no new tab / no hidden nav → landing gate keeps the 4 tabs; `AddressLookup` is not a `TabKey`. ✓
- §Decision 4 fresh-session gate (`data.places.length === 0 && !lookupPoint && !sharedPoints`, plus `!manualEntry`/`activeTab==="places"`/`!draft` for coherent escapes) → Task 3 step 3g. ✓
- §Decision 5 single subject (lookup clears selection; select clears lookup) → Task 3 steps 3e–3f. ✓
- §Architecture "remove `mc-empty` overlay" → Task 3 step 3h. ✓
- §Testing (AddressLookup unit; MapWorkspace points-path-no-persist, bridge; updated empty-state tests; `make test-all`) → Tasks 1, 3, 4, 6. ✓
- §Out of scope (no backend, no number-line CI, no pre-map screen, assistant not wired to lookup) → nothing in the plan violates these. ✓

**Placeholder scan:** No TBD/TODO; every code step carries full code. ✓

**Type consistency:** `ComparePoint` = `{ latitude, longitude, label }` (from `useCompareSet`) is what `lookupPoint`, the analyze `points`, and the synthesized `selected` all use; `handleLookup` builds it from a `GeocodeResult` (`{ label, latitude, longitude, source }`). `previewSearch(result: GeocodeResult)` matches its `usePinDraft` call site. `onCompareWith?: () => void` and `onSave?: () => void` are declared in `AnalyzeTab` Props and passed from `MapWorkspace`. `showLanding` references only in-scope values (`data.places`, `lookupPoint`, `sharedPoints`, `manualEntry`, `activeTab`, `pinDraft.draft`). ✓
```
