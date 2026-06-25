Codex Build Prompt: Waypoint MVP
Google Maps/Timeline upload -> normalized common locations -> Seattle crime comparison -> Tableau-ready export

How to use this document
Copy the full prompt below into Codex at the start of a new build. It is designed for a backend-first MVP. It intentionally makes Google Maps/Timeline the first supported source while leaving clean adapter seams for CSV, GPX, GeoJSON, OwnTracks, GPSLogger, and Overland later.

Single-shot Codex prompt

You are Codex working in a software repository. Build the first backend-first MVP for Waypoint, a privacy-first reported-incident analysis tool.

Product objective
Build an application that lets a user upload personal location-history data, initially Google Maps/Timeline or Google Takeout-style data, normalizes it into derived mobility objects, compares recurring places against Seattle SPD crime data from Seattle's open-data portal, and exports privacy-safe Tableau-ready outputs.

The key product principle is: do not make raw GPS points the main product object. Raw uploaded data is only a temporary input artifact. The canonical product objects are stop visits, recurring place clusters, optional trip/route patterns, and crime/context summaries.

Start by inspecting the existing repository. If it is empty, scaffold the project. If it already has a framework or package manager, integrate with it instead of replacing it. Do not delete user work. Make reasonable assumptions and proceed without asking clarification questions.

Preferred stack
Use this stack unless the repository clearly already uses another one:
- Python 3.11+
- FastAPI for API endpoints
- Pydantic v2 for request/response and parser models
- SQLAlchemy 2.x + Alembic for persistence
- PostgreSQL/PostGIS through Docker Compose for production-like local development
- Pure-Python geospatial utilities for unit tests so tests do not require PostGIS
- pytest for tests
- pandas only where it meaningfully simplifies CSV/export work
- optional: shapely/geopandas only if already available or easy to add; do not let them block the MVP

Core repo structure
Create or adapt toward this structure:

app/
  main.py
  config.py
  db.py
  models.py
  schemas.py
  api/
    routes_health.py
    routes_imports.py
    routes_places.py
    routes_exports.py
  parsers/
    base.py
    google_timeline.py
    csv_points.py
    geojson_points.py
    gpx_points.py
  normalization/
    geo.py
    stops.py
    clusters.py
    sensitive_locations.py
  crime/
    seattle_socrata.py
    summaries.py
  exports/
    tableau.py
  services/
    import_service.py
    normalization_service.py
    crime_service.py
alembic/
tests/
  fixtures/
  test_google_timeline_parser.py
  test_csv_parser.py
  test_stop_detection.py
  test_place_clustering.py
  test_crime_summary.py
  test_tableau_export.py
pyproject.toml
docker-compose.yml
README.md
.env.example

Functional requirements

1. Imports and source adapters
Implement a source-adapter interface that converts source-specific files into canonical observations and source-derived events.

Support at least:
- Google Timeline / Google Takeout JSON MVP parser
- CSV fallback parser with timestamp, latitude, longitude and optional accuracy_m, activity_type, source fields

Create stubs or minimal support for:
- GeoJSON Point/LineString uploads
- GPX track uploads

The Google parser should be tolerant and schema-aware. It should attempt to handle:
- Semantic Location History with timelineObjects containing placeVisit and activitySegment
- records-style exports with locations arrays and latitudeE7/longitudeE7
- newer on-device Timeline JSON variants when possible, using robust key detection rather than assuming one exact shape

For Google coordinates, convert latitudeE7/longitudeE7 into decimal degrees. Preserve source metadata such as source_type, source_record_type, source_record_hash, observed_at, start_time, end_time, accuracy_m, activity_type, confidence_score, and selected raw fields needed for debugging. Do not keep full raw payloads by default.

2. Data model
Implement SQLAlchemy models and Alembic migrations for the MVP tables below. Include numeric latitude/longitude fields even if geometry columns are also available; this keeps tests and exports simple.

ImportBatch
- id UUID primary key
- user_id_hash text
- source_type text
- original_filename text
- file_hash_sha256 text
- parser_version text
- detected_schema text nullable
- uploaded_at timestamptz
- min_time_utc timestamptz nullable
- max_time_utc timestamptz nullable
- status text
- raw_retention_until timestamptz nullable
- privacy_mode text default tableau_safe
- error_message text nullable

StagingLocationObservation
- id UUID primary key
- import_id FK
- user_id_hash text
- source_record_type text
- source_record_hash text nullable
- observed_at_utc timestamptz nullable
- start_time_utc timestamptz nullable
- end_time_utc timestamptz nullable
- latitude double precision nullable
- longitude double precision nullable
- accuracy_m double precision nullable
- activity_type text nullable
- confidence_score double precision nullable
- created_at timestamptz

StopVisit
- id UUID primary key
- import_id FK
- user_id_hash text
- place_cluster_id UUID nullable
- start_time_utc timestamptz
- end_time_utc timestamptz
- duration_minutes numeric
- local_date date nullable
- local_day_of_week smallint nullable
- local_hour_start smallint nullable
- centroid_latitude double precision
- centroid_longitude double precision
- radius_m double precision nullable
- accuracy_median_m double precision nullable
- source_basis text
- point_count_used integer nullable
- confidence_score double precision nullable
- created_at timestamptz

PlaceCluster
- id UUID primary key
- user_id_hash text
- cluster_version text
- cluster_method text
- centroid_latitude double precision
- centroid_longitude double precision
- display_latitude double precision nullable
- display_longitude double precision nullable
- cluster_radius_m double precision nullable
- visit_count integer
- total_dwell_minutes numeric nullable
- median_dwell_minutes numeric nullable
- first_seen_utc timestamptz nullable
- last_seen_utc timestamptz nullable
- dominant_days text nullable
- dominant_hours text nullable
- inferred_place_type text default unknown
- sensitivity_class text default normal
- display_label text nullable
- label_source text nullable
- created_at timestamptz
- updated_at timestamptz

CrimeIncident
- id UUID primary key
- external_incident_id text unique nullable
- report_number text nullable
- offense_id text nullable
- offense_start_utc timestamptz nullable
- offense_end_utc timestamptz nullable
- report_utc timestamptz nullable
- offense_category text nullable
- offense_subcategory text nullable
- nibrs_group text nullable
- precinct text nullable
- sector text nullable
- beat text nullable
- mcpp text nullable
- block_address text nullable
- latitude double precision nullable
- longitude double precision nullable
- source_dataset text default seattle_spd_crime
- snapshot_at timestamptz

PlaceCrimeSummary
- id UUID primary key
- user_id_hash text
- place_cluster_id FK
- radius_m integer
- analysis_start_date date
- analysis_end_date date
- offense_category text nullable
- offense_subcategory text nullable
- nibrs_group text nullable
- incident_count integer
- nearest_incident_m numeric nullable
- incidents_per_visit numeric nullable
- incidents_per_hour_dwell numeric nullable
- created_at timestamptz

Optional but useful if time allows:
TripEvent and RoutePattern tables with nullable geometry/representative fields. Do not block the MVP on route extraction.

3. Privacy and retention requirements
The default privacy mode is tableau_safe.
- Do not expose raw GPS observations in exports.
- Raw upload files should be stored only in local dev storage and deleted after successful normalization unless a config flag says otherwise.
- Display coordinates for sensitive places must be generalized or suppressed.
- Home-like/work-like inference should be used mainly for privacy protection, not as a user-facing claim.
- Exclude sensitive clusters from Tableau exports by default.
- Add clear TODOs for real auth, encryption at rest, and per-user tenant isolation.

For MVP user identity, accept an X-Demo-User-Id header or default to demo_user, then hash it server-side. Do not implement full authentication yet.

4. Normalization logic
Implement stop-first normalization.

Stop extraction rules:
- If Google placeVisit records provide start/end and lat/lon, convert them directly to StopVisit rows.
- For raw point streams, detect stops when the user remains within approximately 75 meters for at least 10 minutes.
- Deduplicate near-identical source records by source_record_hash or timestamp+coordinate.
- Filter invalid observations: missing coordinates, impossible latitude/longitude, duplicate timestamps, and obviously impossible movement speeds when consecutive points are available.

Default thresholds should be configurable:
- minimum_stop_duration_minutes = 10
- stop_radius_m = 75
- cluster_radius_m = 100
- minimum_cluster_visits = 3
- minimum_cluster_total_dwell_minutes = 60
- crime_radii_m = [250, 500, 1000]

Place clustering rules:
- Cluster StopVisit centroids into recurring PlaceCluster objects.
- Use a simple, well-tested clustering implementation suitable for MVP. A pure-Python DBSCAN-like implementation using haversine distance is acceptable. Keep it behind a function that can later be replaced by PostGIS ST_ClusterDBSCAN or scikit-learn.
- A cluster should require at least minimum_cluster_visits or minimum_cluster_total_dwell_minutes.
- Compute centroid, cluster radius, visit count, total dwell, median dwell, first_seen, last_seen, dominant days, and dominant hours.
- Update StopVisit.place_cluster_id after clustering.

Sensitive-location inference:
- home_like: recurring cluster with significant overnight dwell, e.g. 8pm-6am, across multiple days.
- work_like: recurring weekday daytime dwell, e.g. Mon-Fri 9am-5pm.
- Mark these as sensitivity_class home_candidate or work_candidate.
- For tableau_safe exports, suppress exact coordinates and exclude these clusters by default.

5. Seattle crime-data ingestion
Implement a Seattle Socrata client with:
- configurable base URL and dataset ID, default dataset ID tazs-3rd5
- optional app token via env var SOCRATA_APP_TOKEN
- pagination support with limit/offset
- ability to ingest from local CSV fixture for tests and offline development
- flexible field mapping because Socrata field names can change or contain nulls

Expected useful fields include report_number, offense_id, offense_start_datetime, offense_end_datetime, report_datetime, crime_against_category, offense_parent_group, offense, precinct, sector, beat, mcpp, 100_block_address, longitude, latitude. Map these into CrimeIncident.

Tests must not depend on live Socrata network access. Include a small sample fixture.

6. Crime comparison summaries
Implement place-level crime summaries for recurring places.

For each PlaceCluster and configured radius:
- Count CrimeIncident rows within radius meters of the cluster centroid or display-safe analysis coordinate.
- Group summaries by offense_category, offense_subcategory, and nibrs_group where available.
- Compute nearest incident distance.
- Compute incidents_per_visit and incidents_per_hour_dwell when denominator is available.
- Support analysis_start_date and analysis_end_date filters.

For distance calculations in unit tests, use a haversine function. In the DB/PostGIS path, make the code easy to replace with ST_DWithin later.

Do not claim exact simultaneity between user presence and a crime. Product language and README should frame outputs as reported incidents within a distance and selected date range.

7. API endpoints
Implement these endpoints:
- GET /health
- POST /imports: upload a file, detect parser, create ImportBatch, parse to staging observations and/or source-derived stops
- GET /imports/{import_id}: status and summary counts
- POST /imports/{import_id}/normalize: run stop extraction and place clustering
- GET /places: list non-sensitive place clusters for the demo user, with optional include_sensitive=false default
- POST /crime/ingest/sample: load sample crime fixture for development/tests
- POST /crime/summarize: compute PlaceCrimeSummary rows for selected date range and radii
- GET /exports/tableau/place-summary.csv: export privacy-safe place summary CSV

Add a CLI or Makefile targets if convenient:
- make test
- make run
- make demo
- make migrate

8. Tableau export
Create a CSV export suitable for Tableau with columns:
- user_id_hash
- place_cluster_id
- display_label
- latitude
- longitude
- cluster_radius_m
- visit_count
- total_dwell_minutes
- median_dwell_minutes
- inferred_place_type
- sensitivity_class, only if safe; otherwise omit or generalize
- radius_m
- analysis_start_date
- analysis_end_date
- offense_category
- offense_subcategory
- nibrs_group
- incident_count
- nearest_incident_m
- incidents_per_visit
- incidents_per_hour_dwell

For tableau_safe mode:
- exclude home_candidate, work_candidate, health_candidate, religious_candidate, and suppress_from_public_export clusters by default
- use display_latitude/display_longitude, not exact centroids
- if display coordinates are missing, generate them by snapping exact centroid to a coarse grid or rounding to no more than 3 decimal places

9. Tests and fixtures
Create realistic but tiny fixtures:
- Google semantic JSON with at least two placeVisit objects and one activitySegment
- Google records-style JSON with locations latitudeE7/longitudeE7/timestamp fields
- CSV points that create one stop through stay detection
- sample Seattle crime CSV with a few incidents near and far from a cluster

Tests should cover:
- latE7/lonE7 conversion
- Google semantic placeVisit parsing
- Google records parsing
- CSV parsing
- stop detection from raw points
- place clustering threshold behavior
- sensitive-location inference at least for home_like
- crime radius count and nearest distance
- Tableau CSV export excludes sensitive clusters by default

10. README requirements
Write a README that includes:
- What the app does
- What it does not do
- Privacy posture
- Local setup with Docker Compose
- How to run tests
- How to run the demo flow
- Supported upload formats
- How Tableau export works
- Data caveats: reported crime data, generalized crime locations, incomplete/inaccurate location history, no safety scoring
- Licensing note: the implementation is original; related repos were used as references only

11. Reference repositories to examine, if web access is available
Use these as reference points, not as code to copy blindly:
- supsi-dacd-isaac/google-maps-timeline: inspect Google Timeline loading, location normalization, clustering, and commute extraction ideas.
- dedicatedcode/reitti: inspect visit/trip/significant-place architecture and PostGIS-oriented modeling.
- tess1o/geopulse: inspect adapter strategy and multi-source ingestion ideas.
- Freika/dawarich: inspect import UX, background jobs, schema pitfalls, and issue tracker edge cases.
- DovarFalcone/google-takeout-location-parser: inspect MIT-licensed parser behavior and Google Takeout fixture shapes.
- kurupted/google-maps-timeline-viewer: inspect client-side preview and old/new Timeline format handling.
- dwimbush/Seattle_Crime_Data_Pipeline: inspect Seattle crime ETL/dashboard ideas.

License guardrail:
Do not copy code from AGPL, GPL, or BSL repositories unless the repository owner has explicitly chosen compatible licensing for this project. It is fine to learn architecture and algorithms and then implement original code. If any MIT-licensed code is reused, preserve attribution and license notices. Prefer original implementation.

12. Engineering quality requirements
- Use type hints.
- Keep parser code defensive and well-tested.
- Keep normalization idempotent: running normalization twice should not duplicate StopVisit, PlaceCluster, or summary records for the same import unless explicitly requested.
- Add unique constraints or deletion/rebuild logic where needed.
- Separate pure logic from API handlers so it is testable.
- No network calls in normal unit tests.
- Use environment variables for secrets and config.
- Do not print raw user coordinates unnecessarily in logs.
- Include structured error messages for unsupported file formats.

13. Definition of done for this first build
The build is done when:
- docker compose up starts the API and Postgres/PostGIS services
- alembic migrations run successfully
- pytest passes locally without live network access
- sample Google fixture can be uploaded through API or test client
- normalization produces StopVisit and PlaceCluster rows
- sample crime fixture can be loaded
- crime summarization produces PlaceCrimeSummary rows
- Tableau place-summary CSV exports successfully
- README explains setup, demo, privacy posture, and limitations
- final response summarizes files changed, commands run, tests passing/failing, known gaps, and next recommended build step

Implementation sequence
Work in this order:
1. Scaffold project, config, DB, models, migrations, tests framework.
2. Implement pure geo utilities and parser interface.
3. Implement Google parser and CSV parser with fixtures.
4. Implement stop detection and place clustering with tests.
5. Implement sensitive-location inference and display-coordinate generalization.
6. Implement sample crime ingestion and summary calculations.
7. Implement API endpoints.
8. Implement Tableau CSV export.
9. Write README and .env.example.
10. Run tests and fix failures.

Important product wording
Use language like:
- "Reported SPD incidents within 500m of this recurring location during the selected date range."
- "Recurring location" or "recurring area," not "safe/unsafe place."
- "Home-like/work-like cluster suppressed for privacy," not "your home" or "your workplace."

Avoid language like:
- "This location is dangerous."
- "You were near a crime when it happened."
- "This route is safe."

Begin implementation now.

Optional follow-up Codex prompts

Follow-up 1: harden Google Timeline parser
Audit the Google Timeline parser against additional fixture shapes. Add schema-detection tests for Semantic Location History, Records.json, and newer on-device Timeline exports. Improve parser error reporting so unsupported files return clear actionable errors without exposing raw user data. Keep parsing defensive and add fixtures for missing coordinates, missing timestamps, and malformed activity segments.

Follow-up 2: route-pattern V2
Add trip_event and route_pattern support. Extract origin-destination trip events from Google activitySegment records and from raw point transitions between stop visits. Create recurring route patterns by start cluster, end cluster, mode, and time-of-day bucket. For privacy, export only generalized route corridors and corridor-based crime summaries, not exact traces.

Follow-up 3: Tableau and BI polish
Add richer Tableau exports: place summary CSV, route summary CSV, optional GeoJSON export, and database views. Add a sample Tableau data dictionary. Ensure sensitive clusters are excluded by default. Add a small synthetic demo dataset that can be safely published publicly.

Follow-up 4: local-first upload preview
Create a lightweight frontend upload preview. It should detect file type, date range, approximate point/visit counts, and privacy mode before upload. It should not render raw points by default. Add a clear consent screen explaining what is processed, retained, deleted, and exported.
