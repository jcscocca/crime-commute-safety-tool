# Postgres soak-test harness (H2) — design

**Status:** approved (2026-07-02), pre-implementation
**Roadmap item:** H2 — Long-run Postgres validation under load
**Worktree/branch:** `h2-postgres-soak`

## Problem

Waypoint's deploy runs on real Postgres 16 (the ThinkPad, via `scripts/start-waypoint.ps1`
→ `docker compose`), but its correctness is only ever exercised by SQLite in CI and by
short single-pass smoke runs (`scripts/live_smoke.py`). Nothing today drives the deploy
under **sustained concurrent load** to surface the failure modes that only appear over
hours: connection-pool leaks, sessions stuck idle-in-transaction, latency drift from plan
flips or table bloat, lock contention, and working-set pressure on `shared_buffers`.

H2 is that missing validation. It is an **ops exercise**, not a code-behavior change: stand
up the existing deploy, drive it hard for hours, and watch both the client-side latency and
the server-side Postgres internals.

## Goal & pass criteria

Prove **both stability and latency** over a sustained run:

- **Stability** — the stack survives the full duration with error-rate ≈ 0 (excluding
  intentional 4xx), no connection creep, no sustained idle-in-transaction backends, no
  deadlocks, and no lock contention.
- **Latency** — per-endpoint p95 stays within budget, and **latency drift** (last-hour p95
  ÷ first-hour p95) stays under ~1.3×.

A run "passes H2" when all of the above hold for the target duration at the target
concurrency.

## Non-goals / YAGNI

- No third-party load framework (locust/k6) — the deploy host is Windows and docker-only;
  a stdlib-threads driver avoids installing a new binary and matches `live_smoke.py`.
- No Grafana/live dashboard — streamed CSV + periodic console lines + a final summary are
  enough; the CSVs can be opened later in a notebook or the app's own Tableau exports.
- No multi-host / distributed load — a single-ThinkPad deploy doesn't need it.
- No CI integration — the soak is an on-demand ops tool, explicitly **out of**
  `make test-all`. Only the scripts' pure logic is unit-tested (so `make test-all` stays
  green).
- The harness **does not run the soak itself**. It delivers the tooling + runbook; the user
  kicks off the multi-hour run on the ThinkPad (the run is measured in hours and the host is
  not reachable from the dev machine).

## Components

### 1. Load driver — `scripts/soak/soak_driver.py`

Stdlib-only, threads for concurrency (matches `live_smoke.py`'s `urllib` + `CookieJar`
pattern; the workload is I/O-bound so the GIL is a non-issue up to low-hundreds of virtual
users). Runs on the ThinkPad host against `http://localhost:8000`.

- **Virtual users (VUs):** each thread establishes its own session (`POST /sessions`, own
  cookie jar), seeds/reuses a set of real Seattle places spread across *different beats*,
  then loops a **weighted read-mix** over the perf-sensitive public endpoints:
  - `POST /dashboard/analyze`
  - `POST /dashboard/neighborhood` (the whole-beat baseline load — the heaviest path)
  - `POST /dashboard/compare`
  - `POST /dashboard/incidents`
  - `GET  /dashboard/summary`
  - `GET  /dashboard/freshness` (TTL-cached — cheap sanity)
  - occasional `GET /exports/tableau/place-summary.csv`
- **Parameter variation:** radii (250/500/1000), date window, `offense_category`
  (None/PROPERTY/…), and which place — all drawn from a `--seed`-seeded RNG so runs are
  reproducible and don't all collapse onto one cache line.
- **CLI/env:** `--users`, `--duration` (e.g. `4h`) *or* `--requests`, `--ramp` (ramp-up
  seconds), `--think-time`, `--base-url` (default `http://localhost:8000`), `--seed`,
  `--out` (results dir). Env fallbacks (`SOAK_*`) mirror the flags.
- **Output:**
  - `requests.csv` streamed to disk as rows complete (crash-safe): `ts, vu, endpoint,
    status, latency_ms, ok`.
  - Rolling console line every ~30s: elapsed, throughput (req/s), error-rate, windowed
    p50/p95/p99.
  - Final `summary.json` + console table: per-endpoint count / error-rate / p50 / p95 / p99
    / max, overall, **latency-drift ratio** (last-hour p95 ÷ first-hour p95), and per-endpoint
    p95 **budget breaches**.
- **Latency budgets:** a small default dict of per-endpoint p95 budgets (overridable via a
  `--budgets` JSON file). Breaches are flagged, not fatal.

### 2. Postgres observer — `scripts/soak/pg_observer.py`

Stdlib + `subprocess`, shelling to `docker compose --env-file .env.deploy exec -T db psql
-A -F,` so **no psycopg is required on the host** (the deploy is docker-only; the host only
needs Python 3). The `psql` invocation is overridable via `--psql-cmd` for hosts that would
rather connect over the published `:5432` with a real DSN.

Every interval (default 15s) it samples and appends `pg_stats.csv`:

- **`pg_stat_activity`** — total / active / idle / **idle-in-transaction** connections,
  waiting backends (`wait_event_type IS NOT NULL`), longest running-query age, longest
  idle-in-transaction age.
- **`pg_stat_database`** (`datname='mca'`) — commit/rollback, **cache hit ratio**
  (`blks_hit / (blks_hit + blks_read)`), deadlocks, `temp_files` / `temp_bytes` (disk spill),
  tuples returned/fetched.
- **`pg_locks`** — counts by mode + **not-granted** count (contention).

At **run start** it self-bootstraps `CREATE EXTENSION IF NOT EXISTS pg_stat_statements` and
calls `pg_stat_statements_reset()`; at **run end** it snapshots the top-N queries by
`total_exec_time` (`calls`, `mean_exec_time`, `max_exec_time`, `stddev`). Because the run
starts from a reset baseline, a query whose `mean_exec_time` grew across the run is a
**plan-drift** signal. Hot-table sizes (`incidents` / `calls` / `arrests`, via
`pg_total_relation_size`) are captured at start and end to expose **bloat** deltas.

The observer prints a per-interval console line mirroring the key gauges and writes a final
`pg_summary.json` with the deltas and any thresholds tripped.

**Design seam for testing:** the "raw psql rows → metrics dict" transforms are pure
functions (no subprocess/DB), unit-tested with canned `psql -A -F,` output. The subprocess
call is a thin uncovered shim.

### 3. Infra change — enable `pg_stat_statements`

Add to the `db` service in `docker-compose.yml`:

```yaml
    command:
      - "postgres"
      - "-c"
      - "shared_preload_libraries=pg_stat_statements"
      - "-c"
      - "pg_stat_statements.track=all"
```

`shared_preload_libraries` requires a server restart, so the one-time step to pick it up is
`docker compose --env-file .env.deploy up -d --force-recreate db` (documented in the
runbook). The extension itself is created by the observer at run start. Overhead is a few MB
of shared memory — harmless for normal dev, and useful for any future perf work.

### 4. Runbook — `docs/soak-testing.md`

The operator-facing checklist:

- **Prereqs:** deploy up (`start-waypoint.ps1`); crime/calls/arrests data ingested;
  `pg_stat_statements` enabled (the one-time `--force-recreate db`); Python 3 on the host.
- **First-run recipe (baked in):** a concrete starting point — e.g. ramp to **25 VUs over
  60s**, hold for **2 hours**, 15s observer interval — with the exact two commands to run
  (observer in one terminal, driver in another) and where output lands. Framed as "start
  here, then scale users up on the next run once this is clean."
- **How to run + where output lands** (`--out` dir with `requests.csv`, `summary.json`,
  `pg_stats.csv`, `pg_summary.json`).
- **What to watch — thresholds and what each symptom means:**
  | Signal | Healthy | Trouble → meaning |
  |---|---|---|
  | active/idle connections | plateau below pool size | climbing → **pool leak** |
  | idle-in-transaction | ~0 | sustained > 0 → a session not committing (**bug**) |
  | latency drift (last-hr/first-hr p95) | < ~1.3× | higher → plan flip / bloat / cache pressure |
  | `pg_locks` not-granted | 0 | > 0 sustained → **contention** (unexpected read-mostly) |
  | cache hit ratio | ≈ ≥ 0.99, steady | falling → working set outgrowing `shared_buffers` |
  | `temp_bytes` | flat | climbing → queries spilling to disk (bad plan / missing index) |
  | deadlocks | 0 | > 0 → **bug** |
  | `pg_stat_statements` end-diff | stable means | a query's mean grew / new expensive query |
  | hot-table size delta | ~0 on read-only tables | unexpected growth |
- **Pass criteria** — restated from the Goal section.

### 5. Wiring

- `make soak-observe` and `make soak-load` Makefile targets (thin wrappers passing through
  `USERS` / `DURATION` / `OUT`). Kept **out of** `make test-all`.
- Unit tests (`tests/test_soak_driver.py`, `tests/test_pg_observer.py`) covering:
  - percentile computation (p50/p95/p99, edge cases: empty, single, exact-boundary),
  - weighted endpoint selection (distribution respects weights under a fixed seed),
  - latency-drift ratio + budget-breach flagging,
  - summary rollup shape,
  - observer row→metrics transforms (connection buckets, cache-hit-ratio math, lock counts,
    statements diff) from canned psql output.

## Data flow

```
                     ThinkPad host
  ┌───────────────────────────────────────────────────────────┐
  │  soak_driver.py  ──HTTP──▶  api :8000  ──▶  db :5432 (pg)   │
  │      │  (N VU threads, weighted read-mix)        ▲          │
  │      ▼                                           │          │
  │  requests.csv / summary.json          pg_observer.py        │
  │                                  (docker compose exec db     │
  │                                   psql, 15s interval)        │
  │                                           │                  │
  │                                           ▼                  │
  │                              pg_stats.csv / pg_summary.json  │
  └───────────────────────────────────────────────────────────┘
```

Driver and observer are independent processes started together; neither depends on the
other's output. Correlation is by wall-clock timestamp across the two CSVs.

## Testing strategy

- Pure logic (percentiles, weighted selection, drift/budget flagging, summary rollup, and
  the observer's row→metrics transforms) is unit-tested with no server or DB — keeps
  `make test-all` green and follows the repo's TDD cadence.
- No live-Postgres integration test in CI (CI uses SQLite). The DB-touching code sits behind
  the pure-transform seam so tests exercise the parsing/aggregation, not the socket.
- Manual validation is the soak run itself, per the runbook.

## Process

Dedicated worktree (`h2-postgres-soak`), TDD, `make test-all` green, fold the H2 ROADMAP
tick, PR → user squash-merges. Files touched:

- `scripts/soak/soak_driver.py` (new)
- `scripts/soak/pg_observer.py` (new)
- `docs/soak-testing.md` (new)
- `docker-compose.yml` (`db` service `command:` — the only infra edit)
- `Makefile` (`soak-observe`, `soak-load` targets)
- `tests/test_soak_driver.py`, `tests/test_pg_observer.py` (new)
- `docs/ROADMAP.md` (H2 tick)
