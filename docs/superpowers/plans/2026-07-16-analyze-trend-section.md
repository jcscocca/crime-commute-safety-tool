# Analyze Trend Section Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `GET /dashboard/trends` (monthly MCPP + citywide incident-count series) and a descriptive "volume over time" section on the Analyze tab with a 12-month rolling mean and an anchored-indexed citywide overlay.

**Architecture:** Backend returns two raw zero-filled monthly series (TTL-cached per layer/MCPP/category, citywide shared); all math (anchor factor, rolling mean, indexing, suppression) is frontend-pure per `docs/analysis/trend-indexing-method.md` §8. Spec: `docs/superpowers/specs/2026-07-16-analyze-trend-section-design.md`.

**Tech Stack:** FastAPI + SQLAlchemy (SQLite dev / Postgres prod — mind the `func.timezone` branch), React + TypeScript + vitest.

**House rules:** work in this worktree; match existing comment density (low); `make test-all` before claiming done. Read the spec and methodology doc before Task 1.

---

### Task 1: Backend service — window, series, publicized helpers

**Files:**
- Modify: `app/services/neighborhood_service.py` (rename `_months` → `months_between`, `_area_month_counts` → `area_month_counts`; def at :56 and :126, call sites at :66, :355, :364, :379)
- Create: `app/services/trends_service.py`
- Test: `tests/test_trends_service.py`

- [ ] **Step 1: Mechanical rename in `neighborhood_service.py`**

Rename `_months` → `months_between` (3 sites: def line 56, lines 66, 355) and `_area_month_counts` → `area_month_counts` (def line 126, call sites lines 364, 379). No behavior change. Run `pytest tests/ -k neighborhood -q` — expect all pass.

- [ ] **Step 2: Write failing service tests**

`tests/test_trends_service.py`. Seed incidents by copying the exact `CrimeIncident(...)` construction used in `tests/helpers_dashboard.py` (that file is the canonical row shape — verify kwargs there before writing; the fields that matter here are `source_dataset`, `offense_start_utc`/`report_utc`, `latitude`/`longitude`, `mcpp`, `beat`, `offense_category`). Use `beat="M3"`, `mcpp="TEST HILL"` (real keys — the neighborhood API tests rely on them).

```python
from datetime import date

from app.services.trends_service import (
    reset_trends_cache,
    trends_for_mcpp,
    window_bounds,
)

TODAY = date(2026, 7, 16)


def test_window_bounds_reported_is_60_complete_months():
    start, end = window_bounds("reported", TODAY)
    assert end == date(2026, 6, 30)          # last complete month
    assert start == date(2021, 7, 1)          # 60 months inclusive


def test_window_bounds_calls_clamped_to_rolling_floor():
    start, end = window_bounds("calls", TODAY)
    assert end == date(2026, 6, 30)
    assert start == date(2024, 7, 1)          # calls_data_floor(TODAY)


def test_series_are_zero_filled_and_aligned(seeded_session):
    # seeded_session fixture: sqlite Session with TEST HILL incidents in
    # 2026-01, 2026-01, 2026-03 (area) and one 2026-02 incident in another
    # beat/mcpp (citywide-only)
    payload = trends_for_mcpp(
        seeded_session, mcpp="TEST HILL", layer="reported",
        offense_category=None, today=TODAY,
    )
    months = payload["months"]
    assert len(months) == 60 == len(payload["area_counts"]) == len(payload["citywide_counts"])
    assert months[0] == "2021-07" and months[-1] == "2026-06"
    by_month = dict(zip(months, payload["area_counts"]))
    assert by_month["2026-01"] == 2
    assert by_month["2026-02"] == 0            # zero-filled, not missing
    assert by_month["2026-03"] == 1
    city = dict(zip(months, payload["citywide_counts"]))
    assert city["2026-02"] == 1                # other-beat incident counts citywide
    assert payload["mcpp"] == "TEST HILL" and payload["mcpp_label"] == "Test Hill"


def test_category_filter_applies(seeded_session):
    payload = trends_for_mcpp(
        seeded_session, mcpp="TEST HILL", layer="reported",
        offense_category="PROPERTY", today=TODAY,
    )
    assert sum(payload["area_counts"]) == <count of PROPERTY-seeded rows>


def test_cache_hit_and_reset(seeded_session):
    clock = iter([0.0, 1.0, 2.0, 5000.0]).__next__
    first = trends_for_mcpp(seeded_session, mcpp="TEST HILL", layer="reported",
                            offense_category=None, today=TODAY, now=clock)
    second = trends_for_mcpp(seeded_session, mcpp="TEST HILL", layer="reported",
                             offense_category=None, today=TODAY, now=clock)
    assert second is first                     # served from cache
    reset_trends_cache()
```

(Replace the `<count …>` placeholder with the fixture's real number when writing the fixture; make the fixture seed at least one `PROPERTY` and one `PERSON` row.)

Run: `pytest tests/test_trends_service.py -q` — expect ImportError/FAIL.

- [ ] **Step 3: Implement `app/services/trends_service.py`**

```python
"""Monthly trend series for the Analyze 'volume over time' section.

Methodology: docs/analysis/trend-indexing-method.md (§8 implementation contract).
Raw series only — indexing/rolling are computed client-side.
"""
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache
from time import monotonic
from typing import Callable

from sqlalchemy.orm import Session

from app.analysis.area_baselines import mcpp_display_label
from app.analysis.beat_baselines import load_beat_areas
from app.crime.seattle_socrata import calls_data_floor, crime_data_floor
from app.crime.sources import LAYER_CALLS, sources_for_layer
from app.models import CrimeIncident
from app.services.neighborhood_service import area_month_counts, months_between

WINDOW_MONTHS = 60
TRENDS_CACHE_TTL_S = 3600.0

_trends_cache: dict[str, dict[str, object]] = {}
_trends_expires: dict[str, float] = {}


def reset_trends_cache() -> None:
    _trends_cache.clear()
    _trends_expires.clear()


@lru_cache(maxsize=1)
def _beat_names() -> tuple[str, ...]:
    return tuple(sorted(load_beat_areas()))


def window_bounds(layer: str, today: date) -> tuple[date, date]:
    end = today.replace(day=1) - timedelta(days=1)          # last complete month
    months_back = WINDOW_MONTHS - 1
    year = end.year - (months_back // 12)
    month = end.month - (months_back % 12)
    if month < 1:
        month += 12
        year -= 1
    start = date(year, month, 1)
    floor = calls_data_floor(today) if layer == LAYER_CALLS else crime_data_floor(today)
    return max(start, floor), end


def trends_for_mcpp(
    session: Session,
    *,
    mcpp: str,
    layer: str,
    offense_category: str | None,
    today: date | None = None,
    now: Callable[[], float] = monotonic,
) -> dict[str, object]:
    sources = sources_for_layer(layer)
    effective_today = today or date.today()
    start, end = window_bounds(layer, effective_today)
    key = f"{layer}:{mcpp}:{offense_category or ''}:{start}:{end}"
    cached = _trends_cache.get(key)
    if cached is not None and now() < _trends_expires.get(key, 0.0):
        return cached

    month_keys = months_between(start, end)
    area = _cached_series(
        session, f"area:{key}", CrimeIncident.mcpp, (mcpp,),
        start, end, offense_category, sources, month_keys, now,
    )
    city_key = f"city:{layer}:{offense_category or ''}:{start}:{end}"
    city = _cached_series(
        session, city_key, CrimeIncident.beat, _beat_names(),
        start, end, offense_category, sources, month_keys, now,
    )
    value: dict[str, object] = {
        "layer": layer,
        "mcpp": mcpp,
        "mcpp_label": mcpp_display_label(mcpp),
        "category": offense_category,
        "months": [f"{y:04d}-{m:02d}" for y, m in month_keys],
        "area_counts": area,
        "citywide_counts": city,
    }
    _trends_cache[key] = value
    _trends_expires[key] = now() + TRENDS_CACHE_TTL_S
    return value
```

`_cached_series` is a small private helper that checks `_trends_cache`/`_trends_expires` for its own key, else calls `area_month_counts(session, column, values, start, end, offense_category, None, None, sources=sources)` (mirror the exact keyword usage of the call sites at `neighborhood_service.py:364-388`) and zero-fills with `[counts.get(k, 0) for k in month_keys]`, caching the list. Note the citywide list is cached independently of MCPP — that sharing is the point.

- [ ] **Step 4: Run tests**

`pytest tests/test_trends_service.py tests/ -k "trends or neighborhood" -q` — expect PASS. Also `ruff check .`.

- [ ] **Step 5: Commit**

```bash
git add app/services/ tests/test_trends_service.py
git commit -m "feat(trends): monthly MCPP+citywide series service with TTL cache"
```

### Task 2: Route, cache-reset fixture, API tests

**Files:**
- Modify: `app/api/routes_public_dashboard.py` (new handler; imports)
- Modify: `tests/conftest.py` (autouse reset fixture)
- Modify: `tests/test_internal_surface.py` (add `/dashboard/trends` to `PUBLIC_PATHS`)
- Test: `tests/test_dashboard_trends_api.py`

- [ ] **Step 1: Write failing API tests**

`tests/test_dashboard_trends_api.py`, following `tests/test_dashboard_freshness.py`'s structure (create_app + TestClient + `client.post("/sessions")`):

```python
def test_trends_requires_a_public_session(app_client_no_session):
    response = app_client_no_session.get("/dashboard/trends?mcpp=TEST HILL")
    assert response.status_code == 401


def test_trends_unknown_mcpp_is_404(client):
    assert client.get("/dashboard/trends?mcpp=NOWHEREVILLE").status_code == 404


def test_trends_bad_layer_is_400(client):
    assert client.get("/dashboard/trends?mcpp=TEST HILL&layer=nope").status_code == 400


def test_trends_normalizes_mcpp_case(client_with_seeds):
    response = client_with_seeds.get("/dashboard/trends?mcpp=Test Hill")
    assert response.status_code == 200
    assert response.json()["mcpp"] == "TEST HILL"


def test_trends_empty_db_returns_zero_filled_series(client):
    body = client.get("/dashboard/trends?mcpp=TEST HILL").json()
    assert len(body["months"]) == len(body["area_counts"])
    assert set(body["area_counts"]) == {0}
```

Run: `pytest tests/test_dashboard_trends_api.py -q` — expect 404-for-route FAILs.

- [ ] **Step 2: Implement the handler**

In `app/api/routes_public_dashboard.py` (imports: `normalize_mcpp` from `app.analysis.area_baselines`, `LAYER_REPORTED`, `sources_for_layer` from `app.crime.sources`, `trends_for_mcpp` from `app.services.trends_service`; reuse the existing `_mcpp_areas()` lru accessor at :54-61 for validation):

```python
@router.get("/dashboard/trends")
def dashboard_trends(
    _user_id_hash: Annotated[str, Depends(required_public_user_hash)],
    session: Annotated[Session, Depends(get_session)],
    mcpp: Annotated[str, Query(max_length=80)],
    layer: Annotated[str, Query(max_length=20)] = LAYER_REPORTED,
    category: Annotated[str | None, Query(max_length=80)] = None,
) -> dict[str, object]:
    try:
        sources_for_layer(layer)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    name = normalize_mcpp(mcpp)
    if name is None or name not in _mcpp_areas():
        raise HTTPException(status_code=404, detail="Unknown MCPP")
    return trends_for_mcpp(session, mcpp=name, layer=layer, offense_category=category)
```

- [ ] **Step 3: Autouse cache reset + public-contract entry**

`tests/conftest.py`, next to `_reset_freshness_cache`:

```python
@pytest.fixture(autouse=True)
def _reset_trends_cache():
    reset_trends_cache()
    yield
```

Add `"/dashboard/trends"` to `PUBLIC_PATHS` in `tests/test_internal_surface.py`.

- [ ] **Step 4: Run tests**

`pytest tests/test_dashboard_trends_api.py tests/test_internal_surface.py -q` then full `pytest -q` — expect PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/routes_public_dashboard.py tests/
git commit -m "feat(trends): public GET /dashboard/trends endpoint"
```

### Task 3: Guard follow-up — trend-flavored safety asks

**Files:**
- Modify: `app/assistant/agent.py:71-77` (`_AMBIGUOUS_TERM_PATTERN`)
- Test: extend the existing guard test module (find it: `grep -rl "_AMBIGUOUS_TERM_PATTERN\|contains_safety_ranking" tests/`)

- [ ] **Step 1: Write failing tests** (in the guard's existing test file, matching its existing parametrize style)

```python
# trips: ambiguous trend term + place context
("is this neighborhood getting worse?", True),
("¿este barrio está empeorando?", True),
# safe: no place context
("my chess rating is getting worse", False),
("the compile times got worse after the upgrade", False),
```

Run the guard test file — expect the two `True` cases to FAIL.

- [ ] **Step 2: Extend the pattern**

In `_AMBIGUOUS_TERM_PATTERN` (line 72-75), add one alternation to the existing lexicon, before `|avoid`:

```python
    r"|seed(?:y|ier|iest)|scar(?:y|ier|iest)|frightening|ghetto"
    r"|wors(?:e|ening)|empeor\w*|peor(?:es)?"
    r"|segur[oa]s?|insegur[oa]s?|tranquil[oa]s?|conflictiv[oa]s?"
```

Do NOT touch `_UNAMBIGUOUS_SAFETY_PATTERN` or the English `bad/worst` exclusion.

- [ ] **Step 3: Run the full guard/assistant test module** — expect PASS, no regressions.

- [ ] **Step 4: Commit**

```bash
git add app/assistant/agent.py tests/
git commit -m "feat(guard): refuse trend-flavored safety asks (worse/empeorando + place)"
```

### Task 4: Frontend math + types + client wrapper

**Files:**
- Create: `frontend/src/lib/trendMath.ts`
- Modify: `frontend/src/types.ts` (add `TrendsResponse`)
- Modify: `frontend/src/api/client.ts` (add `getTrends`)
- Test: `frontend/src/lib/trendMath.test.ts`, extend `frontend/src/api/client.test.ts`

- [ ] **Step 1: Failing tests for the math** (`trendMath.test.ts`, no jsdom pragma needed — pure logic)

```ts
import { describe, expect, it } from "vitest";
import { anchorFactor, indexCitywide, rollingMean12 } from "./trendMath";

describe("anchorFactor", () => {
  it("is the pooled sum ratio over the first 12 months", () => {
    const area = [...Array(12).fill(3), 9, 9];      // ΣA(anchor)=36
    const city = [...Array(12).fill(300), 1, 1];    // ΣC(anchor)=3600
    expect(anchorFactor(area, city)).toBeCloseTo(0.01);
  });
  it("is null when the anchor area sum is zero", () => {
    expect(anchorFactor(Array(14).fill(0), Array(14).fill(100))).toBeNull();
  });
  it("is null when fewer than 13 months exist", () => {
    expect(anchorFactor(Array(12).fill(1), Array(12).fill(10))).toBeNull();
  });
});

describe("rollingMean12", () => {
  it("is null before month 12 and a trailing mean after", () => {
    const out = rollingMean12([...Array(11).fill(0), 12, 24]);
    expect(out[10]).toBeNull();
    expect(out[11]).toBeCloseTo(1);                  // (0×11 + 12)/12
    expect(out[12]).toBeCloseTo(3);                  // (0×10 + 12 + 24)/12
  });
});

describe("indexCitywide", () => {
  it("rescales by k", () => {
    expect(indexCitywide([100, 200], 0.01)).toEqual([1, 2]);
  });
});
```

Run: `cd frontend && npx vitest run src/lib/trendMath.test.ts` — expect FAIL.

- [ ] **Step 2: Implement `trendMath.ts`**

```ts
// Frontend half of docs/analysis/trend-indexing-method.md §8.
export const ANCHOR_MONTHS = 12;

const sum = (xs: number[]) => xs.reduce((a, b) => a + b, 0);

export function anchorFactor(area: number[], city: number[]): number | null {
  if (area.length < ANCHOR_MONTHS + 1 || city.length !== area.length) return null;
  const a = sum(area.slice(0, ANCHOR_MONTHS));
  const c = sum(city.slice(0, ANCHOR_MONTHS));
  if (a === 0 || c === 0) return null;
  return a / c;
}

export function rollingMean12(series: number[]): (number | null)[] {
  return series.map((_, i) =>
    i < ANCHOR_MONTHS - 1 ? null : sum(series.slice(i - ANCHOR_MONTHS + 1, i + 1)) / ANCHOR_MONTHS,
  );
}

export function indexCitywide(city: number[], k: number): number[] {
  return city.map((v) => v * k);
}
```

- [ ] **Step 3: Types + client wrapper**

`types.ts`:

```ts
export type TrendsResponse = {
  layer: LayerKey;
  mcpp: string;
  mcpp_label: string;
  category: string | null;
  months: string[];
  area_counts: number[];
  citywide_counts: number[];
};
```

`client.ts` (first GET-with-querystring wrapper; thread `signal` like `getIncidentPoints` at :161-170):

```ts
export function getTrends(
  params: { mcpp: string; layer: string; category?: string | null },
  signal?: AbortSignal,
): Promise<TrendsResponse> {
  const search = new URLSearchParams({ mcpp: params.mcpp, layer: params.layer });
  if (params.category) search.set("category", params.category);
  return request<TrendsResponse>(`/dashboard/trends?${search.toString()}`, { signal });
}
```

Add a `client.test.ts` case asserting the built URL and `credentials: "include"` (mirror the existing fetch-spy pattern at :26-32).

- [ ] **Step 4: Run** `npx vitest run src/lib/trendMath.test.ts src/api/client.test.ts` — expect PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/trendMath.* frontend/src/types.ts frontend/src/api/
git commit -m "feat(trends): frontend trend math, types, and API wrapper"
```

### Task 5: `useTrends` hook

**Files:**
- Create: `frontend/src/lib/useTrends.ts`
- Test: `frontend/src/lib/useTrends.test.ts` (mirror `useIncidentPoints.test.ts` — read it first and copy its mocking/`renderHook` mechanics)

- [ ] **Step 1: Failing tests** — cases: (a) null mcpp → no fetch, data null; (b) fetch fires after 300 ms debounce with the right params; (c) param change aborts the in-flight request (assert first controller aborted); (d) error sets `error` and clears `data`. Copy the timer/abort test scaffolding from `useIncidentPoints.test.ts` verbatim.

- [ ] **Step 2: Implement** — clone `useIncidentPoints.ts:51-121` mechanics exactly (300 ms trailing debounce, `AbortController` in a ref, abort-before-refire, cleanup aborts, `signal.aborted` guards before every state write), with deps `[mcpp, layer, category]`, calling `getTrends({ mcpp, layer, category }, controller.signal)`. Shape:

```ts
export function useTrends(
  mcpp: string | null,
  layer: string,
  category: string | null,
): { data: TrendsResponse | null; loading: boolean; error: string | null };
```

`mcpp === null` clears state and skips fetching (the `bounds === null` hold-off pattern).

- [ ] **Step 3: Run** `npx vitest run src/lib/useTrends.test.ts` — PASS.
- [ ] **Step 4: Commit** — `git commit -m "feat(trends): useTrends lazy fetch hook"`

### Task 6: `TrendChart` SVG + styles

**Files:**
- Create: `frontend/src/components/TrendChart.tsx`
- Modify: `frontend/src/styles/mapWorkspace.css` (new `.mc-trend*` block after `.mc-bplot*` ~line 597)
- Test: `frontend/src/components/TrendChart.test.tsx` (`// @vitest-environment jsdom` first line)

- [ ] **Step 1: Failing tests** — render with a 60-month fixture; assert: `data-testid="trend-chart"` exists; three `path`s when citywide provided (`data-testid` `trend-raw`, `trend-rolling`, `trend-city`); `trend-city` absent when `citywide` prop is null; January tick labels rendered (e.g. `2022`); hovering (`fireEvent.pointerMove`) shows the readout row (`data-testid="trend-readout"`) with rounded integer values.

- [ ] **Step 2: Implement**

Props and geometry (fixed viewBox, pure helpers — the `LocatorChip`/`locatorGeometry` precedent):

```tsx
type TrendChartProps = {
  months: string[];                 // "YYYY-MM"
  area: number[];
  rolling: (number | null)[];
  citywide: number[] | null;        // indexed values, or null (suppressed overlay)
};

const W = 560, H = 170, PAD_L = 34, PAD_R = 8, PAD_T = 8, PAD_B = 20;
```

`domainMax = 1.05 × max(all provided series, 1)` (zero-anchored, the `plotDomainMax` convention); `x(i) = PAD_L + (i / (n - 1)) × (W - PAD_L - PAD_R)`; `y(v) = PAD_T + (1 - v / domainMax) × (H - PAD_T - PAD_B)`. Null-skipping path builder:

```tsx
function linePath(values: (number | null)[], x: (i: number) => number, y: (v: number) => number): string {
  let d = "";
  let pen = false;
  values.forEach((v, i) => {
    if (v == null) { pen = false; return; }
    d += `${pen ? "L" : "M"}${x(i).toFixed(1)} ${y(v).toFixed(1)}`;
    pen = true;
  });
  return d;
}
```

Marks (neutral tokens, identical in both themes — the CSS invariant comment at `mapWorkspace.css:604-606`): raw = `stroke: var(--slate-soft)`, 1.5px; rolling = `var(--graphite)`, 2.5px; citywide = `var(--text-dim)`, 2px, `stroke-dasharray: 6 4`; all `fill="none"`, `stroke-linejoin/linecap="round"`. X ticks: indices where `months[i].endsWith("-01")`, label `months[i].slice(0, 4)`. Y: 3 gridlines + integer labels (`Math.round`). Hover: `onPointerMove` on the `<svg>` → nearest index from `clientX` via `getBoundingClientRect()`, `useState<number | null>`, vertical `<line>` + a readout row above the chart showing `{month}: {area} · avg {Math.round(rolling ?? …)} · citywide (indexed) {Math.round(city)}`; `onPointerLeave` clears. Aria: `role="img"` + `aria-label` naming the MCPP and window.

CSS block: `.mc-trend { border-top: 1px solid var(--border); padding-top: 10px; margin-top: 10px; }`, `.mc-trend-legend`/`.mc-trend-readout` at `font-size: 11px; color: var(--text-dim);`, legend swatches as 18×0 spans with `border-top` styles matching the three marks, `.mc-trend svg { width: 100%; height: auto; display: block; }`, `.mc-trend-note { font-size: 10.5px; color: var(--text-dim); }` — follow the `.mc-bplot` rhythm.

- [ ] **Step 3: Run** `npx vitest run src/components/TrendChart.test.tsx` — PASS.
- [ ] **Step 4: Commit** — `git commit -m "feat(trends): neutral-mark SVG trend chart"`

### Task 7: `TrendSection` + AnalyzeTab integration + copy pinning

**Files:**
- Create: `frontend/src/components/TrendSection.tsx`
- Modify: `frontend/src/components/AnalyzeTab.tsx` (render between the verdict-card map at :616-632 and `<PairwiseSection …>` at :634)
- Test: `frontend/src/components/TrendSection.test.tsx`

- [ ] **Step 1: Failing tests** — mock `../api/client`'s `getTrends` (vi.mock) with a canned 60-month `TrendsResponse`. Cases:
  - renders title "Reported incident volume over time" and subtitle "… · last 5 years · monthly" for layer `reported`;
  - calls layer: subtitle contains "last 24 months — data floor" (mock a 24-month response);
  - both footnote strings present ("direction, not magnitude" / "not verified events");
  - multi-MCPP: two places with different `baselines[kind=mcpp].label` → chip row with both labels; clicking the second refetches with its name;
  - suppressed overlay: response whose first-12 area sum is 0 → no `trend-city` path, note shown;
  - short window (< 13 months) → raw only + note;
  - **verdict-vocabulary guard:** `expect(container.textContent).not.toMatch(/\b(safe|unsafe|danger\w*|risk\w*|improv\w*|worsen\w*|worse|better)\b/i)` on every rendered state.

- [ ] **Step 2: Implement `TrendSection.tsx`**

```tsx
type TrendSectionProps = {
  neighborhood: NeighborhoodAnalysis;
  layer: LayerKey;
  category: string | null;
};
```

- Derive unique MCPP labels: `neighborhood.places.flatMap(p => p.baselines?.find(b => b.kind === "mcpp")?.label ?? [])`, de-duped in order; none → return null. `useState` for the selected label (default first, reset when the list changes).
- `const { data, loading, error } = useTrends(selected, layer, category);` (backend normalizes the label).
- Compute `k = anchorFactor(data.area_counts, data.citywide_counts)`, `rolling = rollingMean12(...)`, `city = k == null ? null : indexCitywide(...)`; short window (`months.length < 13`) → pass `rolling` as all-null and `citywide: null`.
- Copy (exact strings, pinned by the tests):

```tsx
const TITLES: Record<LayerKey, string> = {
  reported: "Reported incident volume over time",
  arrests: "Arrest volume over time",
  calls: "911 call volume over time",
};
const COUNT_NOTES: Record<LayerKey, string> = {
  reported: "Counts are reported incidents, not verified events.",
  arrests: "Counts are arrests — enforcement activity, not reported incidents.",
  calls: "Counts are 911 calls — requests for service, not confirmed incidents.",
};
const INDEX_NOTE =
  "Citywide series is indexed to this area's scale — it shows direction, not magnitude.";
const ANCHOR_SUPPRESSED_NOTE =
  "Too few incidents in the anchor period to index the citywide series.";
const SHORT_WINDOW_NOTE = "Not enough complete months for a trend view yet.";
```

Subtitle: `` `${data.mcpp_label} · ${layer === "calls" ? "last 24 months — data floor" : "last 5 years"} · monthly · fixed window` ``. Legend labels: "Monthly count", "12-month average", "Citywide, indexed" (omit the third when suppressed). Loading → the existing skeleton style; error → the shared inline-error style used by AnalyzeTab.

- [ ] **Step 3: Wire into `AnalyzeTab.tsx`**

After the `neighborhood?.places?.map(...)` block and before `<PairwiseSection …>`:

```tsx
{!running && neighborhood ? (
  <TrendSection
    neighborhood={neighborhood}
    layer={analysis.layer}
    category={analysis.offenseCategory || null}
  />
) : null}
```

Check `AnalyzeTab.test.tsx` still passes (its fixtures now render the section — mock `getTrends` in that file's setup if it fetches).

- [ ] **Step 4: Run** `npx vitest run src/components/ -q` then the whole suite `npm test` — PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(trends): volume-over-time section on Analyze"`

### Task 8: Docs + full verification

**Files:**
- Modify: `docs/architecture/api.md` (endpoint row in the public-tier table, matching neighbors' format)
- Modify: `docs/ROADMAP.md` (shipped entry under the newest section)
- Spec: fill "Shipped deviations" if any accrued

- [ ] **Step 1: api.md** — add `GET /dashboard/trends` to the public endpoint table: session-gated; `mcpp` (normalized, 404 unknown), `layer` (400 unknown), `category`; returns raw monthly `area_counts`/`citywide_counts`, zero-filled, last complete month; TTL-cached; math in `docs/analysis/trend-indexing-method.md`.

- [ ] **Step 2: ROADMAP.md** — new checked entry:

```markdown
- [x] **Analyze trend section — volume over time (2026-07-16):** descriptive monthly
  MCPP-vs-citywide series on Analyze (12-month rolling mean, anchored-indexed citywide
  overlay — methodology: `docs/analysis/trend-indexing-method.md`), lazy
  `GET /dashboard/trends` with shared citywide TTL cache; guard broadened for
  trend-flavored safety asks (worse/empeorando + place context). Spec/plan:
  `docs/superpowers/{specs,plans}/2026-07-16-analyze-trend-section*`.
```

- [ ] **Step 3: Full gate**

Run: `make test-all` (pytest + ruff + frontend npm test + build). Expect: all green. Fix anything that isn't before proceeding.

- [ ] **Step 4: Commit** — `git commit -m "docs(trends): api reference + roadmap entry"`

---

## Self-review notes

- Spec coverage: endpoint contract → Tasks 1–2; guard → Task 3; math/types/client → Task 4; hook → Task 5; chart+styles → Task 6; section/placement/copy/suppression/multi-MCPP → Task 7; docs rows → Task 8. Window/zero-fill/complete-month/cache each have explicit tests.
- Postgres `func.timezone` branch is inherited by reusing `area_month_counts` (not re-implemented) — that's deliberate; do not write a new GROUP BY.
- Naming consistency: `months_between`/`area_month_counts` (Task 1) are the names imported in `trends_service.py`; `getTrends`/`useTrends`/`TrendsResponse` consistent across Tasks 4–7.
