# Waypoint MVP Design

## Scope

Build a backend-first FastAPI MVP that imports personal mobility files, normalizes them into
stop visits and recurring place clusters, summarizes reported Seattle SPD incidents near those
recurring areas, and exports a Tableau-safe CSV.

## Architecture

The API layer stays thin and delegates to services. Parser adapters convert source files into
canonical observations and source-derived stops. Pure normalization modules perform haversine
distance calculations, point-stream stop detection, recurring-place clustering, and sensitive
location inference. SQLAlchemy models persist import batches, staging observations, stop visits,
place clusters, Seattle crime incidents, and place crime summaries.

## Privacy

Raw GPS points are staging inputs, not exported product objects. Demo user ids are hashed
server-side. Tableau-safe exports exclude sensitive clusters and use generalized display
coordinates.

## Testing

Unit tests cover parser behavior, E7 coordinate conversion, CSV parsing, stop detection,
place clustering, sensitive cluster inference, crime radius summaries, and Tableau export
privacy suppression. An API flow test exercises upload, normalization, sample crime ingestion,
summarization, place listing, and CSV export.
