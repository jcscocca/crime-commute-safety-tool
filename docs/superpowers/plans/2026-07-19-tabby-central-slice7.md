# Tabby-Central Slice 7: Parity Checklist + Legacy Tab Retirement — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every Compare/Export capability gets a rail-side home (recorded in a committed parity checklist), auto-run flows land as thread cards instead of opening the legacy view, and then the legacy tabs, RailNav, and their dead chrome are deleted.

**Architecture:** Share-link/lookup/restored auto-runs keep `useCompare.run()` (the assistant tools can't take raw lat/lng points) but their results are synthesized into a LOCAL `AnalysisCardData` (`runId: null` — no export link, no badges) appended to the thread with a deterministic summary line; `railView` and the legacy views then have no remaining producer and are deleted wholesale: `CompareTab`, `ExportTab`, `RailNav`, `TabKey`, the BottomSheet `nav` slot, and the orphaned CSS. Rehomed before deletion: a **Run analysis** button + **Copy link** action in the ContextStrip editor; export privacy toggles + the Tableau CSV link in `ManagePlacesModal`; the product caveat line in the expanded card. The parity checklist is a committed doc mapping every retired capability → its new home → the test/E2E that proves it.

**Tech Stack:** React 18 + Vitest; no backend changes.

**Spec:** `docs/superpowers/specs/2026-07-19-tabby-central-redesign-design.md` (Migration section — this slice is the checklist "pass" and the deletion it gates). Reviews carried in: orphaned `tabpanel` roles die with the components; mobile `is-collapsed` CSS co-application ends (desktop `is-collapsed` rules remain — desktop still uses the boolean); `BottomSheet.tsx:94-98` snap heights deduplicate through `snapHeightPx` while that file is open.

**Worktree:** from `main`; usual setup. Baselines expected: backend 682, frontend 539.

---

## File structure

| File | Status | Responsibility |
| --- | --- | --- |
| `frontend/src/lib/localCard.ts` (+test) | create | `cardFromCompareResults` + `localSummaryLine` |
| `frontend/src/components/MapWorkspace.tsx` (+test) | modify | auto-runs → cards; railView removal; wiring |
| `frontend/src/components/ContextStrip.tsx` (+test) | modify | Run analysis + Copy link actions |
| `frontend/src/components/ManagePlacesModal.tsx` (+test) | modify | export privacy toggles + Tableau CSV link |
| `frontend/src/components/AnalysisCard.tsx` (+test) | modify | caveat line in expanded view |
| `frontend/src/components/CompareTab.tsx`, `ExportTab.tsx`, `RailNav.tsx`, `CompareAddressInput.tsx` (+tests) | delete | superseded |
| `frontend/src/components/BottomSheet.tsx` (+test) | modify | drop `nav` slot; dedupe snap heights |
| `frontend/src/lib/usePinDraft.ts` (+its consumers) | modify | drop the `setActiveTab` dep |
| `frontend/src/types.ts` | modify | drop `TabKey` |
| `frontend/src/styles/mapWorkspace.css` | modify | delete mc-tabs/mc-dock-slot/mc-railnav/mc-querybar-era rules; end mobile is-collapsed co-application |
| `docs/superpowers/specs/2026-07-19-tabby-central-slice7-parity.md` | create | the committed checklist |

Components that STAY (AnalysisCard imports them): `CompareVerdict`, `CompareRankedList`, `CompareRateNumberLine`, `PlaceContextCard`, `TrendSection`, `IncidentDetailsSection`, `MethodsAppendix`, `BaselineIntervalPlot`, `LocatorChip`, `PlaceChipStrip`, `PinDraftPopover`, `TrendChart`/`TrendSection` internals. Verify each deletion candidate's importers before deleting (grep).

---

### Task 1: Local cards for auto-run results

**Files:** Create `frontend/src/lib/localCard.ts` (+test); modify `frontend/src/components/MapWorkspace.tsx` (+test).

- [ ] **Step 1 (TDD, lib):**

```ts
// frontend/src/lib/localCard.ts
import type { AnalysisCardData, AnalysisSettings, IncidentDetailsResponse, NeighborhoodAnalysis, SiteComparison } from "../types";

/** Card synthesized from a client-run analysis (share links, lookups, restored
 * sessions run through useCompare — the assistant tools can't take raw points).
 * runId stays null: no run-scoped export, no server badges. */
export function cardFromCompareResults(input: {
  comparison: SiteComparison | null;
  neighborhood: NeighborhoodAnalysis | null;
  incidents: IncidentDetailsResponse | null;
  analysis: AnalysisSettings;
  placeIds: string[];
}): AnalysisCardData | null {
  const { comparison, neighborhood, incidents, analysis, placeIds } = input;
  if (!comparison && !neighborhood) return null;
  return {
    runId: null,
    kind: comparison ? "compare" : "analyze",
    placeIds,
    settings: {
      radius_m: analysis.radiusM,
      analysis_start_date: analysis.startDate,
      analysis_end_date: analysis.endDate,
      offense_category: analysis.offenseCategory || null,
      layer: analysis.layer,
    },
    comparison,
    neighborhood: comparison ? null : neighborhood,
    incidents: comparison ? null : incidents,
  };
}

export function localSummaryLine(card: AnalysisCardData, placeCount: number): string {
  const noun = placeCount === 1 ? "place" : "places";
  return card.kind === "compare"
    ? `Compared your ${placeCount} ${noun} — details in the card.`
    : `Pulled the reports around your ${noun} — details in the card.`;
}
```

Tests: comparison present → compare card with neighborhood/incidents nulled (matches the bridge's shape convention); neighborhood-only → analyze card; both null → null; settings frozen from the passed analysis (camelCase→snake_case mapping incl. "" category → null); summary lines.

- [ ] **Step 2 (MapWorkspace):** the auto-run consume effect currently does `setRailView("compare"); void compare.run();`. Change: drop the `setRailView` line and make the run's completion append the card — `useCompare.run()` resolves after `Promise.allSettled`; check its return/state contract (survey slice 3: state lands in `compare.comparison/neighborhood/incidents`). Wire via an effect keyed on run completion (e.g. `compare.running` false transition with fresh results + a `pendingCardRef` armed by the auto-run effect) OR — if `run()` returns a promise — await it and read the hook's state via a ref. Read `useCompare.ts` and pick the least invasive mechanism; the acceptance contract is: after an auto-run completes with results, exactly ONE `analysis_card` + one `tabby_text` summary land in the thread, and NONE land when the run yields no payloads (error path). Guard against double-append on re-renders (ref-armed, cleared on fire).
- [ ] **Step 3 (tests):** share-link mount → card on the rail (thread contains analysis_card with runId null; no export link rendered — extend an AnalysisCard assertion), single-fire preserved (call counts still 1); lookup → same; restored-session → same; error path (mocked rejection) → no card, no summary. The old assertions that these flows open the Compare view are REPLACED by rail-card assertions (this is the sanctioned behavioral change of the slice).
- [ ] **Step 4:** suites + tsc; commit `feat(rail): auto-run analyses land as local cards on the rail`.

---

### Task 2: Rehoming — run/copy-link/export controls + caveat

**Files:** `frontend/src/components/ContextStrip.tsx` (+test), `frontend/src/components/ManagePlacesModal.tsx` (+test), `frontend/src/components/AnalysisCard.tsx` (+test), `frontend/src/components/MapWorkspace.tsx` (+test).

- [ ] **Step 1 (ContextStrip):** the editor (open state) gains a footer row with two buttons: **Run analysis** (`onRun?: () => void` — disabled via `runDisabled?: boolean` when no places) and **Copy link** (`onCopyLink?: () => Promise<boolean> | boolean`, showing a transient "Copied" note on success — mirror CompareTab's copy-status idiom before deleting it). MapWorkspace wires `onRun` to the deterministic command path: 2+ saved → `compare_places`, 1 → `analyze_places` (reuse `runPanelCommand`'s arg building via a small shared helper or call it with the right command); `onCopyLink` wraps the existing `buildShareUrl` + clipboard write (read how CompareTab does the clipboard call today and reuse the mechanism). Tests: run button fires the right command per place count and is disabled with none; copy-link writes the URL and flashes the note.
- [ ] **Step 2 (ManagePlacesModal):** each place row gains an "Include in export" toggle (mirrors ExportTab's `onToggleExport` contract — `sensitivity_class` normal ↔ suppress_from_public_export; read ExportTab for the exact copy/aria before deleting it) and the modal footer gains a "Download Tableau CSV" link (`href` = the export href prop). MapWorkspace passes `exportHref={data.exportHref}` and the existing `onToggleExport` handler (move it from the ExportTab render). Tests: toggle calls updatePlace with the right sensitivity class both directions; link renders with the href.
- [ ] **Step 3 (AnalysisCard):** expanded view renders the product caveat line above `MethodsAppendix`: reuse the exact `REVISED_CAVEAT` string from CompareTab (move the constant into `frontend/src/lib/layerCopy.ts` or a suitable lib home, import in the card; CompareTab imports it too until Task 3 deletes it). Test: expanded card shows the caveat; compact doesn't.
- [ ] **Step 4:** suites + tsc; commit `feat(rail): rehome run, share link, export controls, and caveat`.

---

### Task 3: The deletion

**Files:** delete `CompareTab.tsx`, `ExportTab.tsx`, `RailNav.tsx`, `CompareAddressInput.tsx` (+ each `.test`); modify `MapWorkspace.tsx` (+test), `BottomSheet.tsx` (+test), `usePinDraft.ts`, `types.ts`, `mapWorkspace.css`.

- [ ] **Step 1 (grep gate):** for each deletion candidate, `grep -rn "<name>" frontend/src` — the only importers must be MapWorkspace/their own tests (CompareAddressInput: imported only by CompareTab). If anything else imports one (e.g. a lib), STOP and report.
- [ ] **Step 2 (MapWorkspace):** remove `railView` state entirely (the drawer body is always the rail; the `railView === "tabby"` conditional and the legacy branches go); remove the `nav={<RailNav .../>}` prop, `openLegacyView`-era imports, the CompareTab/ExportTab renders and their prop plumbing (`compare` results still feed map highlights via `useCompare` — keep the hook and `applyAssistant`/`invalidateAnalysisContext` paths; delete only the pane-rendering usage). `usePinDraft`: drop the `setActiveTab` dependency from its signature and MapWorkspace's call (its only use was legacy view routing — verify by reading it).
- [ ] **Step 3 (BottomSheet):** remove the `nav` prop and its render slot; dedupe the release-snap candidate heights through `snapHeightPx` (import from drawer.ts; keep the 120 bar constant consistent — move it into drawer.ts as the bar branch already returns 120). Desktop preset strip stays (it's the width control, not the tab nav).
- [ ] **Step 4 (types/CSS):** delete `TabKey` (grep first — RailNav was its last consumer besides MapWorkspace); CSS: delete `.mc-tabs*`, `.mc-dock-slot*`, `.mc-railnav*`, and CompareTab-only rules (`.mc-querybar*`, `.mc-analyze-actions`, `.mc-copy-status` IF now unused — grep each class name against `frontend/src` before deleting; keep anything AnalysisCard/ContextStrip reuses); end the mobile `is-collapsed` co-application (BottomSheet stops applying `is-collapsed`/`is-open` on mobile — `is-bar/is-half/is-full` are the mobile classes now; desktop keeps `is-collapsed`/`is-open`; adjust the mobile CSS block accordingly and verify the peek styling keys on `is-bar`).
- [ ] **Step 5 (test migration):** delete the four component test files; MapWorkspace tests: `openLegacyView`/`backToTabby` helpers die (everything is the rail now) — flows assert cards/chips/strip directly; protected classes (analysis payload/map effects/share-link single-fire/pin drafts/degraded) keep their assertions with the rail as the surface. Run the full suite and fix mechanically, investigating anything that fails outside the anticipated classes.
- [ ] **Step 6:** full suites + tsc + build; commit `feat(rail): retire the legacy Compare/Export views`.

---

### Task 4: The parity checklist document

**Files:** create `docs/superpowers/specs/2026-07-19-tabby-central-slice7-parity.md`.

- [ ] Write the table: every capability from the spec's Migration list (address add/save/remove; explicit run; exact date inputs; radius/category choices; share links; loading/error a11y announcements; layer disclosures; baseline detail; trends; incident rows; methods; export privacy toggles; run-scoped card exports; Tableau CSV) → its new home → the specific test name or E2E step that proves it. Every row must cite something that actually exists (grep the test names). Commit `docs(specs): slice 7 parity checklist — verified homes for retired surfaces`.

---

### Task 5: Gate + E2E + merge (coordinator)

- [ ] Full gate; E2E (desktop + mobile preset): share link → local card on the rail (no export link), map highlights intact; ContextStrip Run analysis + Copy link; manage modal export toggle + CSV link; expanded card caveat; no tab chrome anywhere; invariant sweep. Fresh-context final review against the parity checklist; squash-merge.

## Out of scope
- Verdict-text badges, subcategory freezing, multi-worker run-id threading (tracked separately)
- Any backend change
