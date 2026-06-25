# Incident Detail Analysis Design

## Summary

Waypoint should stop presenting `incidents_per_visit` as a meaningful user-facing metric.
Weekly visits describe routine relevance, but they do not provide time overlap with reported
incidents. The Analyze tab should instead show clear place-context metrics and spell out the
underlying reported incidents in a table.

## Goals

- Keep the primary analysis honest: reported incident counts, nearest distance, and incident mix.
- Treat weekly visits as place metadata, not as a denominator or exposure proxy.
- Show the incident rows behind a place's count in the Analyze tab.
- Use the same selected places, date range, radius, and category filter for counts and details.
- Preserve existing safety caveats: reported incidents are not personal risk predictions.

## Non-Goals

- Do not infer personal exposure from visit frequency.
- Do not claim that a user was present during an incident.
- Do not build time-window overlap until typical days/hours or actual dwell windows are first-class inputs.
- Do not add incident markers to the public map in this pass.
- Do not remove stored `visit_count`; it remains useful for sorting and routine context.

## Product Behavior

The Analyze tab remains the place where users run selected-place analysis. After analysis,
it should show:

- Total reported incidents for each selected place at the active radius.
- Incident mix by category and subcategory.
- Nearest reported incident distance.
- A compact incident table titled `Reported incidents near selected places`.

The incident table should include:

- Place.
- Date/time, using offense start when available and report time as fallback.
- Category.
- Subcategory or offense label.
- Distance from the selected place.
- Block/address when available.
- Report number, external incident id, or internal id.

Default sorting should group by place and then sort by nearest incident. If an incident falls
within the active radius of multiple selected places, it should appear once for each matching
place because the table is explaining each place's count.

The table should cap initial output to 100 rows and clearly state when the response is capped,
for example `Showing nearest 100 matching reported incidents`.

## Metrics

Remove `incidents_per_visit` from primary UI copy and comparison cards. The backend can keep
the column for legacy exports, but new public copy should avoid it.

Primary metrics:

- `reported_incident_count`: count within selected radius/date/filter.
- `nearest_incident_m`: closest matching reported incident.
- `incident_mix`: grouped category/subcategory counts.

Visits should appear only as metadata such as `5 visits/week`.

## Backend Design

Add a dashboard incident-details endpoint:

```text
POST /dashboard/incidents
```

Use the same request shape as `/dashboard/analyze`:

```json
{
  "place_ids": ["..."],
  "analysis_start_date": "2026-01-01",
  "analysis_end_date": "2026-06-24",
  "radii_m": [250],
  "offense_category": "PROPERTY",
  "offense_subcategory": null,
  "nibrs_group": null,
  "limit": 100
}
```

The first implementation should support one active radius, matching the current Analyze UI.
If more than one radius is sent, use the first radius and ignore the rest, consistent with
the UI's single active radius.

Response shape:

```json
{
  "incidents": [
    {
      "place_id": "place-1",
      "place_label": "Library",
      "incident_id": "crime-1",
      "external_incident_id": "2026-...",
      "report_number": "2026-...",
      "occurred_at": "2026-01-03T10:00:00Z",
      "reported_at": "2026-01-04T12:00:00Z",
      "offense_category": "PROPERTY",
      "offense_subcategory": "THEFT",
      "nibrs_group": "A",
      "block_address": "100 BLOCK EXAMPLE ST",
      "distance_m": 42.3
    }
  ],
  "returned_count": 1,
  "total_count": 1,
  "limit": 100,
  "radius_m": 250
}
```

Implementation should reuse the existing selected-cluster and filtered-incident logic where
possible. It should compute exact distance with `haversine_m`, filter by active radius, then
sort by place label and distance.

## Frontend Design

Add an API client method for `/dashboard/incidents` and types for incident-detail rows.
`MapWorkspace` should request incident details after a successful Analyze run and store them
in local state. Changing selected places, radius, date range, category, or deleting a place
should invalidate the incident details in the same way comparison results are invalidated.

`AnalyzeTab` should receive incident details and render a table below the findings summary.
The table should use existing panel/list styling and remain compact inside the bottom sheet.

When no analysis has run, show only the existing prompt. When analysis has run but there are
no matching incidents, show `No matching reported incidents for the selected filters.`

## Testing

Backend tests should cover:

- The incident detail endpoint returns rows for selected places inside the radius.
- Distance is computed against display coordinates.
- The endpoint respects date, radius, place id, and offense category filters.
- The endpoint caps rows at the requested/default limit and reports `total_count`.

Frontend tests should cover:

- `AnalyzeTab` renders incident details in a table.
- Empty detail results show the empty-state message.
- `MapWorkspace` fetches incident details after Analyze succeeds.
- Changing analysis controls or selected places clears stale incident details.

## Open Questions Resolved

- Incident rows should be shown in Analyze, not only Compare.
- Visits remain visible as routine metadata but are not used as a public metric.
- Incident details should be fetched from a new endpoint rather than embedded into stored
  summary rows.
