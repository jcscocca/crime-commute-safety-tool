# Tabby-Central Slice 3: Inline Analysis Cards — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Assistant-driven analyses render as frozen cards inside the Tabby thread (compact + expanded), each with a run-scoped CSV export and deterministic follow-up chips — ending the bounce to the legacy Compare view for assistant flows.

**Architecture:** Tool results already carry plain-serializable payload slices (`comparison`/`neighborhood`/`incidents`); a new `analysis_card` thread item freezes those plus `settings_used` and a new backend-surfaced `analysis_run_id`. The card component recomposes the existing Compare result components (all payload-driven pure props per the survey) — compact by default, expanded via a drawer-width callback. The bridge stops emitting `tab` for analyze/compare and instead emits `card`. Follow-up chips are client-side deterministic templates keyed off the newest card's frozen settings, run as `/assistant/commands` (they also make degraded-mode chips real). `useAssistantTurn` gains turn-id + abort: a new send cancels the in-flight turn and stale events are ignored. Manual flows (share links, lookup auto-run, legacy Compare) are untouched this slice.

**Tech Stack:** FastAPI + SQLAlchemy (run ids, export param); React 18 + TS + Vitest.

**Spec:** `docs/superpowers/specs/2026-07-19-tabby-central-redesign-design.md` (Slice 3), plus three carried items from slice 2 reviews: suppress the duplicate summary bubble for settings-only command turns; follow-up chips make "chips keep working while degraded" observable; turn_id/abort serialization (deferred here from the spec's architecture section).

**Worktree:** dedicated worktree from `main`; `make install` + `cd frontend && npm install` once. Gate: backend `.venv/bin/python -m pytest tests -q` + `.venv/bin/python -m ruff check .`; frontend `npm test`, `npx tsc --noEmit`, `npm run build`.

---

## File structure

| File | Status | Responsibility |
| --- | --- | --- |
| `app/assistant/tools.py` | modify | return `analysis_run_id` from `_analyze_places` / `_compare_places` |
| `app/services/export_service.py` | modify | optional `run_id` scoping (ownership-checked) |
| `app/api/routes_exports.py` | modify | `run_id` query param on the public CSV route |
| `tests/test_assistant_tools.py`, `tests/test_exports_api.py` (or the existing export test file) | modify | run-id + scoping tests |
| `frontend/src/lib/threadItems.ts` (+test) | modify | `analysis_card` item kind |
| `frontend/src/lib/assistantBridge.ts` (+test) | modify | export `SettingsUsed`; `card` effect; drop `tab` |
| `frontend/src/lib/followupChips.ts` (+test) | create | deterministic follow-up chip templates |
| `frontend/src/components/AnalysisCard.tsx` (+test) | create | compact/expanded card composition |
| `frontend/src/components/AssistantPanel.tsx` (+test) | modify | render cards; persistent follow-up chip row |
| `frontend/src/lib/useAssistantTurn.ts` (+test) | modify | settings-only summary suppression; turn-id + abort |
| `frontend/src/api/client.ts` (+test) | modify | `signal` pass-through on SSE helpers |
| `frontend/src/components/MapWorkspace.tsx` (+test) | modify | append cards; expand→width; chips args-patch; export href base |
| `frontend/src/styles/mapWorkspace.css` | modify | card + chip-row styles |

---

### Task 1: Backend — surface `analysis_run_id` in analyze/compare tool results

**Files:** Modify `app/assistant/tools.py`; test `tests/test_assistant_tools.py`.

Per the survey, `_compare_places` (tools.py ~L289-332) already calls `analyze_selected_places(...)` to persist a run and discards the id; `_analyze_places` (~L227-286) runs the same persistence path. Read both and locate where the run row is created (follow `analyze_selected_places` into its service; it calls `create_analysis_run` from `app/services/analysis_runs.py` and its return value or the run object is available in the call chain).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_assistant_tools.py`, following its existing fixtures for a session with saved places and seeded analysis inputs (there are existing `_analyze_places`/`_compare_places` tests — mirror their setup exactly):

```python
def test_analyze_places_returns_analysis_run_id(...existing fixture args...):
    result = execute_tool(session, user_hash, "analyze_places", {...same args the existing analyze test uses...})
    run_id = result["result"]["analysis_run_id"]
    assert isinstance(run_id, str) and run_id
    # The id must reference a persisted run owned by this user.
    from app.models import AnalysisRun
    run = session.get(AnalysisRun, run_id)
    assert run is not None and run.user_id_hash == user_hash


def test_compare_places_returns_analysis_run_id(...):
    result = execute_tool(session, user_hash, "compare_places", {...same args the existing compare test uses...})
    assert result["result"]["analysis_run_id"]
```

(Adapt the `...` fixture/args placeholders to the file's real existing test parameters — copy the sibling test's setup verbatim; the new assertion lines are the substance.)

- [ ] **Step 2: Run to verify fail** — `.venv/bin/python -m pytest tests/test_assistant_tools.py -q` → FAIL (KeyError `analysis_run_id`).

- [ ] **Step 3: Implement**

Thread the created run's id back: if `analyze_selected_places` (or whichever service persists the run) doesn't return it, capture it there (return the id alongside its current return, or query `latest_analysis_run_id(session, user_id_hash)` immediately after the persistence call inside the tool handler — prefer returning it from the service if the change is ≤ a few lines; fall back to `latest_analysis_run_id` only if the service return is widely consumed). Add to BOTH result dicts:

```python
"analysis_run_id": run_id,
```

(`None` is acceptable only if persistence was skipped — if there's a code path that skips run creation, mirror it with `"analysis_run_id": None` and note it in your report.)

- [ ] **Step 4: Run to verify pass** — same command → PASS; full backend suite green.

- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat(assistant): analyze/compare tool results carry analysis_run_id"`

---

### Task 2: Backend — run-scoped export

**Files:** Modify `app/services/export_service.py`, `app/api/routes_exports.py`; test in the existing export API test file (find it: `grep -rl "place-summary.csv" tests/`).

- [ ] **Step 1: Write the failing tests**

In the export API test file, following its existing session/client idioms:

```python
def test_export_scopes_to_requested_run(...):
    # Arrange: two runs for the user (run the analysis twice via the existing
    # test helpers this file / test_assistant_tools.py already use), capture both ids.
    ...
    response = session_client.get(f"/exports/tableau/place-summary.csv?run_id={older_run_id}")
    assert response.status_code == 200
    # CSV rows reflect the older run (assert on a value that differs between runs,
    # e.g. incident counts after seeding differently, or simply that the endpoint
    # accepted the param and returned CSV with the header row).
    assert response.headers["content-type"].startswith("text/csv")


def test_export_rejects_foreign_or_unknown_run(session_client):
    response = session_client.get("/exports/tableau/place-summary.csv?run_id=not-a-real-run")
    assert response.status_code == 404


def test_export_without_run_id_unchanged(session_client):
    response = session_client.get("/exports/tableau/place-summary.csv")
    assert response.status_code == 200
```

(For the foreign-run case: also create a run under a DIFFERENT user hash and assert 404 when requesting it — ownership must be enforced, not just existence.)

- [ ] **Step 2: Run to verify fail** — 404-test fails today (unknown query params are ignored → 200).

- [ ] **Step 3: Implement**

`app/services/export_service.py` — extend the signature:

```python
def tableau_place_summary_csv(session: Session, user_id_hash: str, run_id: str | None = None) -> str:
    if run_id is not None:
        run = session.get(AnalysisRun, run_id)
        if run is None or run.user_id_hash != user_id_hash:
            raise LookupError("analysis run not found")
        scoped_run_id = run.id
    else:
        scoped_run_id = latest_analysis_run_id(session, user_id_hash)
    ...  # existing body, using scoped_run_id where it used the latest id
```

(Import `AnalysisRun` from `app.models`. Keep the no-param behavior byte-identical.)

`app/api/routes_exports.py` — the public route gains `run_id: str | None = None` as a query parameter, passes it through, and maps `LookupError` to `HTTPException(404, "Analysis run not found.")`. Internal route unchanged. The path itself is unchanged, so `PUBLIC_PATHS` needs no edit — verify `tests/test_internal_surface.py` still passes.

- [ ] **Step 4: Run to verify pass** — export tests + `tests/test_internal_surface.py` + full suite green; ruff clean.

- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat(exports): run-scoped place-summary CSV with ownership check"`

---

### Task 3: Frontend libs — `analysis_card` item + bridge card effect

**Files:** Modify `frontend/src/lib/threadItems.ts` (+test), `frontend/src/lib/assistantBridge.ts` (+test), `frontend/src/types.ts`.

- [ ] **Step 1: Types + failing tests**

`threadItems.ts` — extend the union and keep API mapping silent on cards:

```ts
import type { AnalysisCardData } from "./assistantBridge";

export type ThreadItem =
  | { kind: "user_text"; text: string }
  | { kind: "tabby_text"; text: string }
  | { kind: "receipt"; text: string }
  | { kind: "notice"; text: string }
  | { kind: "analysis_card"; card: AnalysisCardData };
```

(`toApiMessages` already maps only user/tabby kinds — add a test asserting an `analysis_card` item is skipped.)

`assistantBridge.ts` — export the settings type and the card data type; add `card` to the effect; drop `tab`:

```ts
export type SettingsUsed = { ...existing private type, now exported... };

export type AnalysisCardData = {
  runId: string | null;
  kind: "analyze" | "compare";
  placeIds: string[];
  settings: SettingsUsed;
  comparison: SiteComparison | null;
  neighborhood: NeighborhoodAnalysis | null;
  incidents: IncidentDetailsResponse | null;
};
```

In `frontend/src/types.ts`, `AssistantToolEffect`: remove the `tab?: TabKey` field, add `card?: AnalysisCardData` (import type from the bridge — if that creates an import cycle, move `AnalysisCardData` into `types.ts` instead and have the bridge import it; pick whichever direction the existing imports already flow).

Bridge cases for `analyze_places` / `compare_places`: keep `selection`/`settings`/payload/`refetchSummary` exactly as today, REMOVE `tab: "compare"`, and add:

```ts
card: {
  runId: typeof result.analysis_run_id === "string" ? result.analysis_run_id : null,
  kind: "analyze",            // "compare" in the compare_places case
  placeIds: Array.isArray(result.place_ids) ? (result.place_ids as string[]) : [],
  settings: (result.settings_used as SettingsUsed) ?? {},
  comparison: null,           // compare_places: (result.comparison as SiteComparison) ?? null
  neighborhood: (result.neighborhood as NeighborhoodAnalysis) ?? null,   // compare_places: null
  incidents: (result.incidents as IncidentDetailsResponse) ?? null,     // compare_places: null
},
```

Tests (`assistantBridge.test.ts`): update the two existing analyze/compare expectations (no `tab`, `card` present with runId/kind/settings), plus a case asserting a missing `analysis_run_id` yields `runId: null`.

- [ ] **Step 2: Run to verify fail, implement, pass** — `npm test -- src/lib/threadItems.test.ts src/lib/assistantBridge.test.ts`. Note: `MapWorkspace.tsx` still references `effect.tab` — TypeScript will flag it; that line is removed in Task 6, so for THIS commit keep compilation green by removing the `if (effect.tab) setRailView(effect.tab);` line now (it is dead once the bridge stops emitting `tab`) while leaving everything else in MapWorkspace untouched. Run the MapWorkspace suite; tests that asserted the assistant analyze/compare flows switch to the Compare view will fail — mark them for Task 6 by SKIPPING nothing: fix them now to assert the flow does NOT leave the rail (`screen.getByLabelText("Analyst message")` still present) but defer card-content assertions to Task 6. Keep all non-assistant tests green.

- [ ] **Step 3: Commit** — `git add -A && git commit -m "feat(rail): analysis_card thread item + bridge card effect (no more tab bounce)"`

---

### Task 4: Frontend lib — follow-up chip templates

**Files:** Create `frontend/src/lib/followupChips.ts` (+test).

- [ ] **Step 1: Write the failing tests**

```ts
// frontend/src/lib/followupChips.test.ts
import { describe, expect, it } from "vitest";

import { followupChipsFor } from "./followupChips";

const settings = {
  radius_m: 250,
  analysis_start_date: "2026-01-01",
  analysis_end_date: "2026-07-19",
  offense_category: null,
  layer: "reported" as const,
};

describe("followupChipsFor", () => {
  it("offers the next radius up, a category narrow, and a layer switch", () => {
    const chips = followupChipsFor("analyze", settings, [250, 500, 1000]);
    expect(chips.map((c) => c.label)).toEqual([
      "Widen to 500 m",
      "Property only",
      "Check 911 calls",
    ]);
    expect(chips[0]).toMatchObject({
      command: "analyze_places",
      argsPatch: { radii_m: [500] },
      settingsPatch: { radius_m: 500 },
    });
    expect(chips[1].argsPatch).toEqual({ offense_category: "PROPERTY" });
    expect(chips[2].argsPatch).toEqual({ layer: "calls" });
  });

  it("tightens instead when already at the largest radius, and widens category when narrowed", () => {
    const chips = followupChipsFor(
      "compare",
      { ...settings, radius_m: 1000, offense_category: "PROPERTY" },
      [250, 500, 1000],
    );
    expect(chips.map((c) => c.label)).toEqual([
      "Tighten to 500 m",
      "All categories",
      "Check 911 calls",
    ]);
    expect(chips[0].command).toBe("compare_places");
    expect(chips[0].argsPatch).toEqual({ radius_m: 500 });
    expect(chips[1].argsPatch).toEqual({ offense_category: "ALL" });
  });

  it("offers police reports when on another layer", () => {
    const chips = followupChipsFor("analyze", { ...settings, layer: "calls" }, [250, 500]);
    expect(chips[2].label).toBe("Back to police reports");
    expect(chips[2].argsPatch).toEqual({ layer: "reported" });
  });
});
```

- [ ] **Step 2: Run to verify fail**, then implement:

```ts
// frontend/src/lib/followupChips.ts
import type { AssistantCommandName } from "../api/client";
import type { SettingsUsed } from "./assistantBridge";

export type FollowupChip = {
  label: string;
  command: AssistantCommandName;
  /** Merged over the re-run command's arguments (field shapes per command). */
  argsPatch: Record<string, unknown>;
  /** The settings delta the chip represents (used only for labeling/receipts). */
  settingsPatch: Partial<SettingsUsed>;
};

/** Deterministic follow-ups for the newest analysis card. No LLM involved —
 * these must keep working in degraded mode. */
export function followupChipsFor(
  kind: "analyze" | "compare",
  settings: SettingsUsed,
  availableRadii: number[],
): FollowupChip[] {
  const command: AssistantCommandName = kind === "compare" ? "compare_places" : "analyze_places";
  const radii = availableRadii.length > 0 ? availableRadii : [250, 500, 1000];
  const sorted = [...radii].sort((a, b) => a - b);
  const current = settings.radius_m ?? sorted[0];
  const index = sorted.indexOf(current);
  const chips: FollowupChip[] = [];

  const next = index >= 0 && index < sorted.length - 1 ? sorted[index + 1] : null;
  const prev = index > 0 ? sorted[index - 1] : null;
  const radius = next ?? prev;
  if (radius !== null) {
    const radiusArgs = command === "analyze_places" ? { radii_m: [radius] } : { radius_m: radius };
    chips.push({
      label: `${next !== null ? "Widen" : "Tighten"} to ${radius} m`,
      command,
      argsPatch: radiusArgs,
      settingsPatch: { radius_m: radius },
    });
  }

  if (settings.offense_category) {
    chips.push({
      label: "All categories",
      command,
      argsPatch: { offense_category: "ALL" },
      settingsPatch: { offense_category: null },
    });
  } else {
    chips.push({
      label: "Property only",
      command,
      argsPatch: { offense_category: "PROPERTY" },
      settingsPatch: { offense_category: "PROPERTY" },
    });
  }

  if (settings.layer === "reported" || settings.layer === undefined) {
    chips.push({
      label: "Check 911 calls",
      command,
      argsPatch: { layer: "calls" },
      settingsPatch: { layer: "calls" },
    });
  } else {
    chips.push({
      label: "Back to police reports",
      command,
      argsPatch: { layer: "reported" },
      settingsPatch: { layer: "reported" },
    });
  }

  return chips;
}
```

Backend note for the reviewer chain: `offense_category: "ALL"` clears the filter on the analyze/compare arg models ONLY if those models accept it — check `AnalyzePlacesArgs`/`ComparePlacesByNameArgs` in `app/assistant/tools.py`. If they treat `offense_category: None`/omitted as all-reported and don't know the `ALL` sentinel (that sentinel exists on `UpdateFiltersArgs` only), then the chip must instead OMIT the field and the re-run builder in Task 6 must strip it: change `argsPatch` to `{ offense_category: null }` and have the arg-builder drop null/undefined entries before sending. Resolve this against the real models during implementation and make the unit test match the resolved contract — this is the one deliberately open point in this file.

- [ ] **Step 3: Pass + commit** — `git add -A && git commit -m "feat(rail): deterministic follow-up chip templates"`

---

### Task 5: `AnalysisCard` component

**Files:** Create `frontend/src/components/AnalysisCard.tsx` (+`.test.tsx`); CSS additions in `frontend/src/styles/mapWorkspace.css`.

Compact: header (kind label + frozen-settings line + run-scoped export link when `runId` + expand toggle), verdict content (comparison → `CompareVerdict` + `CompareRateNumberLine` from `toCompareVerdict(comparison)`; else one line per `neighborhood.places` entry using the existing verdict-copy helper — read `frontend/src/lib/verdictCopy.ts` for the exact function and reuse it), an incident count line, and **category mini-bars**: a pure helper in the component file `categoryCounts(incidents: IncidentDetailsResponse | null): { label: string; count: number }[]` aggregating `incidents.incidents` by offense category (reuse `categoryLabel`), rendered as small proportional inline bars (`div.mc-card-minibar` with width % of the max count; skip entirely when no incidents). Include a unit test for `categoryCounts` (export it). Spec deviation, deliberate: the spec's compact "trend sparkline" is NOT rendered compact — trend data requires a per-card fetch, so trends appear only in the expanded view via `TrendSection`; note this in the final report. Expanded (toggle → `onExpandChange(true)`): adds `CompareRankedList` (when comparison; `expansionByOptionId` omitted), per-place `PlaceContextCard` grid (when neighborhood; recompute `domainMax` via `plotDomainMax(neighborhood.places)`, `windowLabel` from the frozen dates, `locator={null}`, omit hover/fly callbacks — check the real prop optionality in `PlaceContextCard.tsx` and pass the minimal viable set), `TrendSection` (`neighborhood`, frozen `settings.layer`, frozen `settings.offense_category ?? null`), `IncidentDetailsSection` (`details`, `layout="table"`), `MethodsAppendix`. All props come from the frozen card — never from live dashboard state.

- [ ] **Step 1: Write the failing tests** (`AnalysisCard.test.tsx`, jsdom + Testing Library):

1. compact analyze card renders the settings line ("250 m", dates, "All reported"/category label, layer noun), one line per place, and NO trend/incident sections;
2. compact compare card renders the `CompareVerdict` callout text (feed a minimal `SiteComparison` fixture — copy one from `compareVerdict.test.ts` / `CompareTab.test.tsx` fixtures);
3. export link renders with `href` containing `?run_id=<id>` when `runId` set, absent when null;
4. clicking Expand calls `onExpandChange(true)` and renders the expanded sections (assert `MethodsAppendix` text and the incident-details table appear); collapse calls `onExpandChange(false)`;
5. expanded card mocks `useTrends`-driven `TrendSection` the way `TrendSection.test.tsx` does (mirror its mocking of the trends fetch) and passes the FROZEN layer/category through (assert on the mock's received args).

Write the fixtures by copying the smallest existing ones from the named test files — do not invent payload shapes.

- [ ] **Step 2: Implement** with props:

```ts
type Props = {
  card: AnalysisCardData;
  expanded: boolean;
  onExpandChange: (expanded: boolean) => void;
  exportHrefBase: string; // e.g. "/exports/tableau/place-summary.csv"
};
```

Root `div.mc-card` (+`is-expanded`); header `div.mc-card-head` with `.mc-card-kind` ("Analysis"/"Comparison"), `.mc-card-settings` (reuse the ContextStrip summary formatting helpers — `categoryLabel`, `incidentNoun`), export `<a className="mc-card-export" href={`${exportHrefBase}?run_id=${card.runId}`} download>` when `runId`, and an expand `<button aria-expanded>`. CSS (append after the ctx block): `.mc-card{border:1px solid var(--border);border-radius:10px;padding:8px 10px;display:grid;gap:8px;background:var(--surface-sunken);}` `.mc-card-head{display:flex;align-items:center;gap:8px;flex-wrap:wrap;}` `.mc-card-kind{font-family:var(--f-mono);font-size:10px;text-transform:uppercase;letter-spacing:.05em;color:var(--text-dim);}` `.mc-card-settings{font-family:var(--f-mono);font-size:10.5px;color:var(--text-dim);}` `.mc-card-export{margin-left:auto;font-size:11.5px;color:var(--accent-deep);}` plus `.mc-card.is-expanded{background:var(--surface);}`.

- [ ] **Step 3: Pass + commit** — `git add -A && git commit -m "feat(rail): AnalysisCard — frozen compact/expanded analysis rendering"`

---

### Task 6: Integration — cards in the thread, chips row, width toggle, export base

**Files:** Modify `frontend/src/components/AssistantPanel.tsx` (+test), `frontend/src/components/MapWorkspace.tsx` (+test), `frontend/src/lib/useAssistantTurn.ts` (+test).

- [ ] **Step 1: `useAssistantTurn` — settings-only summary suppression (TDD)**

New test: a COMMAND turn whose only tool event is `update_filters` commits NO `tabby_text` (the receipt covers it); a command turn with an `analyze_places` tool event still commits the summary; chat turns always commit. Implement inside `runTurn`: track `let sawTool = false; let settingsOnly = true;` — on tool events set `sawTool = true` and `settingsOnly &&= String(event.data.tool_name) === "update_filters"`; commit becomes `if (!errored && text.trim() && !(kind === "command" && sawTool && settingsOnly)) append(...)`.

- [ ] **Step 2: `AssistantPanel` — cards + persistent chip row (TDD)**

New props (added to the existing presentational set):

```ts
followupChips: FollowupChip[];
onFollowupChip: (chip: FollowupChip) => void;
expandedCardIndex: number | null;
onCardExpandChange: (index: number, expanded: boolean) => void;
exportHrefBase: string;
```

Render `analysis_card` items in the thread map: `<AnalysisCard card={item.card} expanded={expandedCardIndex === index} onExpandChange={(e) => onCardExpandChange(index, e)} exportHrefBase={exportHrefBase} />`. Below the thread log (above `contextStrip`), when `followupChips.length > 0 && !busy`, render `div.mc-followups` of `mc-chip` buttons calling `onFollowupChip(chip)`; command chips are NOT disabled when `offline` (they're the degraded path), and with this row present, update `OFFLINE_COMPOSER_HINT` back to "Tabby can't reach the case files — chips and filters still work." (it's truthful now). Tests: card renders in thread; chip row renders when chips provided and hidden while busy; chip click forwards the chip object; offline leaves follow-up chips enabled (this is now REAL integration-visible behavior); `displayItems` draft-fold index math still right with card items present (the draft key must not collide — it appends at `items.length` as before).

- [ ] **Step 3: `MapWorkspace` — wiring (TDD via the workspace suite)**

- `applyAssistantToolResult`: when `effect.card`, `thread.append({ kind: "analysis_card", card: effect.card })`. (The `effect.tab` line is already gone from Task 3.) Everything else (selection/settings/receipts/`compare.applyAssistant` for map highlights/refetchSummary) stays — cards do not replace map effects.
- Expansion state: `const [expandedCard, setExpandedCard] = useState<number | null>(null);` and a width memory `const prevWidthRef = useRef<number | null>(null);`. Handler:

```ts
function handleCardExpandChange(index: number, expanded: boolean) {
  if (expanded) {
    if (prevWidthRef.current === null) prevWidthRef.current = drawer.collapsed ? null : drawer.widthPx;
    setExpandedCard(index);
    if (!isMobile) onPreset("wide");
    else setDrawerCollapsed(false);
  } else {
    setExpandedCard(null);
    if (!isMobile && prevWidthRef.current !== null) onDrawerResize(prevWidthRef.current);
    prevWidthRef.current = null;
  }
}
```

- Follow-up chips: derive from the newest card — `const latestCard = [...thread.items].reverse().find((i) => i.kind === "analysis_card")?.card ?? null;` then `const followupChips = latestCard ? followupChipsFor(latestCard.kind, latestCard.settings, data.availableRadii) : [];`. Handler `handleFollowupChip(chip)`: re-run against the card's own scope with the patch merged over the frozen settings (NOT current dashboard state):

```ts
function handleFollowupChip(chip: FollowupChip) {
  if (!latestCard) return;
  const s = latestCard.settings;
  const base: Record<string, unknown> = {
    place_ids: latestCard.placeIds,
    analysis_start_date: s.analysis_start_date ?? null,
    analysis_end_date: s.analysis_end_date ?? null,
    layer: s.layer,
    ...(chip.command === "analyze_places"
      ? { radii_m: [s.radius_m ?? analysis.radiusM] }
      : { radius_m: s.radius_m ?? analysis.radiusM }),
    ...(s.offense_category ? { offense_category: s.offense_category } : {}),
  };
  const args = { ...base, ...chip.argsPatch };
  // Strip null/undefined so omitted-means-all fields don't hard-fail validation.
  for (const key of Object.keys(args)) if (args[key] == null) delete args[key];
  void turn.runCommand(chip.label, chip.command, args);
}
```

- Panel props: `followupChips`, `onFollowupChip: handleFollowupChip`, `expandedCardIndex: expandedCard`, `onCardExpandChange: handleCardExpandChange`, `exportHrefBase: data.exportHref` (it's already the CSV path; if it can carry query params in some deployments, split on `?` — check `useDashboardData.ts:98` and normalize).
- Workspace tests: (a) assistant analyze flow (existing mock) now appends a card — assert the card's settings line + place line appear on the rail and the composer is still present (no view switch); (b) follow-up chip click issues `streamAssistantCommand` with the FROZEN card settings + patch (mock a card-producing analyze first, then click "Widen to 500 m", assert `radii_m: [500]` and the card's dates, not the live dashboard's if they differ); (c) expand → `onPreset`-driven width change (assert the drawer width prop passed to BottomSheet changes and restores on collapse); (d) export link href contains `run_id`.

- [ ] **Step 4: Suite + commit** — full `npm test` + `tsc` green. `git add -A && git commit -m "feat(rail): analysis cards land in the thread with follow-up chips and width toggle"`

---

### Task 7: Turn id + abort in `useAssistantTurn`

**Files:** Modify `frontend/src/api/client.ts` (+test), `frontend/src/lib/useAssistantTurn.ts` (+test).

Behavior change (spec's turn serialization): a new `sendChat`/`runCommand` while a turn is in flight ABORTS the old turn and starts the new one (newest intent wins — replaces the slice-2 "ignore" behavior). Stale-turn events must apply nothing; an aborted turn appends no notice and never touches `offline`.

- [ ] **Step 1: Client signal pass-through (TDD)**

`streamAssistantSse(path, payload, handlers, signal?: AbortSignal)` → `fetch(..., { signal })`; both public wrappers gain the optional last param. Test: aborting the controller rejects the stream promise with an `AbortError`-named error (use a fetch mock that returns a never-resolving body read and honors signal abortion — mirror the existing fetch-mock idiom; asserting `fetch` receives the signal object is sufficient if simulating mid-stream abort is awkward).

- [ ] **Step 2: Hook turn-id/abort (TDD)**

Tests (rewrite the two in-flight tests, add two):
1. "a new send aborts the in-flight turn and runs" — gated first stream; second `sendChat` → first stream's signal aborted (assert via the signal passed to the first mock call), second stream called; both user turns appended (the first user_text stays — it was sent);
2. "an aborted turn appends no notice and leaves offline untouched";
3. "stale events after abort are ignored" — the first mock keeps calling `onEvent` with tokens after abort; assert draft reflects only the second turn's tokens;
4. re-entrancy without abort races: rapid double-click of the SAME chip label within one tick — second call aborts first; total `streamAssistantCommand` calls = 2, appends = 2 user_text (accepted: abort-and-replace supersedes dedupe; note this in the test comment).

Implementation sketch (adapt to the file):

```ts
const turnSeq = useRef(0);
const abortRef = useRef<AbortController | null>(null);

const runTurn = useCallback(async (kind, start) => {
  abortRef.current?.abort();
  const controller = new AbortController();
  abortRef.current = controller;
  const myTurn = ++turnSeq.current;
  const live = () => turnSeq.current === myTurn;
  // reset draft/status/toolActivity/busy as today
  try {
    await start((event) => { if (!live()) return; /* existing event handling */ }, controller.signal);
    if (!live()) return;
    // existing commit/notice/offline logic
  } catch (error) {
    if ((error as Error)?.name === "AbortError" || controller.signal.aborted) return;
    if (!live()) return;
    // existing catch logic
  } finally {
    if (live()) { setDraft(""); setStatusLine(""); setBusy(false); }
  }
}, [append, onToolResult]);
```

Drop the `inFlight` ref and the early-return guards in `sendChat`/`runCommand` (abort-and-replace supersedes them); `start` now receives `(onEvent, signal)` and forwards the signal to the stream call.

- [ ] **Step 3: Full frontend suite green** (update any test relying on the old ignore behavior), `tsc` clean. Commit: `git add -A && git commit -m "feat(rail): newest-intent-wins — turn abort + stale-event guard"`

---

### Task 8: Gate + E2E

- [ ] Full gate: backend pytest + ruff; frontend test + tsc + build.
- [ ] E2E via the `/verify` recipe (fresh port + uniquely named launch config): (a) share-link seed → Back to Tabby → analyze chip → an analysis CARD renders on the rail (no view switch), with settings line + verdict line; (b) follow-up chip "Widen to 500 m" → new card at 500 m + receipt + context strip follows; (c) expand → drawer widens, trend chart + incident table + methods render, collapse restores width; (d) export link downloads CSV with `run_id` param (assert the network request + 200); (e) free text with LLM down → composer disables, follow-up chips REMAIN and still run (the degraded promise, now visible); (f) invariant sweep.
- [ ] Fresh-context final review of the whole branch (diff + acceptance criteria), then squash-merge to `main` per the merge-and-continue workflow.

## Out of scope (later slices)

- Presence badges + badge descriptors (Slice 4); proactive onboarding/place-added moments + auto-run audit (Slice 5); mobile snap mechanics (Slice 6); legacy tab deletion + parity checklist incl. orphaned tabpanel roles (Slice 7).
- Unsaved-pin chip semantics (product call parked with Slice 5's pin-drop proactivity).
