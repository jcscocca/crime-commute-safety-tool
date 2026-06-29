# Analyze Tab Clarity Redesign — Design (Phase 2, tab 1)

> Status: design approved via brainstorming 2026-06-28. First of the Phase 2 tab redesigns
> (the others — Compare, Places, Routes, Export — are separate cycles). **Frontend-only**; the
> backend, the assistant agent, and the data contract are unchanged. Direction "A" (headline +
> comparison bars + progressive statistics) chosen over a glanceable-scale alternative.

## Objective

Make the Analyze tab **lead with the plain answer** — "is this place unusual for its surrounding
area, and how sure are we?" — in plain language, with the heavy statistics available but
**progressive, not overwhelming**. Today the tab is a wall: a verdict card whose interpretation is
buried in an "Analytical detail" expander, then pairwise rows, then a raw incident table.

## Current Context

`frontend/src/components/AnalyzeTab.tsx` renders, in order: the settings querybar (date range,
radius chips, category chips, "Run analysis"); a `VerdictBlock` per place; a `PairwiseSection`; and
`IncidentDetailsTable`/`IncidentDetailsCards`. The neighborhood result's `places[]` already carry
everything we need: `place_label`, `decision`, `baseline_available`, `rate_ratio`, `ci_lower`,
`ci_upper`, `adjusted_p_value`, `exact_p_value`, `place_rate`, `beat_rate`, `beat`,
`place_incident_count`, `monthly_counts`, `type_mix`, `method`, `overdispersion_status`,
`minimum_data_status`, `nearest_incident_m`. `decision` ∈ `above_clear` | `below_clear` |
`not_clear` | `insufficient_data` | `model_warning` | `baseline_unavailable`.

The assistant's deterministic summary (`app/assistant/summaries.py`) reads the same `decision` /
`rate_ratio` fields, so chat and pane stay consistent with no backend change.

## Approved Decisions

| Decision | Choice |
|---|---|
| Direction | **A** — plain headline + significance chip + comparison bars + progressive stats |
| Scope of redesign | The **whole tab's hierarchy** (lead with verdict; tuck the rest), not just the card |
| Incident table | Collapsed behind a **"See the N incidents ▸"** reveal |
| Pairwise | Kept, but clearly **secondary**, below the verdict cards, only when ≥2 places |
| Settings querybar | **Unchanged** |
| Layer | **Frontend-only** — no backend/agent/data change |
| Verdict coloring | **Neutral** (chip encodes statistical *clarity*, not good/bad) — see Invariant |

## Components

### 1. `decisionHeadline(place)` — pure mapping (new)

A pure function (e.g. `frontend/src/lib/verdictCopy.ts`) mapping a neighborhood place to plain
copy: `{ headline: string; chip: { label: string; tone: "clear" | "muted" } }`.

| `decision` | headline | chip |
|---|---|---|
| `above_clear` | "{label} has more reported incidents than its surrounding beat." | "✓ statistically clear" / clear |
| `below_clear` | "{label} has fewer reported incidents than its surrounding beat." | "✓ statistically clear" / clear |
| `not_clear` | "{label} is about the same as its surrounding beat." | "~ not statistically clear" / muted |
| `insufficient_data` / `model_warning` | "Not enough data to compare {label} to its beat." | "too little data" / muted |
| `baseline_unavailable` | "No neighborhood baseline available for {label}." | "no baseline" / muted |

### 2. `VerdictCard` component (new)

Replaces `VerdictBlock`. Given one place, renders:
- the **significance chip** (from `decisionHeadline`),
- the **headline**,
- a **context line**: "{place_incident_count} reported incidents within {radius} m · {date window}",
- **comparison bars** (two rows: "surrounding beat" at `1.0×`, and the place at `rate_ratio`×) —
  only when `baseline_available` and `rate_ratio` is non-null. Each bar's width as a percentage of
  its track is `min(value, CAP) / CAP × 100` with `CAP = 3.0` — so the beat reference (`1.0×`)
  is always `33%`, a `1.4×` place is `47%`, a `0.4×` (below) place is `13%` (visibly shorter than
  the beat), and anything `≥ 3.0×` renders full-width with its true "N.N×" label still shown,
- the **monthly sparkline** (`monthly_counts`) when present,
- a **`<details>` "How we know"** reveal containing today's analytical fields: 95% CI
  (`ci_lower`–`ci_upper`), adjusted + exact p-value, dispersion (`overdispersion_status`),
  `method`, adequacy (`minimum_data_status`), `nearest_incident_m`, and `type_mix`.

When `baseline_available` is false: no bars, no "How we know" stats — just the headline + the
context line (count only).

### 3. `AnalyzeTab` reorganization

Render order becomes: settings querybar (unchanged) → one `VerdictCard` per `neighborhood.places`
→ a secondary `PairwiseSection` (only when ≥2 places) → a collapsed
`<details>`("See the {total} incidents") wrapping the existing incident table/cards →
`MethodsAppendix`. The loading skeleton and the `panelWidthPx`-based table/cards switch are kept.

## Invariant (must hold)

Waypoint reports reported-incident context, not safety. The redesign **must not** imply
safe/unsafe: the headline states a neutral fact ("more/fewer/about the same reported incidents"),
and the chip encodes **statistical clarity** (clear vs not), not good/bad — so the redesign uses a
**neutral** chip/bar palette rather than today's red-for-above / green-for-below (`tone-hot` /
`tone-ok`), which nudges toward a danger judgment. This is a deliberate, invariant-aligned change.

## Error / Edge Cases

- `baseline_available` false, or `rate_ratio` null → no comparison bars; headline + count only.
- `monthly_counts` empty/absent → no sparkline.
- `ci_lower`/`ci_upper` null → "How we know" omits the CI line.
- Multiple places → a vertical stack of `VerdictCard`s; pairwise renders below.
- Zero places (no analysis yet) → the existing empty/skeleton states are unchanged.

## Testing

- `decisionHeadline`: every `decision` value → the exact headline + chip label/tone above.
- `VerdictCard`: renders chip + headline + context + bars (above_clear); a `below_clear` place's
  bar is shorter than the beat reference; `baseline_unavailable` shows no bars and the
  no-baseline headline; "How we know" is collapsed by default and contains the CI + p-value.
- `AnalyzeTab`: one card per place; the incident table is **not** visible until the reveal is
  opened; pairwise renders only with ≥2 places; settings querybar still drives `onChange`.
- Gate: frontend `npm test` + `npm run build` (backend untouched).

## Non-Goals

- Any backend, assistant, or data-contract change (none needed).
- The other tabs (Compare/Places/Routes/Export) — separate redesign cycles.
- New statistics, new charts beyond the existing sparkline, or a map.
- Changing the settings querybar or the analysis flow.
