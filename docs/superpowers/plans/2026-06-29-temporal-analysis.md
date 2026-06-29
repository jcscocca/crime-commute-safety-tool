# Temporal Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show *when* reported incidents occur around a place — hour-of-day and day-of-week profiles with a travel-window highlight — on the Places Analyze tab.

**Architecture:** A pure module (`app/analysis/temporal.py`) turns a place's in-radius incidents into hour/day marginals plus a 7×24 joint matrix; it is wired into the existing `neighborhood_analysis_for_places` path (no new query, no migration) and rides the `/dashboard/neighborhood` response, which already returns a bare dict (no pydantic `response_model`). The frontend renders two 1-D bar profiles and computes the travel-window share client-side from the joint matrix.

**Tech stack:** Python 3.11 / FastAPI / SQLAlchemy / pytest; React + TypeScript + Vite / vitest + testing-library. Run from the worktree `/.worktrees/temporal-analysis`.

**Spec:** `docs/superpowers/specs/2026-06-29-temporal-analysis-design.md`

**Key resolved fact (do not re-litigate):** `CrimeIncident.offense_start_utc` stores **naive Seattle local wall-clock mislabeled as UTC** (`app/crime/seattle_socrata.py:71` → `parse_datetime` at `app/parsers/base.py:48` stamps naive values UTC *without converting*). So local hour/weekday are read **directly** off the stored datetime — **no `zoneinfo` conversion** (it would double-shift ~7–8h). This is pinned by a test.

---

## File Structure

**Backend**
- Create `app/analysis/temporal.py` — `TemporalProfile` dataclass + `local_hour_dow` + `build_temporal_profile` (pure, no DB).
- Modify `app/services/neighborhood_service.py` — import + attach `temporal` to each place dict (3 branches).
- Create `tests/test_temporal_analysis.py` — pure-module unit tests.
- Modify `tests/test_neighborhood_service.py` — assert `temporal` attached at the service layer.
- Modify `tests/test_dashboard_neighborhood_api.py` — API contract + invariant (no safety language) guard.

**Frontend**
- Modify `frontend/src/types.ts` — `TemporalProfile` type + `temporal?` on `NeighborhoodPlace`.
- Create `frontend/src/lib/temporalWindow.ts` — `TravelWindow`, day-set maps, labels, default, `clampInt`, `windowShare`.
- Create `frontend/src/lib/temporalWindow.test.ts` — `windowShare` + `clampInt` unit tests.
- Modify `frontend/src/components/AnalyzeTab.tsx` — `ProfileBars` + `TemporalSection`, rendered in `VerdictCard`.
- Modify `frontend/src/components/AnalyzeTab.test.tsx` — `TemporalSection` rendering/interaction tests.
- Modify `frontend/src/styles/mapWorkspace.css` — neutral temporal styles.

**Docs**
- Modify `docs/ROADMAP.md` — add Phase 4 slate (C1 done) + reconcile stale snapshot rows.

> No assistant change: the assistant tool returns the neighborhood dict, but the chat answer is a deterministic summary (no LLM narration of raw results), so the extra `temporal` key cannot leak time-of-day "advice". The chat→pane bridge (`AssistantToolEffect.neighborhood`) renders the new section for free.

Commands: backend tests `.venv/bin/pytest <path> -v`; frontend tests `cd frontend && npx vitest run <path>`; lint `.venv/bin/ruff check .`; full gate `make test-all`.

---

## Task 1: Pure temporal module

**Files:**
- Create: `app/analysis/temporal.py`
- Test: `tests/test_temporal_analysis.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_temporal_analysis.py`:

```python
from datetime import UTC, datetime

from app.analysis.temporal import build_temporal_profile, local_hour_dow
from app.schemas import CrimeIncidentData


def _inc(dt: datetime | None) -> CrimeIncidentData:
    return CrimeIncidentData(offense_start_utc=dt)


def test_local_hour_dow_reads_wall_clock_without_shift():
    # offense_start_utc holds naive Seattle local stamped UTC (app/parsers/base.py),
    # so 23:30 must read as hour 23 — NOT shifted. 2024-02-10 is a Saturday (weekday 5).
    assert local_hour_dow(datetime(2024, 2, 10, 23, 30, tzinfo=UTC)) == (23, 5)


def test_build_temporal_profile_buckets_hour_and_dow():
    incidents = [
        _inc(datetime(2024, 2, 10, 23, 30, tzinfo=UTC)),  # Sat 23
        _inc(datetime(2024, 2, 12, 8, 0, tzinfo=UTC)),    # Mon 08
        _inc(datetime(2024, 2, 12, 8, 45, tzinfo=UTC)),   # Mon 08
        _inc(None),                                        # no recorded time
    ]
    profile = build_temporal_profile(incidents)

    assert profile.total_with_time == 3
    assert profile.without_time == 1
    assert len(profile.hour_counts) == 24
    assert len(profile.dow_counts) == 7
    assert profile.hour_counts[23] == 1
    assert profile.hour_counts[8] == 2
    assert profile.dow_counts[5] == 1  # Saturday
    assert profile.dow_counts[0] == 2  # Monday
    assert profile.hour_by_dow[0][8] == 2
    assert profile.hour_by_dow[5][23] == 1
    # marginals must equal the joint matrix collapsed each way
    assert profile.hour_counts == [
        sum(profile.hour_by_dow[d][h] for d in range(7)) for h in range(24)
    ]
    assert profile.dow_counts == [sum(profile.hour_by_dow[d]) for d in range(7)]


def test_build_temporal_profile_empty():
    profile = build_temporal_profile([])
    assert profile.total_with_time == 0
    assert profile.without_time == 0
    assert profile.hour_counts == [0] * 24
    assert profile.dow_counts == [0] * 7
    assert profile.hour_by_dow == [[0] * 24 for _ in range(7)]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_temporal_analysis.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.analysis.temporal'`.

- [ ] **Step 3: Write minimal implementation**

Create `app/analysis/temporal.py`:

```python
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from app.schemas import CrimeIncidentData


@dataclass(frozen=True)
class TemporalProfile:
    hour_counts: list[int]  # length 24, local hour 0–23
    dow_counts: list[int]  # length 7, Mon=0 … Sun=6
    hour_by_dow: list[list[int]]  # 7×24 joint counts (rows = weekday, cols = hour)
    total_with_time: int
    without_time: int


def local_hour_dow(dt: datetime) -> tuple[int, int]:
    """Local ``(hour, weekday)`` for an incident's ``offense_start_utc``.

    SPD publishes naive Seattle wall-clock; ``parse_datetime`` stamps it UTC WITHOUT
    converting (see ``app/parsers/base.py``), so the stored value's wall-clock fields are
    ALREADY Seattle-local. Read them directly — a zoneinfo conversion would double-shift by
    ~7–8h. ``weekday()`` returns Mon=0 … Sun=6.
    """
    return dt.hour, dt.weekday()


def build_temporal_profile(incidents: Iterable[CrimeIncidentData]) -> TemporalProfile:
    hour_by_dow = [[0] * 24 for _ in range(7)]
    total_with_time = 0
    without_time = 0
    for incident in incidents:
        dt = incident.offense_start_utc
        if dt is None:
            without_time += 1
            continue
        hour, dow = local_hour_dow(dt)
        hour_by_dow[dow][hour] += 1
        total_with_time += 1
    hour_counts = [sum(hour_by_dow[d][h] for d in range(7)) for h in range(24)]
    dow_counts = [sum(row) for row in hour_by_dow]
    return TemporalProfile(
        hour_counts=hour_counts,
        dow_counts=dow_counts,
        hour_by_dow=hour_by_dow,
        total_with_time=total_with_time,
        without_time=without_time,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_temporal_analysis.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add app/analysis/temporal.py tests/test_temporal_analysis.py
git commit -m "feat(analysis): pure temporal-profile module (hour/dow + joint matrix)"
```

---

## Task 2: Wire temporal into the neighborhood service

**Files:**
- Modify: `app/services/neighborhood_service.py` (imports; 3 `places.append` branches)
- Test: `tests/test_neighborhood_service.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_neighborhood_service.py`:

```python
def test_neighborhood_analysis_attaches_temporal_profile(tmp_path):
    session, user_hash, place_id = session_with_places_and_beat_crime(tmp_path)
    result = neighborhood_analysis_for_places(
        session=session,
        user_id_hash=user_hash,
        place_ids=[place_id],
        radius_m=250,
        analysis_start_date=date(2026, 1, 1),
        analysis_end_date=date(2026, 6, 30),
        offense_category=None,
        offense_subcategory=None,
        nibrs_group=None,
        area_lookup={"M3": 3.0},
        beat_polygons=_M3_POLYGONS,
    )
    temporal = result["places"][0]["temporal"]
    assert len(temporal["hour_counts"]) == 24
    assert len(temporal["dow_counts"]) == 7
    # The fixture's 5 in-radius "near" incidents are dated datetime(2026, m, 12) -> hour 0.
    assert temporal["total_with_time"] == 5
    assert temporal["hour_counts"][0] == 5
    assert temporal["without_time"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_neighborhood_service.py::test_neighborhood_analysis_attaches_temporal_profile -v`
Expected: FAIL — `KeyError: 'temporal'`.

- [ ] **Step 3: Add the imports**

In `app/services/neighborhood_service.py`, add `from dataclasses import asdict` between the `collections` and `datetime` imports:

```python
from collections import Counter
from dataclasses import asdict
from datetime import date
```

And add the temporal import after the `rate_tests` import block (keep alphabetical within `app.analysis`):

```python
from app.analysis.rate_tests import (
    benjamini_hochberg,
    compare_incident_rates,
    dispersion_status,
)
from app.analysis.temporal import build_temporal_profile
```

- [ ] **Step 4: Attach temporal in the baseline-unavailable branch**

Replace:

```python
            places.append(
                {
                    **base,
                    "baseline_available": False,
                    "decision": "baseline_unavailable",
                    "place_incident_count": len(entry.get("place_incidents", [])),
                    "type_mix": _type_mix(entry.get("place_incidents", [])),
                }
            )
```

with:

```python
            places.append(
                {
                    **base,
                    "baseline_available": False,
                    "decision": "baseline_unavailable",
                    "place_incident_count": len(entry.get("place_incidents", [])),
                    "type_mix": _type_mix(entry.get("place_incidents", [])),
                    "temporal": asdict(build_temporal_profile(entry.get("place_incidents", []))),
                }
            )
```

- [ ] **Step 5: Attach temporal in the insufficient-data branch**

Replace:

```python
            places.append(
                {
                    **base,
                    "baseline_available": False,
                    "decision": "insufficient_data",
                    "minimum_data_status": "baseline_too_small",
                    "place_incident_count": len(entry.get("place_incidents", [])),
                    "type_mix": _type_mix(entry.get("place_incidents", [])),
                }
            )
```

with:

```python
            places.append(
                {
                    **base,
                    "baseline_available": False,
                    "decision": "insufficient_data",
                    "minimum_data_status": "baseline_too_small",
                    "place_incident_count": len(entry.get("place_incidents", [])),
                    "type_mix": _type_mix(entry.get("place_incidents", [])),
                    "temporal": asdict(build_temporal_profile(entry.get("place_incidents", []))),
                }
            )
```

- [ ] **Step 6: Attach temporal in the full-result branch**

Replace:

```python
                "monthly_counts": place_monthly,
                "type_mix": _type_mix(place_incidents),
            }
        )
```

with:

```python
                "monthly_counts": place_monthly,
                "type_mix": _type_mix(place_incidents),
                "temporal": asdict(build_temporal_profile(place_incidents)),
            }
        )
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_neighborhood_service.py -v`
Expected: PASS (all existing tests + the new one).

- [ ] **Step 8: Commit**

```bash
git add app/services/neighborhood_service.py tests/test_neighborhood_service.py
git commit -m "feat(analysis): attach temporal profile to neighborhood places"
```

---

## Task 3: API contract + invariant guard

**Files:**
- Test: `tests/test_dashboard_neighborhood_api.py`

> These pass once Task 2 is in (temporal flows automatically through the bare-dict response). They guard the public contract and the product invariant.

- [ ] **Step 1: Write the guard test**

Append to `tests/test_dashboard_neighborhood_api.py`:

```python
def test_neighborhood_endpoint_includes_temporal_and_no_safety_language(neighborhood_client):
    import json

    client, place_id = neighborhood_client
    response = client.post(
        "/dashboard/neighborhood",
        json={
            "place_ids": [place_id],
            "analysis_start_date": "2026-01-01",
            "analysis_end_date": "2026-06-30",
            "radii_m": [250],
            "offense_category": None,
        },
    )
    assert response.status_code == 200
    body = response.json()
    temporal = body["places"][0]["temporal"]
    assert len(temporal["hour_counts"]) == 24
    assert len(temporal["dow_counts"]) == 7
    assert len(temporal["hour_by_dow"]) == 7
    assert all(len(row) == 24 for row in temporal["hour_by_dow"])
    assert temporal["total_with_time"] == 5  # the 5 seeded in-radius incidents

    # Invariant: the payload reports context, never a safety judgment.
    blob = json.dumps(body).lower()
    for banned in ("unsafe", "dangerous", "safest", "risky", "avoid "):
        assert banned not in blob
```

- [ ] **Step 2: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_dashboard_neighborhood_api.py -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_dashboard_neighborhood_api.py
git commit -m "test(analysis): guard temporal API contract + no-safety-language invariant"
```

---

## Task 4: Frontend types + travel-window helper

**Files:**
- Modify: `frontend/src/types.ts`
- Create: `frontend/src/lib/temporalWindow.ts`
- Test: `frontend/src/lib/temporalWindow.test.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/lib/temporalWindow.test.ts`:

```ts
import { describe, expect, it } from "vitest";

import type { TemporalProfile } from "../types";
import { clampInt, DEFAULT_TRAVEL_WINDOW, windowShare } from "./temporalWindow";

function profile(partial: Partial<TemporalProfile> = {}): TemporalProfile {
  return {
    hour_counts: Array(24).fill(0),
    dow_counts: Array(7).fill(0),
    hour_by_dow: Array.from({ length: 7 }, () => Array(24).fill(0)),
    total_with_time: 0,
    without_time: 0,
    ...partial,
  };
}

describe("windowShare", () => {
  it("counts weekday evenings from the joint matrix", () => {
    const hour_by_dow = Array.from({ length: 7 }, (_, d) =>
      Array.from({ length: 24 }, (_, h) => (d <= 4 && h === 17 ? 4 : 0)),
    );
    const { count, share } = windowShare(profile({ hour_by_dow, total_with_time: 40 }), {
      dayset: "weekdays",
      startHour: 16,
      endHour: 19,
    });
    expect(count).toBe(20);
    expect(share).toBeCloseTo(0.5);
  });

  it("returns zero share when nothing has a recorded time", () => {
    const { count, share } = windowShare(profile({ total_with_time: 0 }), DEFAULT_TRAVEL_WINDOW);
    expect(count).toBe(0);
    expect(share).toBe(0);
  });

  it("an all-day window counts every cell", () => {
    const hour_by_dow = Array.from({ length: 7 }, () => Array.from({ length: 24 }, () => 1));
    const { count } = windowShare(profile({ hour_by_dow, total_with_time: 168 }), {
      dayset: "all",
      startHour: 0,
      endHour: 24,
    });
    expect(count).toBe(168);
  });
});

describe("clampInt", () => {
  it("clamps, truncates, and falls back to min on NaN", () => {
    expect(clampInt("99", 0, 23)).toBe(23);
    expect(clampInt("-3", 0, 23)).toBe(0);
    expect(clampInt("8.9", 0, 23)).toBe(8);
    expect(clampInt("abc", 1, 24)).toBe(1);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/lib/temporalWindow.test.ts`
Expected: FAIL — cannot resolve `./temporalWindow` / `TemporalProfile` not exported.

- [ ] **Step 3: Add the `TemporalProfile` type**

In `frontend/src/types.ts`, insert immediately before `export type NeighborhoodPlace = {`:

```ts
export type TemporalProfile = {
  hour_counts: number[]; // length 24, local hour 0–23
  dow_counts: number[]; // length 7, Mon..Sun
  hour_by_dow: number[][]; // 7×24 joint counts
  total_with_time: number;
  without_time: number;
};

```

Then, inside `NeighborhoodPlace`, add a field directly after the `type_mix` line:

```ts
  type_mix: { label: string; count: number }[];
  temporal?: TemporalProfile | null;
```

- [ ] **Step 4: Create the helper**

Create `frontend/src/lib/temporalWindow.ts`:

```ts
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/lib/temporalWindow.test.ts`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types.ts frontend/src/lib/temporalWindow.ts frontend/src/lib/temporalWindow.test.ts
git commit -m "feat(frontend): TemporalProfile type + travel-window share helper"
```

---

## Task 5: TemporalSection component + AnalyzeTab wiring

**Files:**
- Modify: `frontend/src/components/AnalyzeTab.tsx`
- Test: `frontend/src/components/AnalyzeTab.test.tsx`

- [ ] **Step 1: Write the failing tests**

In `frontend/src/components/AnalyzeTab.test.tsx`, add a shared temporal fixture after the existing `homePlace` definition and attach it to `homePlace`. Replace:

```ts
  nearest_incident_m: 42, monthly_counts: [1, 2, 1, 3, 2, 3], type_mix: [{ label: "ASSAULT", count: 7 }],
};
```

with:

```ts
  nearest_incident_m: 42, monthly_counts: [1, 2, 1, 3, 2, 3], type_mix: [{ label: "ASSAULT", count: 7 }],
  temporal: {
    // weekdays 17:00 → 4 each (20 total); Sat 02:00 → 20. total_with_time = 40.
    hour_by_dow: Array.from({ length: 7 }, (_, d) =>
      Array.from({ length: 24 }, (_, h) => (d <= 4 && h === 17 ? 4 : d === 5 && h === 2 ? 20 : 0)),
    ),
    hour_counts: Array.from({ length: 24 }, (_, h) => (h === 17 ? 20 : h === 2 ? 20 : 0)),
    dow_counts: [4, 4, 4, 4, 4, 20, 0],
    total_with_time: 40,
    without_time: 0,
  },
};
```

Then add this `describe` block at the end of the file (before the final closing `});` of the outer `describe`, or as a sibling — place it just above the last line `});`):

```ts
  it("renders hour and day temporal profiles with the window callout", () => {
    const { container } = render(
      <AnalyzeTab selected={[home]} analysis={analysis} availableRadii={[250]} running={false} neighborhood={neighborhood} onChange={vi.fn()} onRun={vi.fn()} />,
    );
    const profiles = container.querySelectorAll(".mc-temporal-profile");
    expect(profiles.length).toBe(2);
    expect(profiles[0].querySelectorAll(".mc-temporal-bar").length).toBe(24);
    expect(profiles[1].querySelectorAll(".mc-temporal-bar").length).toBe(7);
    // default window = weekdays 16–19 → hour 17 (20) / 40 = 50%
    expect(screen.getByText(/50% of the 40 reported incidents with a recorded time/i)).toBeInTheDocument();
  });

  it("recomputes the callout when the travel window changes", () => {
    render(
      <AnalyzeTab selected={[home]} analysis={analysis} availableRadii={[250]} running={false} neighborhood={neighborhood} onChange={vi.fn()} onRun={vi.fn()} />,
    );
    // Weekends 16–19 contains none of the seeded cells (Sat activity is at 02:00) → 0%.
    fireEvent.click(screen.getByRole("button", { name: "Weekends" }));
    expect(screen.getByText(/0% of the 40 reported incidents with a recorded time/i)).toBeInTheDocument();
  });

  it("shows a low-sample caution and a missing-time note", () => {
    const lowN: NeighborhoodPlace = {
      ...homePlace,
      temporal: { ...homePlace.temporal!, total_with_time: 8, without_time: 3 },
    };
    render(
      <AnalyzeTab selected={[home]} analysis={analysis} availableRadii={[250]} running={false} neighborhood={{ ...neighborhood, places: [lowN] }} onChange={vi.fn()} onRun={vi.fn()} />,
    );
    expect(screen.getByText(/Based on 8 incidents — interpret with caution\./i)).toBeInTheDocument();
    expect(screen.getByText(/3 incidents had no recorded time/i)).toBeInTheDocument();
  });

  it("shows an empty temporal state when no incidents have a recorded time", () => {
    const noTime: NeighborhoodPlace = {
      ...homePlace,
      temporal: { hour_counts: Array(24).fill(0), dow_counts: Array(7).fill(0), hour_by_dow: Array.from({ length: 7 }, () => Array(24).fill(0)), total_with_time: 0, without_time: 0 },
    };
    const { container } = render(
      <AnalyzeTab selected={[home]} analysis={analysis} availableRadii={[250]} running={false} neighborhood={{ ...neighborhood, places: [noTime] }} onChange={vi.fn()} onRun={vi.fn()} />,
    );
    expect(screen.getByText("No reported incidents with a recorded time in this area.")).toBeInTheDocument();
    expect(container.querySelectorAll(".mc-temporal-bar").length).toBe(0);
  });
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/components/AnalyzeTab.test.tsx`
Expected: FAIL — `.mc-temporal-profile` not found / callout text absent.

- [ ] **Step 3: Add imports to AnalyzeTab.tsx**

At the very top of `frontend/src/components/AnalyzeTab.tsx`, add the React hook import as the first line:

```ts
import { useState } from "react";
```

Add `TemporalProfile` to the existing type import (insert in the alphabetical list):

```ts
import type {
  AnalysisSettings,
  IncidentDetail,
  IncidentDetailsResponse,
  NeighborhoodAnalysis,
  NeighborhoodPlace,
  Place,
  TemporalProfile,
} from "../types";
```

Add the helper import after the `verdictCopy` import:

```ts
import { decisionHeadline } from "../lib/verdictCopy";
import {
  clampInt,
  DAYSET_DAYS,
  DAYSET_LABELS,
  DEFAULT_TRAVEL_WINDOW,
  DOW_LABELS,
  windowShare,
  type TravelWindow,
} from "../lib/temporalWindow";
```

- [ ] **Step 4: Add `ProfileBars` and `TemporalSection`**

Insert the following directly after the `ComparisonBars` function (i.e. immediately before `function VerdictCard(`):

```tsx
function ProfileBars({
  counts,
  highlight,
  labelFor,
}: {
  counts: number[];
  highlight: Set<number>;
  labelFor: (index: number) => string;
}) {
  const max = Math.max(1, ...counts);
  return (
    <div className="mc-temporal-bars" aria-hidden="true">
      {counts.map((n, i) => (
        <span
          key={i}
          className={`mc-temporal-bar${highlight.has(i) ? " on" : ""}`}
          style={{ height: `${Math.round((n / max) * 100)}%` }}
          title={`${labelFor(i)}: ${n}`}
        />
      ))}
    </div>
  );
}

function TemporalSection({ temporal, windowLabel }: { temporal: TemporalProfile; windowLabel: string }) {
  const [tw, setTw] = useState<TravelWindow>(DEFAULT_TRAVEL_WINDOW);

  if (temporal.total_with_time === 0) {
    return (
      <div className="mc-temporal">
        <h6 className="mc-temporal-title">When reported incidents occurred</h6>
        <p className="mc-empty-list">No reported incidents with a recorded time in this area.</p>
      </div>
    );
  }

  const dayHighlight = new Set(DAYSET_DAYS[tw.dayset]);
  const hourHighlight = new Set<number>();
  for (let h = tw.startHour; h < tw.endHour; h += 1) hourHighlight.add(h);
  const { share } = windowShare(temporal, tw);

  return (
    <div className="mc-temporal">
      <h6 className="mc-temporal-title">When reported incidents occurred</h6>

      <div className="mc-temporal-profile">
        <span className="mc-temporal-axis">By hour</span>
        <ProfileBars counts={temporal.hour_counts} highlight={hourHighlight} labelFor={(h) => `${h}:00`} />
      </div>
      <div className="mc-temporal-profile">
        <span className="mc-temporal-axis">By day</span>
        <ProfileBars counts={temporal.dow_counts} highlight={dayHighlight} labelFor={(d) => DOW_LABELS[d]} />
      </div>

      <div className="mc-temporal-window" role="group" aria-label="Travel window">
        <div className="mc-chips">
          {(["weekdays", "weekends", "all"] as const).map((ds) => (
            <button
              key={ds}
              type="button"
              className={`mc-chip${tw.dayset === ds ? " on" : ""}`}
              aria-pressed={tw.dayset === ds}
              onClick={() => setTw({ ...tw, dayset: ds })}
            >
              {DAYSET_LABELS[ds]}
            </button>
          ))}
        </div>
        <div className="mc-temporal-hours">
          <label>
            From
            <input
              type="number"
              min={0}
              max={23}
              value={tw.startHour}
              aria-label="Window start hour"
              onChange={(e) => setTw({ ...tw, startHour: clampInt(e.target.value, 0, 23) })}
            />
          </label>
          <label>
            to
            <input
              type="number"
              min={1}
              max={24}
              value={tw.endHour}
              aria-label="Window end hour"
              onChange={(e) => setTw({ ...tw, endHour: clampInt(e.target.value, 1, 24) })}
            />
          </label>
        </div>
      </div>

      <p className="mc-temporal-callout">
        {Math.round(share * 100)}% of the {temporal.total_with_time} reported incidents with a recorded time ({windowLabel}) fell in your travel window.
      </p>
      {temporal.total_with_time < 20 ? (
        <p className="mc-temporal-note">Based on {temporal.total_with_time} incidents — interpret with caution.</p>
      ) : null}
      {temporal.without_time > 0 ? (
        <p className="mc-temporal-note">{temporal.without_time} incidents had no recorded time and aren’t shown here.</p>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 5: Render `TemporalSection` inside `VerdictCard`**

In `VerdictCard`, replace the closing of the component:

```tsx
      ) : (
        <p className="mc-verdict-sub">{place.place_incident_count} reported incidents in range; no beat baseline.</p>
      )}
    </section>
  );
}
```

with:

```tsx
      ) : (
        <p className="mc-verdict-sub">{place.place_incident_count} reported incidents in range; no beat baseline.</p>
      )}
      {place.temporal ? <TemporalSection temporal={place.temporal} windowLabel={windowLabel} /> : null}
    </section>
  );
}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/AnalyzeTab.test.tsx`
Expected: PASS (all existing tests + the 4 new ones).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/AnalyzeTab.tsx frontend/src/components/AnalyzeTab.test.tsx
git commit -m "feat(frontend): temporal section on the Analyze tab with travel-window highlight"
```

---

## Task 6: Temporal styles

**Files:**
- Modify: `frontend/src/styles/mapWorkspace.css`

- [ ] **Step 1: Append the temporal styles**

Add to the end of `frontend/src/styles/mapWorkspace.css`:

```css
/* Temporal analysis — descriptive hour-of-day + day-of-week, neutral palette */
.mc-temporal{margin-top:12px;padding-top:11px;border-top:1px solid var(--line);display:grid;gap:8px;}
.mc-temporal-title{margin:0;font-size:11.5px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:var(--faint);}
.mc-temporal-profile{display:grid;grid-template-columns:48px 1fr;align-items:center;gap:8px;}
.mc-temporal-axis{font-size:10px;color:var(--dim);}
.mc-temporal-bars{display:flex;align-items:flex-end;gap:2px;height:40px;}
.mc-temporal-bar{flex:1;min-width:2px;min-height:2px;border-radius:2px 2px 0 0;background:rgba(255,255,255,.16);}
.mc-temporal-bar.on{background:var(--slate);}
.mc-temporal-window{display:flex;flex-wrap:wrap;align-items:center;gap:10px;}
.mc-temporal-hours{display:flex;align-items:center;gap:6px;font-size:11px;color:var(--dim);}
.mc-temporal-hours label{display:inline-flex;align-items:center;gap:5px;}
.mc-temporal-hours input{width:46px;background:rgba(255,255,255,.05);border:1px solid var(--line);border-radius:6px;color:var(--text);padding:3px 5px;font-family:var(--f-mono);}
.mc-temporal-callout{margin:0;font-size:12px;color:var(--text);}
.mc-temporal-note{margin:0;font-size:11px;color:var(--faint);}
```

- [ ] **Step 2: Verify the build is clean**

Run: `cd frontend && npm run build`
Expected: build succeeds (tsc + vite), no type errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/styles/mapWorkspace.css
git commit -m "style(frontend): neutral temporal profile + travel-window styles"
```

---

## Task 7: Roadmap tick (Phase 4 + snapshot reconciliation)

**Files:**
- Modify: `docs/ROADMAP.md`

- [ ] **Step 1: Reconcile the stale "Half-baked" snapshot row**

Replace:

```markdown
| **Half-baked** | Real-data query perf still has residual full-table paths outside the main summarize path; data-freshness surface exposed via API but not surfaced in the UI; Postgres-in-prod (CI-proven but not long-run validated); MapWorkspace still a 497-line hub (not split into per-tab hooks) |
```

with:

```markdown
| **Half-baked** | Real-data query perf still has residual full-table paths outside the main summarize path; Postgres-in-prod (CI-proven but not long-run validated) |
```

- [ ] **Step 2: Reconcile the stale "Open — invariant risk" snapshot row**

Replace:

```markdown
| **Open — invariant risk** | Safety-refusal guard substantially broadened (broad regex, scans last 8 user turns) but a regex gap lets "rank these places" / "score these areas" bypass it (missing `\s+` inside optional noun clause); no output-side guard test on the assistant response token stream |
```

with:

```markdown
| **Open — invariant risk** | Safety-refusal guard hardened (object-first regex gap fixed #59; output-side guard + broadened ranking/determiner detection #63). Residual: synonym-lexicon + non-English breadth (lower-priority follow-up, Phase 4 H4) |
```

- [ ] **Step 3: Replace the "What's next" section with the Phase 4 slate**

Replace:

```markdown
## What's next

All of the planned work (Phases 0–3) is complete — there is no queued work. Waypoint is a disciplined, low-debt internal-trial v1. When a new unit of work is chosen, it follows the cadence in **Conventions** below.
```

with:

```markdown
## Phase 4 — Harden & polish + new capabilities
*The next slate, chosen 2026-06-29. Worked one item at a time per Conventions.*

**Harden & polish**
- [ ] **H1 · Query-perf sweep** — fix the residual full-table query paths outside `summarize_for_user`; add indexes / SQL-filtered paths.
- [ ] **H2 · Long-run Postgres validation** — exercise the prod stack on Postgres under sustained/load conditions beyond the CI parity smoke.
- [ ] **H3 · Address-search polish** — debounce, result ranking, error/empty states, recent searches across Places + Routes.
- [ ] **H4 · Assistant guard breadth** — close the residual synonym-lexicon / non-English gaps in the safety-refusal guard.

**New capabilities**
- [x] **C1 · Temporal analysis** — descriptive hour-of-day + day-of-week incident profiles around a place, with a travel-window highlight, on the Analyze tab. Pure `app/analysis/temporal.py` wired into the analyze path; `offense_start_utc` read as naive Seattle local. Spec/plan: `docs/superpowers/{specs,plans}/2026-06-29-temporal-analysis*`.
- [ ] **C2 · Incident category breakdown** — surface the mix of incident types (not just counts) with the same baseline rigor.
- [ ] **C3 · Saved views** — lightweight cross-session persistence to save & revisit an analysis/comparison.
- [ ] **C4 · Second data source** — integrate another dataset (e.g. SPD 911 calls).

> Deferred temporal follow-ups (after C1): comparative/baseline temporal (rate-ratio per bucket), route corridor-temporal, an assistant temporal tool, and renaming the misnamed `offense_start_utc` column (holds local time) — a separate migration.
```

- [ ] **Step 4: Commit**

```bash
git add docs/ROADMAP.md
git commit -m "docs(roadmap): open Phase 4 slate; mark C1 temporal done; reconcile snapshot"
```

---

## Task 8: Full verification gate

- [ ] **Step 1: Lint**

Run: `.venv/bin/ruff check .`
Expected: `All checks passed!` (fix import order / unused names if flagged, then re-run).

- [ ] **Step 2: Full gate**

Run: `make test-all`
Expected: pytest passes (376+ tests), `ruff check .` clean, frontend `npm test` passes, `npm run build` succeeds.

- [ ] **Step 3: Commit any lint/format fixups (only if Step 1–2 required changes)**

```bash
git add -A
git commit -m "chore: lint/format fixups for temporal analysis"
```

---

## Self-Review

**1. Spec coverage**

- Descriptive hour + day-of-week profiles → Task 1 (engine), Task 5 (UI). ✓
- Travel-window highlight + client-side callout → Task 4 (`windowShare`), Task 5 (control + callout). ✓
- `offense_start_utc` read as naive Seattle local (no conversion) → Task 1 `local_hour_dow` + pin test. ✓
- Missing-time counted, not dropped → Task 1 `without_time`; Task 5 footnote. ✓
- Joint 7×24 matrix returned, not displayed as a grid → Task 1 `hour_by_dow`; Task 4 consumes it; Task 5 renders only 1-D marginals. ✓
- Pure module wired into existing analyze path, no new query/migration → Task 2. ✓
- API carries `temporal`; no `response_model` change needed → Task 3 confirms. ✓
- Invariant: numbers only, no safety language → Task 3 guard; Task 5 neutral copy; Task 6 neutral palette. ✓
- Low-N note (<20) → Task 5. ✓
- Empty state → Task 5. ✓
- Places Analyze tab only; no assistant/routes change → confirmed (no such tasks). ✓
- Roadmap tick + snapshot reconciliation → Task 7. ✓

**2. Placeholder scan:** No TBD/TODO; every code step shows full code. ✓

**3. Type consistency:** `TemporalProfile` fields (`hour_counts`, `dow_counts`, `hour_by_dow`, `total_with_time`, `without_time`) are identical across the Python dataclass (Task 1), the TS type (Task 4), all test fixtures (Tasks 1–5), and the component (Task 5). `windowShare`/`clampInt`/`DAYSET_DAYS`/`DAYSET_LABELS`/`DOW_LABELS`/`DEFAULT_TRAVEL_WINDOW`/`TravelWindow` are defined in Task 4 and consumed with matching signatures in Task 5. `build_temporal_profile`/`local_hour_dow` defined in Task 1, used in Task 2. ✓
