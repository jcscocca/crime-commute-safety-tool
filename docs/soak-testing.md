# Postgres soak testing (H2)

Sustained-load validation of the **real Postgres deploy** on the ThinkPad. CI only ever
exercises SQLite, and `scripts/live_smoke.py` is a single fast pass — neither catches the
failure modes that only show up over hours under concurrency: connection-pool leaks,
sessions stuck idle-in-transaction, latency drift from plan flips or table bloat, lock
contention, and cache pressure. The soak harness drives the deploy hard and watches both the
client-side latency and the server-side Postgres internals.

The harness is two stdlib-only Python processes run side-by-side on the deploy host:

- **`scripts/soak/soak_driver.py`** — N threaded virtual users hammering the public
  dashboard endpoints; streams per-request latency to CSV and prints rolling p50/p95/p99.
- **`scripts/soak/pg_observer.py`** — samples `pg_stat_activity` / `pg_stat_database` /
  `pg_locks` every interval and diffs `pg_stat_statements` over the run, by shelling
  `docker compose exec db psql --csv` (no psycopg needed on the host).

## Prerequisites

1. **Deploy up** — bring the stack up on the ThinkPad the usual way:
   `pwsh -File scripts\start-waypoint.ps1`. This starts Postgres, the api (migrations run on
   boot), OTP, and llama-swap.
2. **Data ingested** — crime / calls / arrests data must already be loaded, or the dashboard
   queries return empty and the soak proves nothing. See `docs/DEPLOY.md`.
3. **Enable `pg_stat_statements` (one-time)** — the `db` service in `docker-compose.yml` sets
   `shared_preload_libraries=pg_stat_statements`, but a preload library only takes effect on
   server start. After pulling this change, recreate the db container once:

   ```
   docker compose --env-file .env.deploy up -d --force-recreate db
   ```

   The observer creates the extension itself (`CREATE EXTENSION IF NOT EXISTS
   pg_stat_statements`) and resets its counters at the start of each run.
4. **Python 3 on the host** — the scripts are stdlib-only. No pip installs.
5. **Run from the repo root** — the observer's default `psql` command is
   `docker compose --env-file .env.deploy exec -T db psql`, which resolves the compose
   project relative to the current directory.

## First run — start here

Two terminals, both at the repo root. Start the observer first so it captures the ramp-up:

```
# terminal 1 — Postgres observer
make soak-observe OUT=soak-out DURATION=2h

# terminal 2 — load driver
make soak-load USERS=25 DURATION=2h OUT=soak-out
```

Start at **25 virtual users for 2 hours** with a 15s observer interval. If that run is clean
against every pass criterion below, raise `USERS` on the next run (50, then 100) to find where
latency or the connection pool starts to bend. Both processes stop on their own at
`DURATION`; the driver also writes a partial summary if you Ctrl-C early.

Direct invocation (equivalent, if you want more knobs):

```
python scripts/soak/pg_observer.py --interval 15 --duration 2h --out soak-out
python scripts/soak/soak_driver.py --users 25 --ramp 60 --think-time 0.2 --duration 2h --out soak-out
```

## Outputs

All under `--out` (default `soak-out/`):

| File | From | Contents |
|---|---|---|
| `requests.csv` | driver | one row per request: `ts, vu, endpoint, status, latency_ms, ok` |
| `summary.json` | driver | per-endpoint + overall p50/p95/p99, latency drift, budget breaches |
| `pg_stats.csv` | observer | one row per interval: connections, cache hit ratio, locks, temp_bytes, … |
| `pg_summary.json` | observer | top statements by mean time + hot-table size deltas |

Correlate the two CSVs by the `ts` (unix-seconds) column.

## What to watch

| Signal (source) | Healthy | Trouble → what it means |
|---|---|---|
| active/idle connections (`pg_stats.csv`) | plateaus below the SQLAlchemy pool size | steadily climbing → **connection-pool leak** |
| `idle_in_txn` (`pg_stats.csv`) | ~0 | sustained > 0 → a session opened a transaction and never committed (**bug**) |
| latency drift (`summary.json` `drift`) | < ~1.3× | higher last-hour vs first-hour p95 → plan flip, table bloat, or cache pressure |
| `locks_not_granted` (`pg_stats.csv`) | 0 | > 0 sustained → **lock contention** (unexpected for a read-mostly workload) |
| `cache_hit_ratio` (`pg_stats.csv`) | ≈ ≥ 0.99, steady | falling over the run → working set outgrowing `shared_buffers` |
| `temp_bytes` (`pg_stats.csv`) | flat | climbing → queries spilling to disk (missing index / bad plan on the beat load) |
| `deadlocks` (`pg_stats.csv`) | 0 | > 0 → **bug** |
| top statements (`pg_summary.json`) | stable | a query whose mean time is unexpectedly high / a new expensive query |
| hot-table size delta (`pg_summary.json`) | ~0 on read-only tables | unexpected growth |
| error rate (`summary.json`) | ≈ 0 (bar intentional 4xx) | rising 5xx → the app or DB is shedding load |

## Pass criteria (H2)

A run **passes** when, for the full target duration at the target concurrency:

- the stack survives without crashing and error-rate stays ≈ 0 (excluding intentional 4xx);
- connections plateau below the pool size — no creep — and `idle_in_txn` stays ~0;
- per-endpoint p95 stays within budget and latency **drift** stays under ~1.3×;
- no deadlocks and no sustained not-granted locks.

Record which `USERS` level the run passed at; that's the validated sustained concurrency for
the current ThinkPad deploy.
