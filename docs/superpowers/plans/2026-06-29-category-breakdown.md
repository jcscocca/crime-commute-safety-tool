# Category Breakdown Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat `type_mix` list (label + raw count) with a richer `category_breakdown` that shows each incident type's *share* of the place's incidents side-by-side with the type's *share in the surrounding beat* — so the reader can see whether, say, Theft is over-represented locally relative to the neighbourhood.

**Architecture:** A pure helper `_category_breakdown` in `app/services/neighborhood_service.py` (same file as `_type_mix`, which it replaces) takes the place's incidents and optionally the beat's incidents, buckets by `offense_subcategory → offense_category → "Uncategorized"`, returns the top-N rows (plus an aggregated "Other") each carrying `{ label, place_count, place_share, beat_share }`. The helper is wired into the three existing `type_mix` attachment points; `type_mix` is removed from both the service dict and the frontend type. The frontend replaces the `<li>{label} · {count}</li>` list with a compact row layout showing place share vs beat share; new `.mc-cat*` CSS classes follow the existing `mc-temporal*` pattern. The bare-dict response (no pydantic `response_model`) means the schema change is a dict-key rename, not a model migration.

**Tech stack:** Python 3.11 / FastAPI / SQLAlchemy / pytest; React + TypeScript + Vite / vitest + testing-library. Run from the worktree `/.worktrees/c2-category-breakdown`.

**Spec:** the locked decomposition in the prompt, 2026-06-29.

**Key resolved facts:**
- `type_mix` consumers: `app/services/neighborhood_service.py` (lines 107–112 helper, lines 241/254/298 attachments); `frontend/src/types.ts` (line 227); `frontend/src/components/AnalyzeTab.tsx` (lines 278–282); `frontend/src/components/AnalyzeTab.test.tsx` (line 40). No other consumers.
- The `/dashboard/neighborhood` endpoint returns a bare dict (no pydantic `response_model`). The schema change is a dict-key rename only. The `app/api/dashboard_schemas.py` file contains request models only and is not modified.
- The fixture in `tests/helpers_dashboard.py` seeds 5 near-incidents (`offense_subcategory="Theft"`) and 8 far-incidents (`offense_subcategory="Burglary"`). In a full-analysis run, the rest-of-beat baseline has 8 "Burglary" incidents; the place has 5 "Theft" incidents.
- `.mc-temporal*` styles live at `frontend/src/styles/mapWorkspace.css` lines 457–470. The new `.mc-cat*` block goes immediately after, using the same variable set.

---

## Task 1: Backend `_category_breakdown` helper + unit tests

**Files:**
- Modify: `app/services/neighborhood_service.py`
- Create: `tests/test_category_breakdown.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_category_breakdown.py`:

```python
from app.schemas import CrimeIncidentData
from app.services.neighborhood_service import _category_breakdown


def _inc(subcategory: str | None = None, category: str | None = None) -> CrimeIncidentData:
    return CrimeIncidentData(offense_subcategory=subcategory, offense_category=category)


# ---------------------------------------------------------------------------
# Bucketing / label fallback
# ---------------------------------------------------------------------------

def test_bucketing_prefers_subcategory():
    incidents = [_inc(subcategory="Theft", category="PROPERTY")]
    rows = _category_breakdown(incidents, None)
    assert rows[0]["label"] == "Theft"


def test_bucketing_falls_back_to_category():
    incidents = [_inc(subcategory=None, category="PROPERTY")]
    rows = _category_breakdown(incidents, None)
    assert rows[0]["label"] == "PROPERTY"


def test_bucketing_falls_back_to_uncategorized():
    incidents = [_inc(subcategory=None, category=None)]
    rows = _category_breakdown(incidents, None)
    assert rows[0]["label"] == "Uncategorized"


# ---------------------------------------------------------------------------
# Top-N + Other fold
# ---------------------------------------------------------------------------

def test_top_n_default_is_6_and_other_folds_remainder():
    # 7 distinct labels → top 6 by count, "Other" for the 7th.
    incidents = (
        [_inc(subcategory="A")] * 7
        + [_inc(subcategory="B")] * 6
        + [_inc(subcategory="C")] * 5
        + [_inc(subcategory="D")] * 4
        + [_inc(subcategory="E")] * 3
        + [_inc(subcategory="F")] * 2
        + [_inc(subcategory="G")] * 1  # lowest → folded into Other
    )
    rows = _category_breakdown(incidents, None)
    labels = [r["label"] for r in rows]
    assert "Other" in labels
    assert "G" not in labels
    assert labels[-1] == "Other"  # Other is always last
    other = rows[-1]
    assert other["place_count"] == 1


def test_fewer_than_top_n_labels_produces_no_other():
    incidents = [_inc(subcategory="A")] * 3 + [_inc(subcategory="B")] * 2
    rows = _category_breakdown(incidents, None)
    assert all(r["label"] != "Other" for r in rows)


def test_custom_top_n():
    incidents = [_inc(subcategory="A")] * 3 + [_inc(subcategory="B")] * 2 + [_inc(subcategory="C")] * 1
    rows = _category_breakdown(incidents, None, top_n=2)
    labels = [r["label"] for r in rows]
    assert "A" in labels
    assert "B" in labels
    assert "C" not in labels
    assert labels[-1] == "Other"
    assert rows[-1]["place_count"] == 1


# ---------------------------------------------------------------------------
# Share math
# ---------------------------------------------------------------------------

def test_place_share_sums_to_1_for_top_rows_plus_other():
    incidents = (
        [_inc(subcategory="A")] * 3
        + [_inc(subcategory="B")] * 2
        + [_inc(subcategory="C")] * 1
    )
    rows = _category_breakdown(incidents, None, top_n=2)
    total_share = sum(r["place_share"] for r in rows)
    assert abs(total_share - 1.0) < 1e-9


def test_place_share_is_zero_when_total_is_zero():
    rows = _category_breakdown([], None)
    assert rows == []


def test_beat_share_is_none_when_baseline_is_none():
    incidents = [_inc(subcategory="Theft")]
    rows = _category_breakdown(incidents, None)
    assert rows[0]["beat_share"] is None


def test_beat_share_is_none_when_baseline_is_empty():
    incidents = [_inc(subcategory="Theft")]
    rows = _category_breakdown(incidents, [])
    assert rows[0]["beat_share"] is None


def test_beat_share_is_fraction_of_beat_total():
    place = [_inc(subcategory="Theft")] * 3
    baseline = [_inc(subcategory="Theft")] * 2 + [_inc(subcategory="Burglary")] * 8
    rows = _category_breakdown(place, baseline)
    theft_row = next(r for r in rows if r["label"] == "Theft")
    assert abs(theft_row["beat_share"] - 2 / 10) < 1e-9


def test_beat_only_label_does_not_appear_as_a_row():
    # "Assault" exists only in the beat, not the place — must NOT appear as a row.
    place = [_inc(subcategory="Theft")] * 3
    baseline = [_inc(subcategory="Theft")] * 2 + [_inc(subcategory="Assault")] * 5
    rows = _category_breakdown(place, baseline)
    assert all(r["label"] != "Assault" for r in rows)


def test_label_in_place_but_absent_in_beat_has_beat_share_zero():
    place = [_inc(subcategory="Theft")] * 3
    baseline = [_inc(subcategory="Burglary")] * 8  # Theft absent in baseline
    rows = _category_breakdown(place, baseline)
    theft_row = next(r for r in rows if r["label"] == "Theft")
    assert theft_row["beat_share"] == 0.0


# ---------------------------------------------------------------------------
# Other row beat_share uses the same top-N label set
# ---------------------------------------------------------------------------

def test_other_row_beat_share_aggregates_non_top_labels_in_beat():
    # top_n=2 → top labels are "A" (3) and "B" (2). "C" folds to Other.
    # Baseline: A=1, B=2, C=4. Other beat_share = C_in_beat / beat_total = 4/7.
    place = [_inc(subcategory="A")] * 3 + [_inc(subcategory="B")] * 2 + [_inc(subcategory="C")] * 1
    baseline = (
        [_inc(subcategory="A")] * 1
        + [_inc(subcategory="B")] * 2
        + [_inc(subcategory="C")] * 4
    )
    rows = _category_breakdown(place, baseline, top_n=2)
    other = next(r for r in rows if r["label"] == "Other")
    assert abs(other["beat_share"] - 4 / 7) < 1e-9


# ---------------------------------------------------------------------------
# Deterministic ordering
# ---------------------------------------------------------------------------

def test_ordering_is_place_count_desc_then_label_asc_other_last():
    place = (
        [_inc(subcategory="Burglary")] * 3
        + [_inc(subcategory="Assault")] * 3  # tie with Burglary → label asc
        + [_inc(subcategory="Theft")] * 2
    )
    rows = _category_breakdown(place, None, top_n=10)
    labels = [r["label"] for r in rows]
    # Both Assault and Burglary have count=3 → alphabetical puts Assault first.
    assert labels[0] == "Assault"
    assert labels[1] == "Burglary"
    assert labels[2] == "Theft"


def test_empty_place_list_returns_empty():
    rows = _category_breakdown([], None)
    assert rows == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_category_breakdown.py -q`
Expected: FAIL — `ImportError: cannot import name '_category_breakdown' from 'app.services.neighborhood_service'`.

- [ ] **Step 3: Write minimal implementation**

In `app/services/neighborhood_service.py`, add the following function immediately after `_type_mix` (after line 112):

```python
def _category_breakdown(
    place_incidents: list[CrimeIncidentData],
    baseline_incidents: list[CrimeIncidentData] | None,
    *,
    top_n: int = 6,
) -> list[dict[str, Any]]:
    """Per-category place-share vs beat-share breakdown.

    Buckets by ``offense_subcategory → offense_category → "Uncategorized"``.
    Returns the top ``top_n`` labels by place count; remaining labels are folded
    into a single ``"Other"`` row appended last.

    ``beat_share`` is each label's share of the beat total — the beat column does NOT
    need to sum to 100 % (beat-only labels are excluded entirely).
    ``beat_share`` is ``None`` when ``baseline_incidents`` is ``None`` or empty.
    """

    def _label(inc: CrimeIncidentData) -> str:
        return inc.offense_subcategory or inc.offense_category or "Uncategorized"

    place_counter: Counter[str] = Counter(_label(i) for i in place_incidents)
    place_total = sum(place_counter.values())

    if place_total == 0:
        return []

    # Build baseline lookup only when baseline is usable.
    baseline_counter: Counter[str] = Counter()
    baseline_total = 0
    has_baseline = baseline_incidents is not None and len(baseline_incidents) > 0
    if has_baseline:
        baseline_counter = Counter(_label(i) for i in baseline_incidents)
        baseline_total = sum(baseline_counter.values())

    # Sort all place labels by count desc then label asc to get a deterministic top-N.
    sorted_labels = sorted(place_counter.keys(), key=lambda lbl: (-place_counter[lbl], lbl))
    top_labels = sorted_labels[:top_n]
    remainder_labels = sorted_labels[top_n:]

    rows: list[dict[str, Any]] = []
    for label in top_labels:
        pc = place_counter[label]
        bc = baseline_counter.get(label, 0)
        rows.append(
            {
                "label": label,
                "place_count": pc,
                "place_share": pc / place_total,
                "beat_share": (bc / baseline_total) if has_baseline else None,
            }
        )

    if remainder_labels:
        other_place = sum(place_counter[lbl] for lbl in remainder_labels)
        other_beat = sum(baseline_counter.get(lbl, 0) for lbl in remainder_labels)
        rows.append(
            {
                "label": "Other",
                "place_count": other_place,
                "place_share": other_place / place_total,
                "beat_share": (other_beat / baseline_total) if has_baseline else None,
            }
        )

    return rows
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_category_breakdown.py -q`
Expected: PASS (all tests in the file).

- [ ] **Step 5: Commit**

```bash
git -C /Users/jscocca/Repos/Crime\ Commute\ Safety\ Tool/.worktrees/c2-category-breakdown \
  add app/services/neighborhood_service.py tests/test_category_breakdown.py
git -C /Users/jscocca/Repos/Crime\ Commute\ Safety\ Tool/.worktrees/c2-category-breakdown \
  commit -m "feat(analysis): _category_breakdown helper — place-share vs beat-share per type"
```

---

## Task 2: Service wiring + schema

**Files:**
- Modify: `app/services/neighborhood_service.py`
- Modify: `tests/test_neighborhood_service.py`
- Modify: `tests/test_dashboard_neighborhood_api.py`

> There is no pydantic `response_model` for the neighborhood endpoint — the response is a bare dict. "Schema" here means the dict-key rename from `type_mix` to `category_breakdown`. The `app/api/dashboard_schemas.py` file (request models only) is not modified.

- [ ] **Step 1: Write failing tests**

Append to `tests/test_neighborhood_service.py`:

```python
def test_neighborhood_analysis_attaches_category_breakdown_full_result(tmp_path):
    """Full-result branch: both place and beat incidents present → beat_share is not None."""
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
    place = result["places"][0]
    assert "type_mix" not in place
    bd = place["category_breakdown"]
    assert isinstance(bd, list)
    assert len(bd) >= 1
    # Full result has a real beat baseline → at least one row has non-null beat_share.
    assert any(r["beat_share"] is not None for r in bd)
    # All rows have the required keys.
    for row in bd:
        assert set(row.keys()) == {"label", "place_count", "place_share", "beat_share"}


def test_neighborhood_analysis_attaches_category_breakdown_degraded(tmp_path):
    """Degraded branch (no beat area): baseline is None → all beat_shares are None."""
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
        area_lookup={},  # no area → baseline_unavailable branch
        beat_polygons=_M3_POLYGONS,
    )
    place = result["places"][0]
    assert "type_mix" not in place
    bd = place["category_breakdown"]
    assert isinstance(bd, list)
    # No beat baseline → every row has beat_share = None.
    assert all(r["beat_share"] is None for r in bd)
```

Append to `tests/test_dashboard_neighborhood_api.py`:

```python
def test_neighborhood_endpoint_includes_category_breakdown_and_no_type_mix(neighborhood_client):
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
    place = body["places"][0]

    # type_mix must be gone.
    assert "type_mix" not in place

    # category_breakdown must be present and well-formed.
    bd = place["category_breakdown"]
    assert isinstance(bd, list)
    assert len(bd) >= 1
    for row in bd:
        assert set(row.keys()) == {"label", "place_count", "place_share", "beat_share"}
        assert isinstance(row["label"], str)
        assert isinstance(row["place_count"], int)
        assert isinstance(row["place_share"], float)
        # beat_share is float or null.
        assert row["beat_share"] is None or isinstance(row["beat_share"], float)

    # Full-result branch → at least one row has non-null beat_share.
    assert any(r["beat_share"] is not None for r in bd)

    # The fixture seeds place incidents all with subcategory="Theft";
    # the top row must reflect that label.
    assert bd[0]["label"] == "Theft"

    # Invariant: no safety language anywhere in the payload.
    blob = json.dumps(body).lower()
    for banned in ("unsafe", "dangerous", "safest", "risky", "avoid "):
        assert banned not in blob
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_neighborhood_service.py tests/test_dashboard_neighborhood_api.py -q`
Expected: FAIL — `KeyError: 'category_breakdown'` (or assertion on `type_mix not in place`).

- [ ] **Step 3: Replace `type_mix` with `category_breakdown` at the three attachment points**

In `app/services/neighborhood_service.py`, make the following three replacements.

**Attachment 1** — `baseline_unavailable` branch (around line 241). Replace:

```python
                    "type_mix": _type_mix(entry.get("place_incidents", [])),
                    "temporal": asdict(build_temporal_profile(entry.get("place_incidents", []))),
```

with:

```python
                    "category_breakdown": _category_breakdown(entry.get("place_incidents", []), None),
                    "temporal": asdict(build_temporal_profile(entry.get("place_incidents", []))),
```

**Attachment 2** — `baseline_too_small` / `insufficient_data` branch (around line 254). Replace:

```python
                    "type_mix": _type_mix(entry.get("place_incidents", [])),
                    "temporal": asdict(build_temporal_profile(entry.get("place_incidents", []))),
```

with:

```python
                    "category_breakdown": _category_breakdown(entry.get("place_incidents", []), None),
                    "temporal": asdict(build_temporal_profile(entry.get("place_incidents", []))),
```

**Attachment 3** — full-result branch (around line 298). Replace:

```python
                "type_mix": _type_mix(place_incidents),
                "temporal": asdict(build_temporal_profile(place_incidents)),
```

with:

```python
                "category_breakdown": _category_breakdown(place_incidents, beat_incidents),
                "temporal": asdict(build_temporal_profile(place_incidents)),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_neighborhood_service.py tests/test_dashboard_neighborhood_api.py -q`
Expected: PASS (all existing tests + the three new ones).

> Note: `_type_mix` is now dead code. Leave it in place until Task 2 is committed; remove it in this same commit.

- [ ] **Step 5: Remove dead `_type_mix`**

Delete the `_type_mix` function from `app/services/neighborhood_service.py` (lines 107–112 in the original file). Also remove `_type_mix` from the module-level `Any` usage (it is imported via `from typing import Any` which is still needed for `_category_breakdown`).

The removed block is:

```python
def _type_mix(incidents: list[CrimeIncidentData]) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for incident in incidents:
        label = incident.offense_subcategory or incident.offense_category or "Uncategorized"
        counter[label] += 1
    return [{"label": label, "count": count} for label, count in counter.most_common(6)]
```

- [ ] **Step 6: Run lint + full backend tests**

Run: `.venv/bin/ruff check app/services/neighborhood_service.py`
Expected: no errors (verify no unused import was left).

Run: `.venv/bin/pytest tests/test_neighborhood_service.py tests/test_dashboard_neighborhood_api.py tests/test_category_breakdown.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git -C /Users/jscocca/Repos/Crime\ Commute\ Safety\ Tool/.worktrees/c2-category-breakdown \
  add app/services/neighborhood_service.py \
      tests/test_neighborhood_service.py \
      tests/test_dashboard_neighborhood_api.py
git -C /Users/jscocca/Repos/Crime\ Commute\ Safety\ Tool/.worktrees/c2-category-breakdown \
  commit -m "feat(analysis): wire category_breakdown into neighborhood service; remove type_mix"
```

---

## Task 3: Frontend

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/components/AnalyzeTab.tsx`
- Modify: `frontend/src/components/AnalyzeTab.test.tsx`
- Modify: `frontend/src/styles/mapWorkspace.css`

- [ ] **Step 1: Write failing frontend tests**

In `frontend/src/components/AnalyzeTab.test.tsx`, make the following changes.

**a) Update the `homePlace` fixture** — replace the existing `type_mix` field on `homePlace` with `category_breakdown`.

Replace:

```ts
  nearest_incident_m: 42, monthly_counts: [1, 2, 1, 3, 2, 3], type_mix: [{ label: "ASSAULT", count: 7 }],
  temporal: {
```

with:

```ts
  nearest_incident_m: 42, monthly_counts: [1, 2, 1, 3, 2, 3],
  category_breakdown: [
    { label: "Theft", place_count: 5, place_share: 0.71, beat_share: 0.20 },
    { label: "Assault", place_count: 2, place_share: 0.29, beat_share: null },
  ],
  temporal: {
```

**b) Imports** — the new typed fixtures below annotate `: NeighborhoodPlace`, so ensure the test imports it: `import type { NeighborhoodPlace } from "../types";` (add it if the file doesn't already import the type). `tsc` (run in Step 7's build) will flag it if missing.

**c) Add four new `it(...)` tests** — append them inside the outer `describe("AnalyzeTab", () => {` block, just before the final closing `});`:

```ts
  it("renders incident type rows with place-share and beat-share", () => {
    const { container } = render(
      <AnalyzeTab selected={[home]} analysis={analysis} availableRadii={[250]} running={false} neighborhood={neighborhood} onChange={vi.fn()} onRun={vi.fn()} />,
    );
    const rows = container.querySelectorAll(".mc-cat-row");
    expect(rows.length).toBe(2);
    // First row: Theft — 71% here · 20% nearby.
    expect(rows[0].textContent).toMatch(/Theft/);
    expect(rows[0].textContent).toMatch(/71%/);
    expect(rows[0].textContent).toMatch(/20%/);
    // Second row: Assault — 29% here, no beat share.
    expect(rows[1].textContent).toMatch(/Assault/);
    expect(rows[1].textContent).toMatch(/29%/);
  });

  it("shows place share only when beat_share is null", () => {
    render(
      <AnalyzeTab selected={[home]} analysis={analysis} availableRadii={[250]} running={false} neighborhood={neighborhood} onChange={vi.fn()} onRun={vi.fn()} />,
    );
    // Assault row has beat_share: null → shows "29% here" but no "nearby".
    const assaultRow = Array.from(document.querySelectorAll(".mc-cat-row")).find(
      (el) => el.textContent?.includes("Assault"),
    );
    expect(assaultRow).toBeTruthy();
    expect(assaultRow!.textContent).toMatch(/29%/);
    expect(assaultRow!.textContent).not.toMatch(/nearby/);
  });

  it('renders an "Other" row when present in category_breakdown', () => {
    const withOther: NeighborhoodPlace = {
      ...homePlace,
      category_breakdown: [
        { label: "Theft", place_count: 5, place_share: 0.71, beat_share: 0.20 },
        { label: "Other", place_count: 2, place_share: 0.29, beat_share: 0.05 },
      ],
    };
    const { container } = render(
      <AnalyzeTab selected={[home]} analysis={analysis} availableRadii={[250]} running={false} neighborhood={{ ...neighborhood, places: [withOther] }} onChange={vi.fn()} onRun={vi.fn()} />,
    );
    const rows = container.querySelectorAll(".mc-cat-row");
    expect(rows.length).toBe(2);
    expect(Array.from(rows).some((el) => el.textContent?.includes("Other"))).toBe(true);
  });

  it("hides the category breakdown section when category_breakdown is empty", () => {
    const noBreakdown: NeighborhoodPlace = {
      ...homePlace,
      category_breakdown: [],
    };
    const { container } = render(
      <AnalyzeTab selected={[home]} analysis={analysis} availableRadii={[250]} running={false} neighborhood={{ ...neighborhood, places: [noBreakdown] }} onChange={vi.fn()} onRun={vi.fn()} />,
    );
    expect(container.querySelector(".mc-cat-breakdown")).not.toBeInTheDocument();
  });
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/jscocca/Repos/Crime\ Commute\ Safety\ Tool/.worktrees/c2-category-breakdown/frontend && npx vitest run src/components/AnalyzeTab.test.tsx`
Expected: FAIL — type error on `type_mix` / `category_breakdown` property, and `.mc-cat-row` not found.

- [ ] **Step 3: Update `frontend/src/types.ts`**

In `frontend/src/types.ts`, replace the `type_mix` field on `NeighborhoodPlace` (line 227) with `category_breakdown`:

Replace:

```ts
  type_mix: { label: string; count: number }[];
```

with:

```ts
  category_breakdown: { label: string; place_count: number; place_share: number; beat_share: number | null }[];
```

- [ ] **Step 4: Update `frontend/src/components/AnalyzeTab.tsx`**

**a) Replace the `type_mix` list inside `VerdictCard` with the `CategoryBreakdown` section.**

Replace the block (lines 278–283 in the original file):

```tsx
            {place.type_mix?.length ? (
              <ul className="mc-typemix">
                {place.type_mix.map((t) => <li key={t.label}>{t.label} · {t.count}</li>)}
              </ul>
            ) : null}
```

with:

```tsx
            <CategoryBreakdown rows={place.category_breakdown} />
```

**b) Add the `CategoryBreakdown` component** — insert it immediately before `function VerdictCard(`:

```tsx
function CategoryBreakdown({ rows }: { rows: { label: string; place_count: number; place_share: number; beat_share: number | null }[] }) {
  if (!rows.length) return null;
  return (
    <div className="mc-cat-breakdown">
      <span className="mc-cat-title">Incident types</span>
      {rows.map((row) => (
        <div key={row.label} className="mc-cat-row">
          <span className="mc-cat-label">{row.label}</span>
          <span className="mc-cat-shares">
            {Math.round(row.place_share * 100)}% here
            {row.beat_share !== null
              ? ` · ${Math.round(row.beat_share * 100)}% nearby`
              : null}
          </span>
          <span className="mc-cat-bar" aria-hidden="true">
            <span className="mc-cat-fill place" style={{ width: `${Math.round(row.place_share * 100)}%` }} />
            {row.beat_share !== null ? (
              <span className="mc-cat-fill beat" style={{ width: `${Math.round(row.beat_share * 100)}%` }} />
            ) : null}
          </span>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 5: Add `.mc-cat*` CSS**

In `frontend/src/styles/mapWorkspace.css`, append the following immediately after the last `.mc-temporal-note` line (line 470):

```css
/* Category breakdown — incident type mix, place-share vs beat-share, neutral palette */
.mc-cat-breakdown{margin-top:12px;padding-top:11px;border-top:1px solid var(--line);display:grid;gap:6px;}
.mc-cat-title{font-size:11.5px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:var(--faint);}
.mc-cat-row{display:grid;grid-template-columns:1fr auto;align-items:center;gap:4px 10px;font-size:11.5px;}
.mc-cat-label{color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.mc-cat-shares{color:var(--dim);white-space:nowrap;font-variant-numeric:tabular-nums;}
.mc-cat-bar{grid-column:1/-1;display:flex;gap:3px;height:4px;}
.mc-cat-fill{display:block;height:100%;border-radius:2px;}
.mc-cat-fill.place{background:var(--slate);}
.mc-cat-fill.beat{background:rgba(255,255,255,.18);}
```

- [ ] **Step 6: Run frontend tests to verify they pass**

Run: `cd /Users/jscocca/Repos/Crime\ Commute\ Safety\ Tool/.worktrees/c2-category-breakdown/frontend && npx vitest run src/components/AnalyzeTab.test.tsx`
Expected: PASS (all existing tests + the four new ones).

- [ ] **Step 7: Verify the build is clean**

Run: `cd /Users/jscocca/Repos/Crime\ Commute\ Safety\ Tool/.worktrees/c2-category-breakdown/frontend && npm run build`
Expected: build succeeds (tsc + vite, no type errors).

- [ ] **Step 8: Commit**

```bash
git -C /Users/jscocca/Repos/Crime\ Commute\ Safety\ Tool/.worktrees/c2-category-breakdown \
  add frontend/src/types.ts \
      frontend/src/components/AnalyzeTab.tsx \
      frontend/src/components/AnalyzeTab.test.tsx \
      frontend/src/styles/mapWorkspace.css
git -C /Users/jscocca/Repos/Crime\ Commute\ Safety\ Tool/.worktrees/c2-category-breakdown \
  commit -m "feat(frontend): category breakdown — place-share vs beat-share on the Analyze tab"
```

---

## Task 4: Roadmap tick

**Files:**
- Modify: `docs/ROADMAP.md`

- [ ] **Step 1: Tick the C2 checkbox**

In `docs/ROADMAP.md`, replace:

```markdown
- [ ] **C2 · Incident category breakdown** — surface the mix of incident types (not just counts) with the same baseline rigor.
```

with:

```markdown
- [x] **C2 · Incident category breakdown** — shipped: `_category_breakdown` replaces `type_mix`; each type shows place-share vs beat-share (null when no beat baseline); top-6 + "Other" fold; `CategoryBreakdown` component on the Analyze tab with `.mc-cat*` neutral styles. Spec/plan: `docs/superpowers/plans/2026-06-29-category-breakdown.md`.
```

- [ ] **Step 2: Commit**

```bash
git -C /Users/jscocca/Repos/Crime\ Commute\ Safety\ Tool/.worktrees/c2-category-breakdown \
  add docs/ROADMAP.md
git -C /Users/jscocca/Repos/Crime\ Commute\ Safety\ Tool/.worktrees/c2-category-breakdown \
  commit -m "docs(roadmap): mark Phase 4 C2 category-breakdown done"
```

---

## Task 5: Final gate

> This task has no code. Verify the full gate passes, review the UI manually, then open the PR.

- [ ] **Step 1: Run the full verification gate**

Run: `make -C /Users/jscocca/Repos/Crime\ Commute\ Safety\ Tool/.worktrees/c2-category-breakdown test-all`
Expected: `pytest` green (all tests), `ruff check .` clean, frontend `npm test` passes, `npm run build` succeeds.

If `ruff` flags an unused import (e.g. `_type_mix` was the only caller of something), fix and re-run before proceeding.

- [ ] **Step 2: Manual spot-check list**

Start the dev server in the worktree:
```bash
make -C /Users/jscocca/Repos/Crime\ Commute\ Safety\ Tool/.worktrees/c2-category-breakdown run
```
Open the dashboard, add a place downtown Seattle, run the Analyze tab, and verify:
- The "Incident types" section appears below the sparkline / monthly trend.
- Each row shows `{label} · {X}% here · {Y}% nearby` (or `{X}% here` alone when beat_share is null).
- An "Other" row appears when there are more than 6 types.
- A place with no incidents shows no breakdown section.
- No safety/ranking/significance language appears anywhere in the breakdown.

- [ ] **Step 3: Open the PR**

```bash
cd /Users/jscocca/Repos/Crime\ Commute\ Safety\ Tool/.worktrees/c2-category-breakdown && \
  gh pr create --base main \
    --title "feat(analysis): incident category breakdown — place-share vs beat-share (Phase 4, C2)" \
    --body "$(cat <<'EOF'
## Summary
- Adds `_category_breakdown` helper in `neighborhood_service.py`: buckets incidents by `offense_subcategory → offense_category → "Uncategorized"`, returns top-6 rows + aggregated "Other", each with `place_share` and `beat_share` (null when no beat baseline available).
- Replaces `type_mix` (raw count list) with `category_breakdown` at all three service attachment points; `_type_mix` removed.
- Frontend: `NeighborhoodPlace.type_mix` → `category_breakdown`; new `CategoryBreakdown` component on the Analyze tab with `.mc-cat*` neutral palette styles.
- Roadmap: Phase 4 C2 ticked.

## Test plan
- [ ] `make test-all` passes green (pytest + ruff + vitest + build).
- [ ] `tests/test_category_breakdown.py`: bucketing, top-N + Other, share math, null baseline, beat-only label excluded, deterministic order, empty list.
- [ ] `tests/test_neighborhood_service.py`: full-result branch has non-null beat_share; degraded branch has all-null beat_share; `type_mix` absent.
- [ ] `tests/test_dashboard_neighborhood_api.py`: `category_breakdown` present and well-formed; `type_mix` absent; first row label = "Theft" (fixture); invariant guard (no safety language).
- [ ] `AnalyzeTab.test.tsx`: place-share and beat-share rendered; null beat_share omits "nearby"; "Other" row renders; empty breakdown hides section.
- [ ] Manual spot-check in dev server: breakdown appears, no safety copy, "Other" row present when >6 types.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
