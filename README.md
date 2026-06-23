# Mobility Context Analyzer

Backend-first MVP for a privacy-first mobility context tool. The app accepts personal
location-history uploads, turns them into stop visits and recurring place clusters, compares
those recurring areas with reported Seattle SPD crime incidents, and exports a Tableau-ready
CSV that avoids raw GPS traces.

## What It Does

- Imports Google Maps/Timeline JSON and CSV point files.
- Imports privacy-light recurring-place CSV files.
- Imports public commute scenario CSV files using generalized Seattle area centroids.
- Includes minimal GeoJSON and GPX point adapters so those formats have clean seams.
- Normalizes uploads into stop visits and recurring place clusters.
- Marks home-like and work-like clusters for privacy suppression.
- Loads a local Seattle crime fixture for offline tests and demo work.
- Computes reported SPD incident counts within selected radii and date ranges.
- Exports privacy-safe Tableau CSV rows using generalized display coordinates.

## What It Does Not Do

- It does not score safety or label places as safe or unsafe.
- It does not claim a user was present when an incident occurred.
- It does not expose raw GPS observations in Tableau exports.
- It does not implement real authentication, encryption at rest, or tenant isolation yet.
- It does not run live Socrata ingestion in unit tests.

## Privacy Posture

Raw uploads are temporary input artifacts. The canonical product objects are stop visits,
recurring place clusters, and context summaries. Demo identity comes from the
`X-Demo-User-Id` header, or `demo_user` when omitted, and is hashed server-side.

In `tableau_safe` mode, home-like, work-like, health-like, religious-like, and explicitly
suppressed clusters are excluded from the Tableau export by default. Exported coordinates use
`display_latitude` and `display_longitude`; if those are missing, the exporter rounds exact
centroids to a coarse grid.

TODO: add production authentication, encryption at rest, per-user tenant isolation, upload
retention controls, and explicit user-facing consent screens.

## Local Setup

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
cp .env.example .env
```

Run tests:

```bash
make test
```

Run the API with SQLite defaults:

```bash
make run
```

Run with Postgres/PostGIS:

```bash
docker compose up --build
```

Apply migrations manually:

```bash
make migrate
```

## Demo Flow

Start the API, then upload the recurring Google fixture:

```bash
curl -F "file=@tests/fixtures/google_recurring.json" \
  -H "X-Demo-User-Id: demo@example.com" \
  http://127.0.0.1:8000/imports
```

Normalize the returned import id:

```bash
curl -X POST -H "X-Demo-User-Id: demo@example.com" \
  http://127.0.0.1:8000/imports/<import_id>/normalize
```

Load sample crime data and summarize:

```bash
curl -X POST http://127.0.0.1:8000/crime/ingest/sample
curl -X POST -H "Content-Type: application/json" \
  -H "X-Demo-User-Id: demo@example.com" \
  -d '{"analysis_start_date":"2024-01-01","analysis_end_date":"2024-01-31","radii_m":[250]}' \
  http://127.0.0.1:8000/crime/summarize
```

Export Tableau CSV:

```bash
curl -H "X-Demo-User-Id: demo@example.com" \
  http://127.0.0.1:8000/exports/tableau/place-summary.csv
```

## Three Input Modes

The guided dashboard flow supports three input modes:

1. **Personal timeline upload** for Google Timeline JSON, raw point CSV, GeoJSON, or GPX.
   This is the highest-detail mode and should be presented with the strongest privacy language.
2. **Generalized recurring places CSV** for users who want dashboard value without uploading
   raw movement history.
3. **Public commute scenario CSV** for neighborhood or transit-oriented scenarios that use
   generalized Seattle area centroids instead of personal location data.

Mode metadata is available from:

```text
GET /input-modes
```

Dashboard-ready summary data is available from:

```text
GET /dashboard/summary
```

## Supported Upload Formats

- Google Semantic Location History JSON with `timelineObjects`.
- Google records-style JSON with `locations`, `latitudeE7`, and `longitudeE7`.
- CSV with `timestamp`, `latitude`, `longitude`, and optional `accuracy_m`,
  `activity_type`, and `source`.
- Recurring places CSV:

```csv
display_label,latitude,longitude,visit_count,total_dwell_minutes,median_dwell_minutes,typical_days,typical_hours,sensitivity_class
Downtown transfer stop,47.609,-122.333,12,360,30,weekday,8-9,normal
Library area,47.621,-122.321,6,420,70,weekend,afternoon,normal
```

- Public commute scenario CSV:

```csv
origin_area,destination_area,mode,usual_departure_time,frequency_per_week
Capitol Hill,Downtown Seattle,transit,08:00,4
```

- Minimal GeoJSON Point/LineString support.
- Minimal GPX track point support.

## Tableau Export

The recurring-place export is available at:

```text
GET /exports/tableau/place-summary.csv
```

It includes recurring-place fields, generalized coordinates, selected analysis range,
crime grouping fields, incident counts, nearest incident distance, incidents per visit, and
incidents per hour of dwell. Product language should describe rows as:

> Reported SPD incidents within 500m of this recurring location during the selected date range.

## Route Alternatives

Route comparison is available in Stage 1 with the current mock routing provider:

```text
POST /routes/alternatives
GET /routes/requests/{request_id}/comparison
```

`POST /routes/alternatives` accepts generalized Seattle origin and destination labels,
route mode, optional departure details, and optional `analysis_start_date`,
`analysis_end_date`, and `radii_m` values. When analysis dates are provided, the response
and persisted comparison include reported incident context summaries near route points
including segment starts and ends.

Tableau route exports are available at:

```text
GET /exports/tableau/route-alternatives.csv
GET /exports/tableau/route-segments.csv
GET /exports/tableau/route-context.csv
```

`route-segments.csv` includes provider/mock route point labels and coordinates for segment
starts and ends; it does not include raw GPS observations.

OpenTripPlanner is the planned provider for live route alternatives. Until that provider is
implemented, the mock provider supplies deterministic Stage 1 route alternatives for local
development, tests, and Tableau dashboard prototyping.

Product language for route dashboards should describe these rows as reported route-point
incident context, not as safe or unsafe route claims.

## Data Caveats

Seattle SPD open data contains reported incidents. Reported crime data can be incomplete,
delayed, corrected, or geographically generalized. Personal location history can also be
incomplete, inaccurate, or biased by device behavior. This tool provides context summaries,
not safety predictions.

The default Socrata dataset id is `tazs-3rd5`, the City of Seattle's "SPD Crime Data:
2008-Present" dataset.

## References And Licensing

This implementation is original. Related projects were used as architecture references only,
including Google Timeline parsing tools, Reitti, GeoPulse, Dawarich, and Seattle crime data
pipelines. No AGPL/GPL/BSL source code was copied. If future MIT-licensed code is reused,
preserve attribution and license notices.
