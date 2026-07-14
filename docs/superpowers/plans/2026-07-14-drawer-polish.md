# Drawer Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Analysis greets returning users on load (persisted selection + auto-run), shared-view chips exit-and-select instead of playing dead, and places can be renamed inline in the manage modal.

**Architecture:** A new `usePersistedSelection` hook owns the `selectedIds` state (restore-once from localStorage when places arrive, persist on change); MapWorkspace gains a `pendingAutoRun` flag effect that fires `runAnalyze` AFTER the restored selection commits (the `useAnalyze` hook reads `selectedIds` per-render, so a same-tick call would use stale ids). The shared-exit and rename items are small handler/prop additions. Spec: `docs/superpowers/specs/2026-07-14-drawer-polish-design.md`.

**Tech Stack:** React + TypeScript + Vite (vitest). Frontend-only — the rename PATCH endpoint already exists (`app/api/routes_public_places.py:49`, partial `ManualPlaceUpdate`, `display_label` min length 1 / max 120).

**Verification gate:** `make test-all` before the PR.

## Key facts (verified against main at 000a95e)

- `selectedIds` lives at `MapWorkspace.tsx:50` (`useState<Set<string>>(new Set())`). `data.places` derives from the dashboard summary (`useDashboardData.ts:96`) — empty until the summary fetch lands, so "initial places load" = first render with `data.places.length > 0`.
- `useAnalyze({ selectedIds, ... })` (MapWorkspace.tsx:124) snapshots `selectedIds` per render — `runAnalyze` called in the same tick as `setSelectedIds` uses the OLD set. Hence the pending-flag pattern.
- An existing mount effect (~MapWorkspace.tsx:136) auto-runs for `initialView` (restored share links), and another (~line 190) re-runs for `lookupPoint`/`sharedPoints`. The new auto-run must skip when `initialView`, `lookupPoint`, or `sharedPoints` is present so it never double-fires.
- `handleToggleSelect` (MapWorkspace.tsx:~222) is the single chip/list toggle path.
- `handleLookup` clears `selectedIds` — so a lookup session persists an empty set; by design the fallback-to-all rule turns a persisted-empty set into "all places" next session (documented behavior, not a bug).
- localStorage helper style to copy: `frontend/src/lib/drawerStorage.ts` (try/catch, module functions).
- client.ts patterns: `createPlace`/`deletePlace` at `frontend/src/api/client.ts:90,106`.
- ManagePlacesModal list rows render label at `frontend/src/components/ManagePlacesModal.tsx` (`<div className="nm">{place.display_label}</div>`), actions in `<div className="right">`.

---

### Task 0: Worktree setup

- [ ] **Step 1:**

```bash
cd /Users/jscocca/Repos/waypoint
git worktree add ../waypoint-polish -b drawer-polish main
cd ../waypoint-polish
ln -s /Users/jscocca/Repos/waypoint/.venv .venv
ln -s /Users/jscocca/Repos/waypoint/frontend/node_modules frontend/node_modules
echo ".venv" >> "$(git rev-parse --git-path info/exclude)"
echo "frontend/node_modules" >> "$(git rev-parse --git-path info/exclude)"
cd frontend && npx vitest run src/lib/useTheme.test.ts
```

Expected: green. All tasks run in `../waypoint-polish`.

---

### Task 1: usePersistedSelection hook

**Files:**
- Create: `frontend/src/lib/usePersistedSelection.ts`
- Create: `frontend/src/lib/usePersistedSelection.test.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/lib/usePersistedSelection.test.ts`:

```tsx
// @vitest-environment jsdom
import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { usePersistedSelection } from "./usePersistedSelection";
import type { Place } from "../types";

const KEY = "compcat.selection";

function place(id: string): Place {
  return {
    id,
    display_label: id,
    latitude: 47.6,
    longitude: -122.3,
    visit_count: 1,
    total_dwell_minutes: null,
    inferred_place_type: "manual",
    sensitivity_class: "normal",
  } as Place;
}

beforeEach(() => localStorage.clear());

describe("usePersistedSelection", () => {
  it("stays empty and unrestored while places have not loaded", () => {
    const { result } = renderHook(() => usePersistedSelection([]));
    expect(result.current.selectedIds.size).toBe(0);
    expect(result.current.restored).toBe(false);
  });

  it("restores the stored selection filtered to existing places", () => {
    localStorage.setItem(KEY, JSON.stringify(["p1", "gone"]));
    const { result } = renderHook(() => usePersistedSelection([place("p1"), place("p2")]));
    expect(result.current.restored).toBe(true);
    expect(Array.from(result.current.selectedIds)).toEqual(["p1"]);
  });

  it("falls back to all places when nothing stored is valid", () => {
    localStorage.setItem(KEY, JSON.stringify(["gone"]));
    const { result } = renderHook(() => usePersistedSelection([place("p1"), place("p2")]));
    expect(Array.from(result.current.selectedIds).sort()).toEqual(["p1", "p2"]);
  });

  it("falls back to all places when the key is absent or unparseable", () => {
    localStorage.setItem(KEY, "{not json");
    const { result } = renderHook(() => usePersistedSelection([place("p1")]));
    expect(Array.from(result.current.selectedIds)).toEqual(["p1"]);
  });

  it("persists changes made after restore", () => {
    const { result } = renderHook(() => usePersistedSelection([place("p1"), place("p2")]));
    act(() => result.current.setSelectedIds(new Set(["p2"])));
    expect(JSON.parse(localStorage.getItem(KEY) ?? "[]")).toEqual(["p2"]);
  });

  it("does not clobber storage before restore happens", () => {
    localStorage.setItem(KEY, JSON.stringify(["p1"]));
    renderHook(() => usePersistedSelection([]));
    expect(JSON.parse(localStorage.getItem(KEY) ?? "[]")).toEqual(["p1"]);
  });

  it("restores only once even as places refresh", () => {
    localStorage.setItem(KEY, JSON.stringify(["p1"]));
    const { result, rerender } = renderHook(({ places }) => usePersistedSelection(places), {
      initialProps: { places: [place("p1"), place("p2")] },
    });
    act(() => result.current.setSelectedIds(new Set(["p2"])));
    rerender({ places: [place("p1"), place("p2"), place("p3")] });
    expect(Array.from(result.current.selectedIds)).toEqual(["p2"]);
  });
});
```

- [ ] **Step 2:** `cd frontend && npx vitest run src/lib/usePersistedSelection.test.ts` — expect FAIL (unresolvable import).

- [ ] **Step 3: Implement**

Create `frontend/src/lib/usePersistedSelection.ts`:

```tsx
import { useCallback, useRef, useState } from "react";

import type { Place } from "../types";

// New keys get the new brand; legacy waypoint.*/wp-* keys stay (identifier renames
// are out of scope for the rebrand).
const STORAGE_KEY = "compcat.selection";

function loadStored(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const parsed: unknown = raw === null ? [] : JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((id): id is string => typeof id === "string") : [];
  } catch {
    return [];
  }
}

function save(ids: Set<string>): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(Array.from(ids)));
  } catch {
    // private mode / disabled storage: selection degrades to per-session
  }
}

// Owns the drawer's selected-place ids: restores the persisted set once when places
// first arrive (filtered to ids that still exist, falling back to ALL places so a
// returning session always has an analyzable selection), persists every change after.
export function usePersistedSelection(places: Place[]) {
  const [selectedIds, setSelectedIdsState] = useState<Set<string>>(new Set());
  const restoredRef = useRef(false);

  if (!restoredRef.current && places.length > 0) {
    restoredRef.current = true;
    const existing = new Set(places.map((p) => p.id));
    const valid = loadStored().filter((id) => existing.has(id));
    setSelectedIdsState(new Set(valid.length > 0 ? valid : places.map((p) => p.id)));
  }

  const setSelectedIds = useCallback((next: Set<string> | ((current: Set<string>) => Set<string>)) => {
    setSelectedIdsState((current) => {
      const resolved = typeof next === "function" ? next(current) : next;
      if (restoredRef.current) save(resolved);
      return resolved;
    });
  }, []);

  return { selectedIds, setSelectedIds, restored: restoredRef.current };
}
```

(Restore runs during render via the ref guard — the same lazy-init trick React docs use for adjusting state on prop change; it avoids a flash frame where all chips render unchecked. The updater-form support matters: MapWorkspace call sites use both direct sets and functional updates.)

- [ ] **Step 4:** Run the hook test — expect PASS (7 tests). Note: the "restores…" tests assert state visible on FIRST render post-places; if the render-phase set doesn't surface synchronously under `renderHook`, wrap assertions in `act` per the failure message — do not weaken the assertions.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/usePersistedSelection.ts frontend/src/lib/usePersistedSelection.test.ts
git commit -m "feat(drawer): usePersistedSelection - restore/persist selected places"
```

---

### Task 2: Auto-run on load + shared-chip exit (MapWorkspace wiring)

These share the `pendingAutoRun` mechanism, so they land together.

**Files:**
- Modify: `frontend/src/components/MapWorkspace.tsx`
- Test: `frontend/src/components/MapWorkspace.test.tsx`

- [ ] **Step 1: Write the failing tests** (follow the file's existing mock/fixture patterns — read a nearby test like "runs analysis for selected places" first):

Add to `MapWorkspace.test.tsx`:

```tsx
  it("auto-runs analysis on load with the restored selection", async () => {
    localStorage.setItem("compcat.selection", JSON.stringify([home.id]));
    vi.mocked(analyzePlaces).mockResolvedValue({ summary_count: 1 });
    renderWorkspace({ places: [home, work] });
    await waitFor(() => {
      expect(analyzePlaces).toHaveBeenCalledTimes(1);
      expect(analyzePlaces).toHaveBeenCalledWith(
        expect.objectContaining({ place_ids: [home.id] }),
      );
    });
  });

  it("auto-runs with all places when nothing is stored", async () => {
    vi.mocked(analyzePlaces).mockResolvedValue({ summary_count: 2 });
    renderWorkspace({ places: [home, work] });
    await waitFor(() =>
      expect(analyzePlaces).toHaveBeenCalledWith(
        expect.objectContaining({ place_ids: expect.arrayContaining([home.id, work.id]) }),
      ),
    );
  });

  it("does not auto-run for an empty session", async () => {
    renderWorkspace({ places: [] });
    await screen.findByText(/look up an address/i);
    expect(analyzePlaces).not.toHaveBeenCalled();
  });

  it("exits a shared view and selects the clicked place from a chip", async () => {
    vi.mocked(analyzePlaces).mockResolvedValue({ summary_count: 1 });
    renderSharedView({ places: [home] });           // helper: render with a shared-view initialView
    const chip = await screen.findByRole("checkbox", { name: home.display_label });
    fireEvent.click(chip);
    expect(screen.queryByText(/shared view/i)).not.toBeInTheDocument();
    await waitFor(() =>
      expect(analyzePlaces).toHaveBeenCalledWith(
        expect.objectContaining({ place_ids: [home.id] }),
      ),
    );
  });
```

Adapt names to the file's actual fixtures/helpers (`home`/`work` place fixtures and a render helper already exist; `renderSharedView` may need assembling from the existing shared-view test's setup — copy that test's arrangement). Exact payload key (`place_ids` vs `selected_place_ids`) must match what `analyzePlaces` receives today — check an existing passing assertion and mirror it.

- [ ] **Step 2:** Run them — expect the 2 auto-run tests + shared-chip test to FAIL (no auto-run exists; shared click today only invalidates). The empty-session test may pass already — keep it as a regression pin.

- [ ] **Step 3: Wire the hook + pending auto-run in MapWorkspace.tsx**

1. Replace line 50 `const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());` with:

```tsx
  const { selectedIds, setSelectedIds, restored } = usePersistedSelection(data.places);
  const [pendingAutoRun, setPendingAutoRun] = useState(false);
```

(import `usePersistedSelection` from `../lib/usePersistedSelection`; all existing `setSelectedIds` call sites keep working — the hook accepts both value and updater forms.)

2. Arm the auto-run once, when restore completes on a plain session (place effect near the other analysis effects, after the `initialView` mount effect):

```tsx
  // "Analysis greets you": one shot after the persisted selection is restored. Skips
  // sessions that already own their first run (share links via initialView, lookup,
  // shared views) and empty selections. The flag fires runAnalyze only AFTER the
  // restored ids have committed — useAnalyze snapshots selectedIds per render, so a
  // same-tick call would analyze the pre-restore (empty) set.
  const autoRunArmedRef = useRef(false);
  useEffect(() => {
    if (!restored || autoRunArmedRef.current) return;
    autoRunArmedRef.current = true;
    if (!initialView && !lookupPoint && !sharedPoints && selectedIds.size > 0) {
      setPendingAutoRun(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [restored]);

  useEffect(() => {
    if (!pendingAutoRun || selectedIds.size === 0) return;
    setPendingAutoRun(false);
    void analyze.runAnalyze();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingAutoRun, selectedIds]);
```

3. Shared-chip exit — in `handleToggleSelect` (currently invalidate + clear lookup/draft + toggle), add a shared-session branch FIRST:

```tsx
  function handleToggleSelect(id: string) {
    invalidateAnalysisContext();
    setLookupPoint(null);
    pinDraft.setDraft(null);
    if (sharedPoints) {
      // A chip click during a shared view exits it (same as the banner's Exit) and
      // starts a fresh selection with the clicked place; the pending-auto-run effect
      // owns the follow-up run once the new selection commits.
      setSharedPoints(null);
      setSelectedIds(new Set([id]));
      setPendingAutoRun(true);
      return;
    }
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }
```

- [ ] **Step 4:** `cd frontend && npx tsc -b && npx vitest run src/components/MapWorkspace.test.tsx` — iterate until green, then full `npx vitest run`. Watch for existing tests that assumed NO auto-run on load (e.g. asserting `analyzePlaces` not called before a manual Run, or call-counts now off by one): fix by clearing the mock after initial render (`vi.mocked(analyzePlaces).mockClear()` post-`waitFor` of first paint) — do NOT weaken their behavioral assertions. localStorage must be cleared between tests (add `localStorage.clear()` to the file's `beforeEach` if not present).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/MapWorkspace.tsx frontend/src/components/MapWorkspace.test.tsx
git commit -m "feat(drawer): analysis greets you on load + shared-view chips exit-and-select"
```

---

### Task 3: Place rename

**Files:**
- Modify: `frontend/src/api/client.ts` (after `createBulkPlaces`, ~line 104)
- Modify: `frontend/src/components/ManagePlacesModal.tsx`
- Modify: `frontend/src/components/MapWorkspace.tsx` (modal props)
- Test: `frontend/src/components/ManagePlacesModal.test.tsx`

- [ ] **Step 1: Failing tests** — add to `ManagePlacesModal.test.tsx` (extend `baseProps` with `onRename: vi.fn().mockResolvedValue(undefined)`):

```tsx
  it("renames a place inline: pencil, edit, Enter", async () => {
    render(<ManagePlacesModal {...baseProps} initialView="manage" />);
    fireEvent.click(screen.getByRole("button", { name: "Rename Home" }));
    const input = screen.getByRole("textbox", { name: "New name for Home" });
    fireEvent.change(input, { target: { value: "Home base" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => expect(baseProps.onRename).toHaveBeenCalledWith("p1", "Home base"));
    expect(screen.queryByRole("textbox", { name: "New name for Home" })).not.toBeInTheDocument();
  });

  it("escape cancels a rename without calling the API", () => {
    render(<ManagePlacesModal {...baseProps} initialView="manage" />);
    fireEvent.click(screen.getByRole("button", { name: "Rename Home" }));
    const input = screen.getByRole("textbox", { name: "New name for Home" });
    fireEvent.change(input, { target: { value: "whatever" } });
    fireEvent.keyDown(input, { key: "Escape" });
    expect(baseProps.onRename).not.toHaveBeenCalled();
    expect(screen.getByText("Home")).toBeInTheDocument();
  });

  it("rejects an empty rename", () => {
    render(<ManagePlacesModal {...baseProps} initialView="manage" />);
    fireEvent.click(screen.getByRole("button", { name: "Rename Home" }));
    const input = screen.getByRole("textbox", { name: "New name for Home" });
    fireEvent.change(input, { target: { value: "   " } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(baseProps.onRename).not.toHaveBeenCalled();
    expect(input).toBeInTheDocument();
  });
```

- [ ] **Step 2:** Run — expect FAIL (no rename button).

- [ ] **Step 3: Implement**

`frontend/src/api/client.ts` (mirror `createPlace`'s style; partial payload per `ManualPlaceUpdate`):

```tsx
export function updatePlace(placeId: string, payload: { display_label: string }): Promise<Place> {
  return request(`/places/${placeId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}
```

`ManagePlacesModal.tsx`:
- Props: add `onRename: (id: string, label: string) => Promise<void>;`
- State: `const [editing, setEditing] = useState<{ id: string; value: string } | null>(null);`
- In each list row's `<div className="meta">`, when `editing?.id === place.id` render instead of the `nm` div:

```tsx
                        <input
                          className="mc-rename-input"
                          aria-label={`New name for ${place.display_label}`}
                          value={editing.value}
                          autoFocus
                          onChange={(e) => setEditing({ id: place.id, value: e.target.value })}
                          onKeyDown={async (e) => {
                            if (e.key === "Escape") setEditing(null);
                            if (e.key === "Enter") {
                              const label = editing.value.trim();
                              if (!label) return;
                              await onRename(place.id, label);
                              setEditing(null);
                            }
                          }}
                        />
```

- In `<div className="right">`, before the delete button, add the pencil:

```tsx
                        <button type="button" className="ico" aria-label={`Rename ${place.display_label}`} onClick={() => setEditing({ id: place.id, value: place.display_label })}>
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17 3l4 4L8 20l-5 1 1-5L17 3z" /></svg>
                        </button>
```

- CSS (next to `.mc-manage` in `mapWorkspace.css`): `.mc-rename-input{width:100%;font:inherit;padding:2px 6px;border:1px solid var(--accent);border-radius:6px;background:var(--surface);color:var(--text-strong);}`

`MapWorkspace.tsx` — pass the handler to the modal:

```tsx
            onRename={async (id, label) => {
              await updatePlace(id, { display_label: label });
              await data.refreshWithFallback("Renamed, but dashboard totals could not refresh.");
            }}
```

(import `updatePlace` alongside the existing client imports.)

- [ ] **Step 4:** `npx tsc -b && npx vitest run` — full suite green (the modal's other tests get `onRename` via `baseProps`).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/components/ManagePlacesModal.tsx frontend/src/components/ManagePlacesModal.test.tsx frontend/src/components/MapWorkspace.tsx frontend/src/styles/mapWorkspace.css
git commit -m "feat(places): inline rename in the manage modal (existing PATCH endpoint)"
```

---

### Task 4: Gate, live check, final review, PR

- [ ] **Step 1:** `make test-all` from the worktree root — pytest 617/3 skipped (backend untouched), ruff, vitest, build all green.

- [ ] **Step 2: Live check** (controller): worktree DB (`mkdir -p dev-output && rm -f dev-output/mobility.sqlite3 && .venv/bin/python -m alembic upgrade head` — the stale-partial-sqlite gotcha), temp launch configs pointed at `../waypoint-polish`, then verify: fresh session with saved places paints verdicts with no click (chips pre-checked); reload preserves a changed selection; rename via pencil persists and the chip label updates; a shared-view link's chips exit-and-select.

- [ ] **Step 3:** Fresh-context final review (Fable) of the whole branch against the spec's acceptance criteria; fix loop until approved.

- [ ] **Step 4:** Push `drawer-polish`, open the PR referencing the spec; note the documented quirk (lookup sessions persist an empty selection → next load falls back to all places) in the body. User squash-merges.
