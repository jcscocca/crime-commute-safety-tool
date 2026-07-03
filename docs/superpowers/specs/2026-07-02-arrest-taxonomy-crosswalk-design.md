# Arrest↔crime taxonomy crosswalk (C4 follow-up) — design

**Date:** 2026-07-02 · **Roadmap item:** Phase 4 · C4 follow-up (arrest taxonomy crosswalk) ·
**Status:** approved design, pre-implementation.

## Problem

SPD **crime** rows carry an `offense_category` — one of `PROPERTY` / `PERSON` / `SOCIETY` (the
NIBRS "crime against" classification, taken from the source `crime_against_category` column).
SPD **arrest** rows carry no such column: `arrest_from_mapping` hardcodes `offense_category=None`
and `nibrs_group=None`, and stores the raw NIBRS offense text in `offense_subcategory` (e.g.
"All Other Larceny", "Drug/Narcotic Violations"). So on the **arrests layer** the category
filter is disabled and arrests can't be compared to crime by category.

This closes that gap: map an arrest's NIBRS offense description to the same
`offense_category` (and `nibrs_group`) the crime layer uses, so category filtering, breakdown,
and reported-vs-arrest category comparison work on the arrests layer.

## Key design inputs (verified against the code)

1. **Arrests carry only free-text `nibrs_description`** — no stable numeric NIBRS code
   (`seattle_socrata.py` `arrest_from_mapping`; `app/data/seed_arrests.csv`). So the crosswalk
   maps **from normalized text**, not a code.
2. **`offense_category` is populated at ingest**, stored on the indexed `CrimeIncident` column
   (`app/models.py`), not computed at query time. So the crosswalk runs **in the mapper**.
3. **Target values are exactly `PROPERTY` / `PERSON` / `SOCIETY`** (`AnalyzeTab.tsx` CATEGORIES;
   `seed_crime.csv`). `nibrs_group` is `"A"` / `"B"`.
4. **Ingest is insert-only** — `ingest_crime_incidents` skips rows that already exist
   (`crime_ingestion_service.py:36`), never updating. So a mapper change alone does **not**
   re-categorize already-stored arrests → a one-time backfill migration is required.
5. **No existing NIBRS→category mapping** anywhere in the repo — we author one.

## Scope

**In scope:**
1. A crosswalk module mapping NIBRS offense description → (`offense_category`, `nibrs_group`),
   covering the full NIBRS Group A + Group B offense list.
2. Wiring it into `arrest_from_mapping` (arrests get a category + group at ingest).
3. A one-time Alembic data migration backfilling existing `seattle_spd_arrests` rows.
4. Exposing the category filter/comparison on the **arrests** layer in the UI (`AnalyzeTab`,
   `CompareTab`) + updating the arrests note.
5. Tests + `docs/architecture/data-model.md`.

**Out of scope:**
- Arrest demographics (still not ingested).
- Any change to crime/911 category derivation.
- Per-category statistical significance on arrests (the breakdown stays descriptive).
- Mapping from a NIBRS code (arrests don't carry one).

## Approach

### 1 · Crosswalk module (`app/crime/nibrs_crosswalk.py`, new)

The single source of truth: a dict keyed on the **normalized** (casefold + strip) NIBRS offense
description, valued with `(offense_category, nibrs_group)`. Based on the FBI NIBRS "Crime
Against" classification (authoritative for Group A) plus a best-effort classification for the
arrest-only Group B offenses.

```python
NIBRS_CROSSWALK: dict[str, tuple[str, str]] = {
    # Group A — Crime Against Person
    "murder & nonnegligent manslaughter": ("PERSON", "A"),
    "aggravated assault": ("PERSON", "A"),
    "simple assault": ("PERSON", "A"),
    "intimidation": ("PERSON", "A"),
    "kidnapping/abduction": ("PERSON", "A"),
    # …(all Person sex offenses, human trafficking, etc.)…
    # Group A — Crime Against Property
    "burglary/breaking & entering": ("PROPERTY", "A"),
    "all other larceny": ("PROPERTY", "A"),
    "theft from motor vehicle": ("PROPERTY", "A"),
    "motor vehicle theft": ("PROPERTY", "A"),
    "destruction/damage/vandalism": ("PROPERTY", "A"),
    "robbery": ("PROPERTY", "A"),
    # …(arson, bribery, counterfeiting/forgery, embezzlement, extortion, fraud offenses,
    #    stolen property, shoplifting, pocket-picking, etc.)…
    # Group A — Crime Against Society
    "drug/narcotic violations": ("SOCIETY", "A"),
    "drug equipment violations": ("SOCIETY", "A"),
    "weapon law violations": ("SOCIETY", "A"),
    # …(gambling, pornography, prostitution, animal cruelty)…
    # Group B (arrest-only) — best-effort
    "driving under the influence": ("SOCIETY", "B"),
    "disorderly conduct": ("SOCIETY", "B"),
    "drunkenness": ("SOCIETY", "B"),
    "liquor law violations": ("SOCIETY", "B"),
    "trespass of real property": ("SOCIETY", "B"),
    "family offenses, nonviolent": ("PERSON", "B"),
    "bad checks": ("PROPERTY", "B"),
    "all other offenses": ("SOCIETY", "B"),
    # …(curfew/loitering, peeping tom)…
}


def classify_nibrs(description: str | None) -> tuple[str | None, str | None]:
    """Map a NIBRS offense description to (offense_category, nibrs_group). Returns (None, None)
    for a missing or unrecognized description — the arrest still ingests, just uncategorized."""
    if not description:
        return (None, None)
    return NIBRS_CROSSWALK.get(description.strip().casefold(), (None, None))
```

The implementation plan will enumerate the **complete** Group A (~52) + Group B (~10) table,
keyed on SPD's actual `nibrs_description` strings (the SPD arrest dataset uses standard NIBRS
offense descriptions). Group A "crime against" assignments are authoritative; Group B
assignments are best-effort and called out in code comments (most → `SOCIETY`, with
`Family Offenses, Nonviolent` → `PERSON` and `Bad Checks` → `PROPERTY`).

### 2 · Wire into `arrest_from_mapping` (`app/crime/seattle_socrata.py`)

Replace the hardcoded nulls:
```python
    offense_category=None,
    offense_subcategory=_first(row, "nibrs_description"),
    nibrs_group=None,
```
with:
```python
    _nibrs = _first(row, "nibrs_description")
    _category, _group = classify_nibrs(_nibrs)
    ...
    offense_category=_category,
    offense_subcategory=_nibrs,   # raw description still drives the "Charge" column
    nibrs_group=_group,
```
`offense_subcategory` is unchanged (still the raw description), so the arrests incident-detail
"Charge" column and the category breakdown's subcategory label are unchanged.

### 3 · Backfill migration (`app/alembic/versions/00NN_arrest_category_backfill.py`)

A data migration that applies the crosswalk to already-stored arrest rows. It **embeds its own
snapshot** of the description→(category, group) pairs (self-contained; does not import the app
module, per Alembic practice). For each pair:
```sql
UPDATE crime SET offense_category = :cat, nibrs_group = :grp
 WHERE source_dataset = 'seattle_spd_arrests'
   AND lower(offense_subcategory) = :desc
   AND offense_category IS NULL;
```
via parameterized `op.execute` (SQLite + Postgres safe). Properties: **scoped** to arrests,
**idempotent** (`offense_category IS NULL` guard), **non-destructive** (fills two nullable
columns only), **reversible** (`downgrade` sets `offense_category`/`nibrs_group` back to NULL
for `seattle_spd_arrests` rows). Follows the repo's dialect-branching migration conventions
(migrations run on SQLite in tests too).

### 4 · Expose on the arrests UI

Arrests now carry categories, so:
- **`AnalyzeTab.tsx`:** `showCategory` changes from `analysis.layer === "reported"` to
  `analysis.layer !== "calls"` — the category filter renders for reported **and** arrests
  (still hidden for calls, which have no category). The incident-detail generalization
  (`showCategory` / `subcategoryHeader`) already handles the rest; arrests keep the "Charge"
  header. Update the arrests enforcement note: keep the enforcement framing, drop "carry no
  offense category," and add a one-line caveat that arrest categories are a **best-effort NIBRS
  crosswalk**.
- **`CompareTab.tsx`:** the category-comparison gate (`analysis.layer === "reported"`) extends
  to arrests → `analysis.layer !== "calls"`.

### 5 · Category filter/breakdown (no new logic)

Category **filter** already does `where(offense_category == value)`; with arrests now
categorized, filtering the arrests layer by `PROPERTY` returns property arrests. Category
**breakdown** groups by `offense_subcategory → offense_category → "Uncategorized"`; arrests
still group by their NIBRS subcategory (unchanged primary label), and the populated category
improves the fallback and enables cross-layer category comparison. No breakdown/query code
changes.

## Data flow

Ingest: arrest row → `arrest_from_mapping` → `classify_nibrs(nibrs_description)` →
`offense_category`/`nibrs_group` stored. Backfill: migration fills those columns on existing
arrest rows. Query: existing category filter + breakdown consume the stored `offense_category`
identically for arrests and crime.

## Error handling / edge cases

- **Unmapped description:** `classify_nibrs` returns `(None, None)` — the arrest ingests
  uncategorized (same as today); a category filter excludes it (acceptable). The full table
  minimizes this; a coverage test asserts every seed-arrest description maps.
- **Normalization:** casefold + strip guards against case/whitespace variance; the migration's
  `lower(offense_subcategory)` mirrors the mapper's `casefold` (both lowercase-compare).
  (ASCII NIBRS text — `lower`/`casefold` agree.)
- **Backfill idempotency/scope/reversibility:** see §3.
- **Product invariant:** arrests remain framed as *enforcement activity* everywhere; the
  crosswalk only adds a category dimension. No safety/ranking language. The safety guard is
  untouched.

## Testing

- `tests/test_nibrs_crosswalk.py` (new): known descriptions → correct (category, group);
  unmapped/empty/None → (None, None); normalization (mixed case / surrounding whitespace);
  a coverage test that every distinct `nibrs_description` in `seed_arrests.csv` maps to a
  non-None category.
- `tests/test_arrest_mapping.py`: update to assert a mapped `offense_category`/`nibrs_group`
  (e.g. "All Other Larceny" → `PROPERTY`/`A`) instead of the old `None`.
- Backfill migration test: seed arrest rows with `offense_category IS NULL`, run the migration
  (upgrade), assert categories populated for mapped descriptions and untouched for crime/911;
  run twice → idempotent; `downgrade` → back to NULL for arrests only.
- Frontend: `AnalyzeTab.test.tsx` — the category filter now renders on the arrests layer;
  the arrests note no longer claims "no offense category." `CompareTab` gate extends to arrests.
- Existing category-filter / breakdown / disjoint-layer tests stay green.

## Verification gate

`make test-all` + `make migrate` (alembic upgrade head) from the worktree.

## Roadmap tick

On merge, mark the arrest↔crime taxonomy crosswalk **shipped** in `docs/ROADMAP.md`'s C4 line
(arrests now carry a best-effort NIBRS-crosswalked `offense_category`/`nibrs_group`; category
filter/comparison available on the arrests layer). This closes the last queued C4 follow-up;
arrest demographics remain the only deferred arrests item.
