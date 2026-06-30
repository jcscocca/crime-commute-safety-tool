# Temporal Analysis — Design (Phase 4, item C1)

> Status: design approved via brainstorming 2026-06-29. First item of the new **Phase 4**
> slate (a blend of *harden & polish* and *new capabilities*; see `docs/ROADMAP.md`).
> **Descriptive-only**, **Places Analyze tab only**. Comparative/baseline temporal, route
> corridor-temporal, and an assistant temporal tool are deliberately deferred to later Phase 4
> slices.

## Objective

Show **when** reported incidents occur around a place — a **hour-of-day** profile and a
**day-of-week** profile — and let the user **highlight their actual travel window** with a
plain share-of-count callout. Waypoint is a *commute* context tool; "when you travel" is as
important as "where." This is strictly descriptive context, never a "safe time" judgment.

## Product invariant (must hold)

Waypoint reports reported-incident context, not safety. The temporal surface is **descriptive
only**: no "safest time", no "avoid these hours", no recommendation. The API returns **numbers
only** (counts); the frontend renders the neutral copy. The travel-window callout is a pure
share statement ("X% of reported incidents fell in this window"). A test asserts the temporal
API payload carries no `safe/unsafe/dangerous/risk`-style language.

## Current context

- `neighborhood_analysis_for_places` (`app/services/neighborhood_service.py:113`) already
  fetches the in-radius incident set per place (`_incidents_in_radius`) and derives per-place
  `type_mix` (`_type_mix`) and `monthly_counts` (`_monthly_counts`). **Temporal buckets are
  computed from that same in-radius set — no new query.**
- `CrimeIncident` carries `offense_start_utc` (UTC, nullable, **indexed**), `offense_end_utc`,
  `report_utc`, plus `offense_category`/`beat`/lat-lng (`app/models.py:118`).
- The per-place neighborhood result object already carries `type_mix`, `monthly_counts`,
  `place_incident_count`, the analysis window, etc. `temporal` is added **alongside** these.
- API surface: `app/routers/dashboard_schemas.py` (response models) and
  `app/routers/routes_public_dashboard.py` (the public analyze endpoint).
- Frontend: `frontend/src/components/AnalyzeTab.tsx`, the `useAnalyze` hook, and shared
  helpers under `frontend/src/lib/`.

## Approved decisions

| Decision | Choice |
|---|---|
| Rigor | **Descriptive only** — no comparative/baseline rate-ratio per bucket |
| Dimensions | **Two 1D profiles**: hour-of-day (24) + day-of-week (Mon–Sun) |
| Travel window | **Highlight + client-side share callout** — no engine change |
| Surface | **Places Analyze tab only** |
| Compute location | Pure module `app/analysis/temporal.py`, wired into the existing analyze path |
| Timestamp | **`offense_start_utc`** (occurrence); `report_utc` **never** used for time-of-day |
| Time zone | Stored value is **naive Seattle local** — read `.hour`/`.weekday()` directly, **no conversion** (see Timezone semantics) |
| Missing time | Incidents lacking a timestamp are counted as `without_time`, **not dropped** |

## Timezone semantics (resolved — read as naive Seattle local)

**Confirmed in code:** `app/crime/seattle_socrata.py:71` maps SPD's `offense_start_datetime`
through `parse_datetime`, and `parse_datetime` (`app/parsers/base.py:48`) stamps **naive**
values with `.replace(tzinfo=UTC)` — i.e. it labels the value UTC **without converting**. SPD
publishes naive **Seattle local wall-clock** with no timezone indicator. Therefore
`offense_start_utc` holds **Seattle local time mislabeled as UTC**.

**Decision:** extract hour/weekday **directly** from the stored datetime's wall-clock fields —
**no `zoneinfo` conversion**. Converting "UTC"→`America/Los_Angeles` would *double-shift* every
bucket by ~7–8h and be wrong. A tiny helper `local_hour_dow(dt) -> (hour, dow)` returns
`(dt.hour, dt.weekday())` (Mon=0…Sun=6), with a comment documenting why no shift is applied.

**Pin it with a test** so a future "fix the misnamed column" change can't silently break this: a
stored `2024-02-10T23:30Z` value must yield `hour=23` (no shift), not `hour=15`/`16`.

> Scope note: this holds for `source_dataset="seattle_spd_crime"` (the only dataset in play).
> The column **misnomer** (`*_utc` holding local time) is a pre-existing data-hygiene wart used
> *consistently* elsewhere (counts/rate windows are tz-label-agnostic), so renaming it is a
> separate migration, **out of scope** here — noted as a possible Phase 4 follow-up.

## Server design

### `app/analysis/temporal.py` (new, pure — matches `comparison.py` / `exposure.py` / `rate_tests.py`)

```
build_temporal_profile(incidents) -> TemporalProfile
```

- **Input:** iterable of incidents exposing `offense_start_utc` (verify `CrimeIncidentData`
  carries it; thread it through the projection if the in-radius fetch currently drops it).
  Local hour/weekday come from `local_hour_dow` (read directly — see Timezone semantics).
- **Output** (`TemporalProfile`):
  - `hour_counts: list[int]` — length 24, local hour 0–23
  - `dow_counts: list[int]` — length 7, Mon=0 … Sun=6
  - `hour_by_dow: list[list[int]]` — 7×24 joint matrix (enables an **exact** travel-window
    stat — e.g. "weekday evenings" — which the two 1D marginals alone cannot reconstruct)
  - `total_with_time: int`
  - `without_time: int` (incidents whose `offense_start_utc` is null)
- Pure, no DB / no IO. `hour_counts` and `dow_counts` are the marginals of `hour_by_dow`
  (returned explicitly for a friendlier contract and simpler tests).

### Schema (`app/routers/dashboard_schemas.py`)

Add a `TemporalProfile` pydantic model and a `temporal: TemporalProfile | None` field on the
per-place neighborhood result model. The display window dates reuse the analysis window already
present on the response (no duplication). `temporal` is `null` when a place has no located
incidents.

### Service wiring (`app/services/neighborhood_service.py`)

In `neighborhood_analysis_for_places`, after the per-place in-radius incident list is built,
call `build_temporal_profile(...)` and attach the result to that place's output object — the
same place the existing `type_mix` / `monthly_counts` are attached.

## Frontend design

### `TemporalSection` component (new)

Given a place's `temporal` and the analysis window:

- **Two bar profiles** rendered from the marginals: a 24-bar **hour-of-day** profile (with
  light AM/PM ticks) and a 7-bar **day-of-week** profile (Mon–Sun).
- A **travel-window control**: a day-set (weekdays / weekends / custom) + a contiguous hour
  range. Defaults to a typical weekday commute window (editable); copy stays share-only and
  neutral. The selected cells are rendered as a highlight overlay on both profiles.
- A **callout** computed **client-side** from `hour_by_dow` (instant; no round-trip on adjust):
  *"42% of the {total_with_time} reported incidents with a recorded time ({window}) fell in
  your travel window."*
- **Low-sample note** when `total_with_time < 20`:
  "Based on {N} incidents — interpret with caution."
- **Missing-time footnote** when `without_time > 0`: "{M} incidents had no recorded time and
  aren't shown here."
- **Empty state** when `total_with_time == 0`: "No reported incidents with a recorded time in
  this area."

### `AnalyzeTab` wiring

Render a `TemporalSection` per place, in a labeled subsection ("When reported incidents
occurred") beneath that place's `VerdictCard`. The verdict stays the lead; temporal is a
compact secondary section, shown inline when `temporal` is present (it is the headline
capability of this unit, so not hidden behind a reveal). Neutral palette consistent with the
redesigned tab.

## Error / edge cases

- `temporal` null or `total_with_time == 0` → empty state, no bars.
- `without_time > 0` → footnote (counts shown honestly).
- Low `total_with_time` → caution note.
- `offense_start_utc` null → counted in `without_time`, never silently dropped.
- Travel window selecting zero incidents → "0% — no reported incidents in your window."
- DST boundary correctness is a tested behavior (see landmine above).

## Testing

**Backend**
- `local_hour_dow` helper: a stored `...T23:30Z` value yields `hour=23` (no shift) — the pin
  test guarding the naive-Seattle-local semantics against a future column rename.
- `build_temporal_profile`: bucketing into hour & dow; `hour_counts`/`dow_counts` equal the
  marginals of `hour_by_dow`; nulls counted in `without_time`; empty input → all-zero profile;
  a Sunday-23:00-local incident lands in `dow=6, hour=23`.
- Service: `temporal` attached to each place; respects the analysis window.
- API contract: the analyze response includes `temporal` with length-24 / length-7 arrays.
- Invariant: the temporal API payload contains no `safe/unsafe/dangerous/risk` language
  (numbers only).

**Frontend**
- `TemporalSection`: profiles render from the marginals; the travel-window callout updates from
  `hour_by_dow` and a weekday-evening window yields the expected %; low-N note; missing-time
  footnote; empty state.

**Gate:** `make test-all` (pytest + ruff + `npm test` + `npm run build`) in the worktree.

## Roadmap tick

The PR folds a **Phase 4** section into `docs/ROADMAP.md` capturing the slate (H1–H4, C1–C4)
and marks **C1 temporal analysis** as the first item, per the established cadence. It also
reconciles the now-stale "Maturity snapshot" rows that the completed Phases 0–3 already
superseded (data-freshness in UI, MapWorkspace split, safety-guard regex gap).

## Non-Goals

- Comparative/baseline temporal (rate-ratio per time bucket) — a future Phase 4 slice.
- Route corridor-temporal and an assistant temporal tool — queued in the Phase 4 slate.
- A 2D day×time **heatmap display** — the joint matrix is used only to compute the window
  stat, never rendered as a grid (avoids small-sample sparsity).
- Filtering the *rest* of the analysis by the travel window (we chose highlight, not filter).
- Any new data ingestion or schema migration on `crime_incidents`.
