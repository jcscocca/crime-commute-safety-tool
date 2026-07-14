#!/usr/bin/env python3
"""Postgres observer for CompCat's soak test (H2).

Samples pg_stat_activity / pg_stat_database / pg_locks on an interval and snapshots
pg_stat_statements over the run. Shells `docker compose exec db psql --csv` so the
host needs no psycopg — only Python 3. Pair with scripts/soak/soak_driver.py.

    python scripts/soak/pg_observer.py --interval 15 --out soak-out

See docs/soak-testing.md for the full runbook.
"""
from __future__ import annotations

import csv
import io

# --------------------------------------------------------------------------- #
# Pure transforms (unit-tested; no subprocess)
# --------------------------------------------------------------------------- #


def parse_psql_csv(raw: str, columns: list[str]) -> list[dict[str, str]]:
    """Parse `psql --csv -t` output (no header) into dicts keyed by columns."""
    reader = csv.reader(io.StringIO(raw))
    rows = []
    for record in reader:
        if not record:
            continue
        rows.append({col: (record[i] if i < len(record) else "") for i, col in enumerate(columns)})
    return rows


def _f(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def activity_metrics(rows: list[dict]) -> dict:
    idle_txn_states = {"idle in transaction", "idle in transaction (aborted)"}
    active = [r for r in rows if r["state"] == "active"]
    idle_txn = [r for r in rows if r["state"] in idle_txn_states]
    return {
        "total": len(rows),
        "active": len(active),
        "idle": sum(1 for r in rows if r["state"] == "idle"),
        "idle_in_transaction": len(idle_txn),
        "waiting": sum(1 for r in active if r.get("wait_event_type")),
        "longest_query_age_s": max((_f(r["query_age"]) for r in active), default=0.0),
        "longest_idle_in_txn_s": max((_f(r["state_age"]) for r in idle_txn), default=0.0),
    }


def database_window(prev: dict, cur: dict, start: dict) -> dict:
    """Windowed view of pg_stat_database's cumulative counters.

    pg_stat_database counters accumulate for the life of the datadir, so logging them
    raw would make the runbook thresholds fire on pre-soak history. Instead:
    - cache_hit_ratio is over the interval since the previous sample, so intra-run
      cache pressure is visible (a lifetime ratio barely moves over 2h);
    - deadlocks/temp_bytes/xact are deltas since run start, so they reflect the soak
      itself — deadlocks_run > 0 means a deadlock happened DURING this run.
    """
    d_hit = _f(cur["blks_hit"]) - _f(prev["blks_hit"])
    d_read = _f(cur["blks_read"]) - _f(prev["blks_read"])
    interval = d_hit + d_read
    return {
        "numbackends": int(_f(cur["numbackends"])),
        "cache_hit_ratio": round(d_hit / interval, 4) if interval > 0 else None,
        "deadlocks_run": int(_f(cur["deadlocks"]) - _f(start["deadlocks"])),
        "temp_bytes_run": int(_f(cur["temp_bytes"]) - _f(start["temp_bytes"])),
        "xact_run": int(_f(cur["xact_commit"]) - _f(start["xact_commit"])),
    }


def lock_metrics(rows: list[dict]) -> dict:
    by_mode: dict[str, int] = {}
    not_granted = 0
    for r in rows:
        by_mode[r["mode"]] = by_mode.get(r["mode"], 0) + 1
        if r.get("granted") == "f":
            not_granted += 1
    return {"total": len(rows), "not_granted": not_granted, "by_mode": by_mode}


def statements_diff(start_rows: list[dict], end_rows: list[dict]) -> list[dict]:
    """Rank statements by mean exec time; report growth vs a start baseline if given.

    The observer resets pg_stat_statements at run start, so end values already reflect
    this run; passing an empty start list leaves mean_ratio None and ranks by mean_ms_end.
    """
    start_by_id = {r["queryid"]: r for r in start_rows}
    out = []
    for r in end_rows:
        s = start_by_id.get(r["queryid"])
        mean_start = _f(s["mean_exec_time"]) if s else 0.0
        mean_end = _f(r["mean_exec_time"])
        out.append({
            "queryid": r["queryid"],
            "query": r.get("query", "")[:200],
            "calls": int(_f(r.get("calls", "0"))),
            "mean_ms_start": mean_start,
            "mean_ms_end": mean_end,
            "mean_ratio": round(mean_end / mean_start, 2) if mean_start else None,
            "max_ms_end": _f(r.get("max_exec_time", "0")),
        })
    out.sort(key=lambda d: d["mean_ms_end"], reverse=True)
    return out


# --------------------------------------------------------------------------- #
# Runtime (subprocess + sampling loop over the pure transforms above)
# --------------------------------------------------------------------------- #

import argparse  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import shlex  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402

# The standalone script is invoked as a file (make / `python scripts/soak/pg_observer.py`),
# which puts scripts/soak (not the repo root) on sys.path — so `scripts.soak.*` would not
# resolve. Put the repo root first so the shared parse_duration import below works under
# every invocation (file, make, `-m`).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from scripts.soak.soak_driver import parse_duration  # noqa: E402

_DEFAULT_PSQL = "docker compose --env-file .env.deploy exec -T db psql -U mca -d mca"

_ACTIVITY_SQL = (
    "SELECT state, coalesce(wait_event_type,''), "
    "coalesce(extract(epoch from (now()-query_start))::text,''), "
    "coalesce(extract(epoch from (now()-state_change))::text,'') "
    "FROM pg_stat_activity WHERE datname='mca' AND pid<>pg_backend_pid()"
)
_ACTIVITY_COLS = ["state", "wait_event_type", "query_age", "state_age"]

_DB_SQL = (
    "SELECT numbackends, xact_commit, xact_rollback, blks_read, blks_hit, "
    "deadlocks, temp_files, temp_bytes FROM pg_stat_database WHERE datname='mca'"
)
_DB_COLS = ["numbackends", "xact_commit", "xact_rollback", "blks_read", "blks_hit",
            "deadlocks", "temp_files", "temp_bytes"]

# Scope locks to mca-connected backends and drop the observer's own psql session, matching
# how the activity query scopes — otherwise locks_total is inflated by other databases and
# the observer's own catalog locks.
_LOCK_SQL = ("SELECT l.mode, l.granted FROM pg_locks l "
             "JOIN pg_stat_activity a ON l.pid = a.pid "
             "WHERE a.datname='mca' AND l.pid <> pg_backend_pid()")
_LOCK_COLS = ["mode", "granted"]

_STMT_SQL = (
    "SELECT queryid, calls, mean_exec_time, max_exec_time, query "
    "FROM pg_stat_statements ORDER BY total_exec_time DESC LIMIT 20"
)
_STMT_COLS = ["queryid", "calls", "mean_exec_time", "max_exec_time", "query"]

_SIZE_SQL = ("SELECT relname, pg_total_relation_size(relid) FROM pg_stat_user_tables "
             "ORDER BY pg_total_relation_size(relid) DESC")
_SIZE_COLS = ["relname", "bytes"]


class _Psql:
    def __init__(self, base_cmd: str) -> None:
        self._prefix = shlex.split(base_cmd)

    def query(self, sql: str, columns: list[str]) -> list[dict]:
        proc = subprocess.run(self._prefix + ["--csv", "-t", "-c", sql],
                              capture_output=True, text=True, timeout=30)
        if proc.returncode != 0:
            raise RuntimeError(f"psql failed: {proc.stderr.strip()}")
        return parse_psql_csv(proc.stdout, columns)

    def exec(self, sql: str) -> None:
        subprocess.run(self._prefix + ["-c", sql], capture_output=True, text=True, timeout=30)


def _bootstrap(psql: _Psql) -> None:
    psql.exec("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
    psql.exec("SELECT pg_stat_statements_reset()")


def _pg_stat_statements_ready(psql: _Psql) -> bool:
    try:
        psql.query("SELECT 1 FROM pg_stat_statements LIMIT 1", ["x"])
        return True
    except (RuntimeError, subprocess.TimeoutExpired):
        return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="CompCat Postgres soak observer")
    ap.add_argument("--interval", type=float, default=float(os.environ.get("SOAK_PG_INTERVAL", 15)))
    ap.add_argument("--duration", default=os.environ.get("SOAK_DURATION", "2h"))
    ap.add_argument("--out", default=os.environ.get("SOAK_OUT", "soak-out"))
    ap.add_argument("--psql-cmd", default=os.environ.get("SOAK_PSQL_CMD", _DEFAULT_PSQL))
    args = ap.parse_args(argv)

    os.makedirs(args.out, exist_ok=True)
    psql = _Psql(args.psql_cmd)
    _bootstrap(psql)
    if not _pg_stat_statements_ready(psql):
        print("[observer] pg_stat_statements is not available — enable it once (prereq 3):\n"
              "  docker compose --env-file .env.deploy up -d --force-recreate db\n"
              "then re-run. See docs/soak-testing.md.", flush=True)
        return 1

    try:
        db_rows = psql.query(_DB_SQL, _DB_COLS)
        sizes_start = {r["relname"]: int(_f(r["bytes"])) for r in psql.query(_SIZE_SQL, _SIZE_COLS)}
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"[observer] baseline snapshot failed: {exc}", flush=True)
        return 1
    if not db_rows:
        print("[observer] pg_stat_database has no 'mca' row — is the app db up?", flush=True)
        return 1
    db_start = db_rows[0]
    prev_db = db_start

    deadline = time.monotonic() + parse_duration(args.duration)

    stats_path = os.path.join(args.out, "pg_stats.csv")
    with open(stats_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["ts", "conn_total", "active", "idle", "idle_in_txn", "waiting",
                         "longest_query_s", "longest_idle_txn_s", "cache_hit_ratio",
                         "deadlocks_run", "temp_bytes_run", "locks_total", "locks_not_granted"])
        while time.monotonic() < deadline:
            try:
                act = activity_metrics(psql.query(_ACTIVITY_SQL, _ACTIVITY_COLS))
                dbrows = psql.query(_DB_SQL, _DB_COLS)
                cur_db = dbrows[0] if dbrows else prev_db
                db = database_window(prev_db, cur_db, db_start)
                prev_db = cur_db
                lk = lock_metrics(psql.query(_LOCK_SQL, _LOCK_COLS))
            except (RuntimeError, subprocess.TimeoutExpired) as exc:
                print(f"[observer] sample failed: {exc}", flush=True)
                time.sleep(args.interval)
                continue
            writer.writerow([
                f"{time.time():.0f}", act["total"], act["active"], act["idle"],
                act["idle_in_transaction"], act["waiting"],
                f"{act['longest_query_age_s']:.1f}", f"{act['longest_idle_in_txn_s']:.1f}",
                db["cache_hit_ratio"], db["deadlocks_run"], db["temp_bytes_run"],
                lk["total"], lk["not_granted"]])
            fh.flush()
            print(f"[{time.strftime('%H:%M:%S')}] conns={act['total']} active={act['active']} "
                  f"idle_txn={act['idle_in_transaction']} wait={act['waiting']} "
                  f"cache={db['cache_hit_ratio']} deadlocks_run={db['deadlocks_run']} "
                  f"not_granted={lk['not_granted']}", flush=True)
            time.sleep(args.interval)

    try:
        stmts = statements_diff([], psql.query(_STMT_SQL, _STMT_COLS))
        sizes_end = {r["relname"]: int(_f(r["bytes"])) for r in psql.query(_SIZE_SQL, _SIZE_COLS)}
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"[observer] end-of-run snapshot failed: {exc}", flush=True)
        stmts, sizes_end = [], {}
    size_delta = {k: sizes_end.get(k, 0) - sizes_start.get(k, 0) for k in sizes_end}
    summary = {"top_statements": stmts[:20], "table_size_delta_bytes": size_delta}
    with open(os.path.join(args.out, "pg_summary.json"), "w") as fh:
        json.dump(summary, fh, indent=2)
    print("top statement (by mean end):", stmts[0] if stmts else "none")
    print("table size deltas:", size_delta)
    return 0


if __name__ == "__main__":
    sys.exit(main())
