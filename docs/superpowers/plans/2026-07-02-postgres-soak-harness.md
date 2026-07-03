# Postgres Soak-Test Harness (H2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship an on-demand harness (load driver + Postgres observer + runbook) that drives the ThinkPad's real-Postgres deploy under sustained concurrent load and surfaces stability + latency regressions.

**Architecture:** Two stdlib-only Python processes run side-by-side on the deploy host. `soak_driver.py` spins up N threaded virtual users that hammer the public dashboard endpoints and streams per-request latency to CSV. `pg_observer.py` shells `docker compose exec db psql --csv` on an interval to sample `pg_stat_activity` / `pg_stat_database` / `pg_locks` / `pg_stat_statements`. All the analysis logic (percentiles, weighted selection, metric transforms) is pure and unit-tested; the threading/HTTP/subprocess shells are thin and uncovered. A one-line `docker-compose.yml` edit enables `pg_stat_statements`.

**Tech Stack:** Python 3.11 stdlib (`urllib`, `threading`, `csv`, `subprocess`, `random`, `statistics`), pytest, Docker Compose + Postgres 16, Makefile.

---

## File structure

- Create: `scripts/soak/__init__.py` — empty, makes `scripts.soak` importable by tests.
- Create: `scripts/soak/soak_driver.py` — load driver: pure helpers + threaded runtime.
- Create: `scripts/soak/pg_observer.py` — observer: pure transforms + sampling runtime.
- Create: `tests/test_soak_driver.py` — unit tests for the driver's pure logic + contract check.
- Create: `tests/test_pg_observer.py` — unit tests for the observer's pure transforms.
- Create: `tests/test_soak_docs.py` — asserts the runbook + compose change stay documented.
- Create: `docs/soak-testing.md` — operator runbook.
- Modify: `docker-compose.yml` — add `command:` to the `db` service.
- Modify: `Makefile` — add `soak-load` / `soak-observe` targets + `.PHONY`.
- Modify: `docs/ROADMAP.md` — tick H2.

`tests/` imports the scripts as `from scripts.soak import soak_driver`. Confirm `scripts/` is import-reachable: repo root is on `sys.path` in tests (pytest rootdir). Add `scripts/soak/__init__.py`; `scripts/__init__.py` does **not** exist and other `scripts/*.py` are run as files, so import via the `scripts.soak` package only (Task 1 Step 0 verifies this resolves).

---

## Task 1: Driver pure helpers

**Files:**
- Create: `scripts/soak/__init__.py`
- Create: `scripts/soak/soak_driver.py`
- Test: `tests/test_soak_driver.py`

- [ ] **Step 0: Create the package marker and confirm import path**

Create `scripts/soak/__init__.py` (empty file).

Run: `cd <worktree> && .venv/bin/python -c "import scripts.soak; print('ok')"`
Expected: `ok` (repo root is importable). If it fails with ModuleNotFoundError, create an empty `scripts/__init__.py` too and re-run.

- [ ] **Step 1: Write failing tests for the pure helpers**

Create `tests/test_soak_driver.py`:

```python
import random

import pytest

from app.api.dashboard_schemas import (
    DashboardAnalyzeRequest,
    DashboardCompareRequest,
    DashboardIncidentDetailsRequest,
)
from scripts.soak import soak_driver as sd


def test_parse_duration_units():
    assert sd.parse_duration("90s") == 90
    assert sd.parse_duration("5m") == 300
    assert sd.parse_duration("2h") == 7200
    assert sd.parse_duration("120") == 120  # bare seconds


def test_parse_duration_rejects_garbage():
    with pytest.raises(ValueError):
        sd.parse_duration("later")


def test_percentile_basic():
    values = list(range(1, 101))  # 1..100
    assert sd.percentile(values, 50) == pytest.approx(50, abs=1)
    assert sd.percentile(values, 95) == pytest.approx(95, abs=1)
    assert sd.percentile(values, 99) == pytest.approx(99, abs=1)


def test_percentile_edges():
    assert sd.percentile([], 95) is None
    assert sd.percentile([42.0], 95) == 42.0


def test_choose_endpoint_respects_weights():
    rng = random.Random(1234)
    weights = {"a": 1, "b": 0, "c": 3}
    picks = [sd.choose_endpoint(rng, weights) for _ in range(2000)]
    assert picks.count("b") == 0  # zero weight never chosen
    assert picks.count("c") > picks.count("a")  # 3:1 ratio, comfortably


def test_build_body_validates_against_real_schemas():
    rng = random.Random(7)
    place_ids = ["p1", "p2", "p3"]
    # Every endpoint the driver hits with a POST body must produce a body the
    # real Pydantic request model accepts — this pins the driver to the API contract.
    DashboardAnalyzeRequest.model_validate(sd.build_body("analyze", rng, place_ids))
    DashboardAnalyzeRequest.model_validate(sd.build_body("neighborhood", rng, place_ids))
    DashboardIncidentDetailsRequest.model_validate(sd.build_body("incidents", rng, place_ids))
    DashboardCompareRequest.model_validate(sd.build_body("compare", rng, place_ids))


def test_summarize_rollup_and_drift():
    # first-hour rows ~100ms, last-hour rows ~300ms → drift ≈ 3x on /analyze.
    rows = []
    base = 1_000_000.0
    for i in range(600):
        rows.append(sd.RequestRecord(ts=base + i, vu=0, endpoint="analyze", status=200, latency_ms=100.0, ok=True))
    for i in range(600):
        rows.append(sd.RequestRecord(ts=base + 7200 + i, vu=0, endpoint="analyze", status=200, latency_ms=300.0, ok=True))
    rows.append(sd.RequestRecord(ts=base + 10, vu=1, endpoint="analyze", status=500, latency_ms=5.0, ok=False))
    summary = sd.summarize(rows, budgets={"analyze": 150.0})
    ep = summary["endpoints"]["analyze"]
    assert ep["count"] == 1201
    assert ep["errors"] == 1
    assert summary["drift"]["analyze"] == pytest.approx(3.0, rel=0.1)
    assert "analyze" in summary["budget_breaches"]  # p95 ~300 > 150
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `.venv/bin/python -m pytest tests/test_soak_driver.py -q`
Expected: FAIL — `ModuleNotFoundError` / `AttributeError` (helpers not defined).

- [ ] **Step 3: Implement the pure helpers**

Create `scripts/soak/soak_driver.py` with the module docstring and this pure core (runtime added in Task 2):

```python
#!/usr/bin/env python3
"""Sustained-load driver for Waypoint's Postgres soak test (H2).

Spins up N threaded virtual users that hammer the public dashboard endpoints and
streams per-request latency to CSV. Pair with scripts/soak/pg_observer.py.

Run on the deploy host against the live api:
    python scripts/soak/soak_driver.py --users 25 --ramp 60 --duration 2h --out soak-out

See docs/soak-testing.md for the full runbook.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

# --------------------------------------------------------------------------- #
# Pure helpers (unit-tested; no I/O)
# --------------------------------------------------------------------------- #

_ENDPOINT_WEIGHTS: dict[str, int] = {
    "analyze": 4,
    "neighborhood": 3,   # whole-beat baseline — the heaviest query path
    "incidents": 2,
    "compare": 1,
    "summary": 2,        # GET, reflects the VU's latest analyze run
    "freshness": 1,      # GET, TTL-cached — cheap sanity
    "export": 1,         # GET place-summary.csv
}

# Real Seattle coordinates spread across different SPD beats so queries don't all
# collapse onto one cached beat. (label, lat, lon)
_SEATTLE_POINTS: list[tuple[str, float, float]] = [
    ("Pike-1st", 47.6090, -122.3380),
    ("3rd-Pine", 47.6113, -122.3378),
    ("Capitol Hill", 47.6190, -122.3210),
    ("U District", 47.6600, -122.3130),
    ("Ballard", 47.6680, -122.3840),
    ("West Seattle Junction", 47.5610, -122.3870),
    ("Rainier Beach", 47.5210, -122.2680),
    ("SODO", 47.5800, -122.3340),
    ("Northgate", 47.7070, -122.3270),
    ("Georgetown", 47.5470, -122.3200),
]

_RADII = [250, 500, 1000]
_OFFENSE_CATEGORIES = [None, "PROPERTY", "PERSON", "SOCIETY"]
_DATE_WINDOWS = [
    ("2024-01-01", "2026-06-30"),
    ("2025-01-01", "2026-06-30"),
    ("2023-06-01", "2025-06-30"),
]


def parse_duration(text: str) -> int:
    """Parse '90s'/'5m'/'2h'/'120' into seconds."""
    text = text.strip().lower()
    units = {"s": 1, "m": 60, "h": 3600}
    if text and text[-1] in units:
        try:
            return int(float(text[:-1]) * units[text[-1]])
        except ValueError as exc:
            raise ValueError(f"bad duration: {text!r}") from exc
    try:
        return int(text)
    except ValueError as exc:
        raise ValueError(f"bad duration: {text!r}") from exc


def percentile(values: list[float], q: float) -> float | None:
    """Nearest-rank percentile of unsorted values; None if empty."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = q / 100.0 * (len(ordered) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(ordered) - 1)
    frac = rank - lo
    return ordered[lo] + (ordered[hi] - ordered[lo]) * frac


def choose_endpoint(rng: random.Random, weights: dict[str, int]) -> str:
    names = list(weights)
    return rng.choices(names, weights=[weights[n] for n in names], k=1)[0]


def build_body(endpoint: str, rng: random.Random, place_ids: list[str]) -> dict:
    """Build a schema-valid request body for a POST endpoint."""
    start, end = rng.choice(_DATE_WINDOWS)
    offense = rng.choice(_OFFENSE_CATEGORIES)
    if endpoint == "compare":
        picks = rng.sample(place_ids, k=min(2, len(place_ids)))
        if len(picks) < 2:
            picks = (place_ids * 2)[:2]
        return {
            "place_ids": picks,
            "analysis_start_date": start,
            "analysis_end_date": end,
            "radius_m": rng.choice(_RADII),
            "offense_category": offense,
        }
    body = {
        "place_ids": [rng.choice(place_ids)],
        "analysis_start_date": start,
        "analysis_end_date": end,
        "radii_m": [rng.choice(_RADII)],
        "offense_category": offense,
    }
    if endpoint == "incidents":
        body["limit"] = rng.choice([50, 100, 200])
    return body


@dataclass
class RequestRecord:
    ts: float
    vu: int
    endpoint: str
    status: int
    latency_ms: float
    ok: bool


def summarize(rows: list[RequestRecord], budgets: dict[str, float]) -> dict:
    """Per-endpoint stats, overall, first-vs-last-hour p95 drift, budget breaches."""
    by_ep: dict[str, list[RequestRecord]] = {}
    for r in rows:
        by_ep.setdefault(r.endpoint, []).append(r)

    endpoints: dict[str, dict] = {}
    drift: dict[str, float] = {}
    breaches: list[str] = []
    if rows:
        t0 = min(r.ts for r in rows)
        t_end = max(r.ts for r in rows)
    else:
        t0 = t_end = 0.0

    for ep, ep_rows in by_ep.items():
        lat = [r.latency_ms for r in ep_rows if r.ok]
        p95 = percentile(lat, 95)
        endpoints[ep] = {
            "count": len(ep_rows),
            "errors": sum(1 for r in ep_rows if not r.ok),
            "p50": percentile(lat, 50),
            "p95": p95,
            "p99": percentile(lat, 99),
            "max": max(lat) if lat else None,
        }
        # drift: last-hour p95 / first-hour p95 (needs ≥ ~2h of data to be meaningful).
        first = [r.latency_ms for r in ep_rows if r.ok and r.ts <= t0 + 3600]
        last = [r.latency_ms for r in ep_rows if r.ok and r.ts >= t_end - 3600]
        fp95, lp95 = percentile(first, 95), percentile(last, 95)
        if fp95 and lp95:
            drift[ep] = lp95 / fp95
        if p95 is not None and ep in budgets and p95 > budgets[ep]:
            breaches.append(ep)

    all_lat = [r.latency_ms for r in rows if r.ok]
    return {
        "endpoints": endpoints,
        "overall": {
            "count": len(rows),
            "errors": sum(1 for r in rows if not r.ok),
            "p50": percentile(all_lat, 50),
            "p95": percentile(all_lat, 95),
            "p99": percentile(all_lat, 99),
            "duration_s": t_end - t0,
        },
        "drift": drift,
        "budget_breaches": breaches,
    }
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `.venv/bin/python -m pytest tests/test_soak_driver.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/soak/__init__.py scripts/soak/soak_driver.py tests/test_soak_driver.py
git commit -m "feat(soak): load-driver pure helpers (percentiles, weighting, body builder)"
```

---

## Task 2: Driver runtime

**Files:**
- Modify: `scripts/soak/soak_driver.py` (append runtime)

Runtime is thin I/O glue over Task-1 helpers; not unit-tested (Task 1's `build_body` contract test already guards the request shapes). Verify by a short live-free dry check.

- [ ] **Step 1: Append the runtime**

Append to `scripts/soak/soak_driver.py`:

```python
import argparse
import csv
import http.cookiejar
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

_DEFAULT_BUDGETS: dict[str, float] = {
    "analyze": 400.0, "neighborhood": 800.0, "incidents": 400.0,
    "compare": 600.0, "summary": 300.0, "freshness": 100.0, "export": 500.0,
}


class _Recorder:
    """Thread-safe: append rows to memory + stream to a CSV file handle."""

    def __init__(self, csv_path: str) -> None:
        self._lock = threading.Lock()
        self.rows: list[RequestRecord] = []
        self._fh = open(csv_path, "w", newline="")
        self._writer = csv.writer(self._fh)
        self._writer.writerow(["ts", "vu", "endpoint", "status", "latency_ms", "ok"])

    def add(self, rec: RequestRecord) -> None:
        with self._lock:
            self.rows.append(rec)
            self._writer.writerow([f"{rec.ts:.3f}", rec.vu, rec.endpoint, rec.status,
                                   f"{rec.latency_ms:.1f}", int(rec.ok)])
            self._fh.flush()

    def snapshot(self) -> list[RequestRecord]:
        with self._lock:
            return list(self.rows)

    def close(self) -> None:
        with self._lock:
            self._fh.close()


def _new_opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def _timed_request(opener, method, url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    t0 = time.monotonic()
    try:
        with opener.open(req, timeout=60) as resp:
            resp.read()
            status = resp.status
    except urllib.error.HTTPError as exc:
        exc.read()
        status = exc.code
    except (urllib.error.URLError, TimeoutError):
        status = 0
    return status, (time.monotonic() - t0) * 1000.0


def _seed_places(opener, base_url, rng) -> list[str]:
    ids: list[str] = []
    for label, lat, lon in rng.sample(_SEATTLE_POINTS, k=3):
        status, _ = _timed_request(opener, "POST", base_url + "/places", {
            "display_label": f"Soak {label}", "latitude": lat, "longitude": lon, "visit_count": 3,
        })
        # /places returns the created id in the body; re-request to read it cleanly.
    # Re-fetch the VU's places to collect ids (GET /places).
    req = urllib.request.Request(base_url + "/places", method="GET")
    try:
        with opener.open(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
    except Exception:
        return ids
    for p in (data if isinstance(data, list) else data.get("places", [])):
        if isinstance(p, dict) and p.get("id"):
            ids.append(p["id"])
    return ids


_GET_PATHS = {
    "summary": "/dashboard/summary",
    "freshness": "/dashboard/freshness",
    "export": "/exports/tableau/place-summary.csv",
}
_POST_PATHS = {
    "analyze": "/dashboard/analyze",
    "neighborhood": "/dashboard/neighborhood",
    "incidents": "/dashboard/incidents",
    "compare": "/dashboard/compare",
}


def _run_vu(vu_id, base_url, deadline, think_time, seed, recorder, ramp_delay):
    time.sleep(ramp_delay)
    rng = random.Random(seed + vu_id)
    opener = _new_opener()
    _timed_request(opener, "POST", base_url + "/sessions")
    place_ids = _seed_places(opener, base_url, rng)
    if not place_ids:
        return
    while time.monotonic() < deadline:
        ep = choose_endpoint(rng, _ENDPOINT_WEIGHTS)
        if ep in _POST_PATHS:
            status, ms = _timed_request(opener, "POST", base_url + _POST_PATHS[ep],
                                        build_body(ep, rng, place_ids))
        else:
            status, ms = _timed_request(opener, "GET", base_url + _GET_PATHS[ep])
        recorder.add(RequestRecord(time.time(), vu_id, ep, status, ms, 200 <= status < 400))
        if think_time:
            time.sleep(rng.uniform(0, think_time))


def _reporter(recorder, deadline, stop):
    while not stop.is_set() and time.monotonic() < deadline:
        stop.wait(30)
        rows = recorder.snapshot()
        recent = [r for r in rows if r.ts >= time.time() - 30]
        lat = [r.latency_ms for r in recent if r.ok]
        errs = sum(1 for r in recent if not r.ok)
        print(f"[{time.strftime('%H:%M:%S')}] total={len(rows)} "
              f"last30s: n={len(recent)} err={errs} "
              f"p50={percentile(lat, 50)} p95={percentile(lat, 95)} p99={percentile(lat, 99)}",
              flush=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Waypoint Postgres soak load driver")
    ap.add_argument("--users", type=int, default=int(os.environ.get("SOAK_USERS", 25)))
    ap.add_argument("--duration", default=os.environ.get("SOAK_DURATION", "2h"))
    ap.add_argument("--ramp", type=int, default=int(os.environ.get("SOAK_RAMP", 60)))
    ap.add_argument("--think-time", type=float, default=float(os.environ.get("SOAK_THINK", 0.2)))
    ap.add_argument("--base-url", default=os.environ.get("SOAK_BASE_URL", "http://localhost:8000"))
    ap.add_argument("--seed", type=int, default=int(os.environ.get("SOAK_SEED", 1)))
    ap.add_argument("--out", default=os.environ.get("SOAK_OUT", "soak-out"))
    ap.add_argument("--budgets", default=None, help="JSON file of per-endpoint p95 budgets")
    args = ap.parse_args(argv)

    budgets = dict(_DEFAULT_BUDGETS)
    if args.budgets:
        budgets.update(json.load(open(args.budgets)))

    os.makedirs(args.out, exist_ok=True)
    base = args.base_url.rstrip("/")
    duration = parse_duration(args.duration)
    recorder = _Recorder(os.path.join(args.out, "requests.csv"))
    deadline = time.monotonic() + duration
    stop = threading.Event()

    print(f"Soak: {args.users} VUs, ramp {args.ramp}s, duration {duration}s → {base}", flush=True)
    rep = threading.Thread(target=_reporter, args=(recorder, deadline, stop), daemon=True)
    rep.start()
    threads = []
    for i in range(args.users):
        ramp_delay = (args.ramp * i / args.users) if args.users else 0
        t = threading.Thread(target=_run_vu,
                             args=(i, base, deadline, args.think_time, args.seed, recorder, ramp_delay))
        t.start()
        threads.append(t)
    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        print("interrupted — writing summary from data so far", flush=True)
    stop.set()

    summary = summarize(recorder.snapshot(), budgets)
    recorder.close()
    with open(os.path.join(args.out, "summary.json"), "w") as fh:
        json.dump(summary, fh, indent=2)
    print(json.dumps(summary["overall"], indent=2))
    print("drift:", summary["drift"])
    print("budget breaches:", summary["budget_breaches"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Verify arg-parsing/summary path without a server**

Run: `.venv/bin/python -c "from scripts.soak.soak_driver import main; import sys; sys.exit(main(['--users','1','--duration','1s','--ramp','0','--base-url','http://127.0.0.1:1','--out','/tmp/soak-dry']))"`
Expected: exits 0; prints a summary with 0 rows (connection refused → the VU returns after `_seed_places` finds no ids). Confirms wiring/imports without needing a live api. `/tmp/soak-dry/requests.csv` exists with just the header.

- [ ] **Step 3: Lint**

Run: `.venv/bin/ruff check scripts/soak/soak_driver.py`
Expected: no errors. (Fix unused `status`/`_` in `_seed_places` if flagged — assign to `_`.)

- [ ] **Step 4: Commit**

```bash
git add scripts/soak/soak_driver.py
git commit -m "feat(soak): threaded VU runtime, recorder, reporter for the load driver"
```

---

## Task 3: Observer pure transforms

**Files:**
- Create: `scripts/soak/pg_observer.py`
- Test: `tests/test_pg_observer.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_pg_observer.py`:

```python
from scripts.soak import pg_observer as ob


def test_parse_csv_handles_quoted_query_text():
    # psql --csv quotes fields with commas/newlines; the query column often has both.
    raw = 'SELECT a,\n b,10,1.5\n"UPDATE t SET x = 1, y = 2",4,2.0\n'
    rows = ob.parse_psql_csv(raw, ["query", "calls", "mean_ms"])
    assert rows[0]["query"] == "SELECT a,\n b"
    assert rows[1]["query"] == "UPDATE t SET x = 1, y = 2"
    assert rows[1]["calls"] == "4"


def test_activity_metrics():
    rows = [
        {"state": "active", "wait_event_type": "", "query_age": "2.0", "state_age": "2.0"},
        {"state": "active", "wait_event_type": "Lock", "query_age": "9.0", "state_age": "9.0"},
        {"state": "idle", "wait_event_type": "", "query_age": "", "state_age": "30.0"},
        {"state": "idle in transaction", "wait_event_type": "", "query_age": "", "state_age": "45.0"},
    ]
    m = ob.activity_metrics(rows)
    assert m["total"] == 4
    assert m["active"] == 2
    assert m["idle"] == 1
    assert m["idle_in_transaction"] == 1
    assert m["waiting"] == 1
    assert m["longest_query_age_s"] == 9.0
    assert m["longest_idle_in_txn_s"] == 45.0


def test_database_metrics_cache_hit_ratio():
    row = {"numbackends": "5", "xact_commit": "100", "xact_rollback": "2",
           "blks_read": "10", "blks_hit": "990", "deadlocks": "0",
           "temp_files": "0", "temp_bytes": "0"}
    m = ob.database_metrics(row)
    assert m["cache_hit_ratio"] == 0.99
    assert m["deadlocks"] == 0


def test_database_metrics_zero_blocks_is_safe():
    row = {"numbackends": "1", "xact_commit": "0", "xact_rollback": "0",
           "blks_read": "0", "blks_hit": "0", "deadlocks": "0",
           "temp_files": "0", "temp_bytes": "0"}
    assert ob.database_metrics(row)["cache_hit_ratio"] is None


def test_lock_metrics():
    rows = [
        {"mode": "AccessShareLock", "granted": "t"},
        {"mode": "AccessShareLock", "granted": "t"},
        {"mode": "ExclusiveLock", "granted": "f"},
    ]
    m = ob.lock_metrics(rows)
    assert m["total"] == 3
    assert m["not_granted"] == 1
    assert m["by_mode"]["AccessShareLock"] == 2


def test_statements_diff_flags_growth():
    start = [{"queryid": "1", "calls": "10", "mean_exec_time": "5.0", "max_exec_time": "8.0"}]
    end = [{"queryid": "1", "calls": "110", "mean_exec_time": "20.0", "max_exec_time": "40.0",
            "query": "SELECT ..."}]
    diff = ob.statements_diff(start, end)
    assert diff[0]["mean_ms_start"] == 5.0
    assert diff[0]["mean_ms_end"] == 20.0
    assert diff[0]["mean_ratio"] == 4.0
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `.venv/bin/python -m pytest tests/test_pg_observer.py -q`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the pure transforms**

Create `scripts/soak/pg_observer.py` (pure core; runtime in Task 4):

```python
#!/usr/bin/env python3
"""Postgres observer for Waypoint's soak test (H2).

Samples pg_stat_activity / pg_stat_database / pg_locks on an interval and diffs
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


def database_metrics(row: dict) -> dict:
    blks_read, blks_hit = _f(row["blks_read"]), _f(row["blks_hit"])
    total = blks_read + blks_hit
    return {
        "numbackends": int(_f(row["numbackends"])),
        "xact_commit": int(_f(row["xact_commit"])),
        "xact_rollback": int(_f(row["xact_rollback"])),
        "cache_hit_ratio": round(blks_hit / total, 4) if total else None,
        "deadlocks": int(_f(row["deadlocks"])),
        "temp_files": int(_f(row["temp_files"])),
        "temp_bytes": int(_f(row["temp_bytes"])),
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
    """Match statements by queryid; report mean-time growth over the run."""
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
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `.venv/bin/python -m pytest tests/test_pg_observer.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/soak/pg_observer.py tests/test_pg_observer.py
git commit -m "feat(soak): pg observer pure transforms (activity/db/locks/statements)"
```

---

## Task 4: Observer runtime

**Files:**
- Modify: `scripts/soak/pg_observer.py` (append runtime)

- [ ] **Step 1: Append the runtime**

Append to `scripts/soak/pg_observer.py`:

```python
import argparse
import json
import os
import shlex
import subprocess
import sys
import time

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

_LOCK_SQL = "SELECT mode, granted FROM pg_locks"
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Waypoint Postgres soak observer")
    ap.add_argument("--interval", type=float, default=float(os.environ.get("SOAK_PG_INTERVAL", 15)))
    ap.add_argument("--duration", default=os.environ.get("SOAK_DURATION", "2h"))
    ap.add_argument("--out", default=os.environ.get("SOAK_OUT", "soak-out"))
    ap.add_argument("--psql-cmd", default=os.environ.get("SOAK_PSQL_CMD", _DEFAULT_PSQL))
    args = ap.parse_args(argv)

    os.makedirs(args.out, exist_ok=True)
    psql = _Psql(args.psql_cmd)
    _bootstrap(psql)
    sizes_start = {r["relname"]: int(_f(r["bytes"])) for r in psql.query(_SIZE_SQL, _SIZE_COLS)}

    from scripts.soak.soak_driver import parse_duration  # shared parser
    deadline = time.monotonic() + parse_duration(args.duration)

    stats_path = os.path.join(args.out, "pg_stats.csv")
    with open(stats_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["ts", "conn_total", "active", "idle", "idle_in_txn", "waiting",
                         "longest_query_s", "longest_idle_txn_s", "cache_hit_ratio",
                         "deadlocks", "temp_bytes", "locks_total", "locks_not_granted"])
        while time.monotonic() < deadline:
            try:
                act = activity_metrics(psql.query(_ACTIVITY_SQL, _ACTIVITY_COLS))
                dbrows = psql.query(_DB_SQL, _DB_COLS)
                db = database_metrics(dbrows[0]) if dbrows else {}
                lk = lock_metrics(psql.query(_LOCK_SQL, _LOCK_COLS))
            except (RuntimeError, subprocess.TimeoutExpired) as exc:
                print(f"[observer] sample failed: {exc}", flush=True)
                time.sleep(args.interval)
                continue
            writer.writerow([f"{time.time():.0f}", act["total"], act["active"], act["idle"],
                             act["idle_in_transaction"], act["waiting"],
                             f"{act['longest_query_age_s']:.1f}", f"{act['longest_idle_in_txn_s']:.1f}",
                             db.get("cache_hit_ratio"), db.get("deadlocks"), db.get("temp_bytes"),
                             lk["total"], lk["not_granted"]])
            fh.flush()
            print(f"[{time.strftime('%H:%M:%S')}] conns={act['total']} active={act['active']} "
                  f"idle_txn={act['idle_in_transaction']} wait={act['waiting']} "
                  f"cache={db.get('cache_hit_ratio')} deadlocks={db.get('deadlocks')} "
                  f"not_granted={lk['not_granted']}", flush=True)
            time.sleep(args.interval)

    stmts = statements_diff([], psql.query(_STMT_SQL, _STMT_COLS))
    sizes_end = {r["relname"]: int(_f(r["bytes"])) for r in psql.query(_SIZE_SQL, _SIZE_COLS)}
    size_delta = {k: sizes_end.get(k, 0) - sizes_start.get(k, 0) for k in sizes_end}
    summary = {"top_statements": stmts[:20], "table_size_delta_bytes": size_delta}
    with open(os.path.join(args.out, "pg_summary.json"), "w") as fh:
        json.dump(summary, fh, indent=2)
    print("top statement (by mean end):", stmts[0] if stmts else "none")
    print("table size deltas:", size_delta)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Note: the end-of-run `statements_diff([], ...)` passes an empty start set because `_bootstrap` already reset the counters at run start, so end values *are* the per-run deltas; `mean_ratio` will be `None` (no start baseline) and ranking is by `mean_ms_end`. This keeps one code path and still surfaces the slowest queries for the run.

- [ ] **Step 2: Lint + import check**

Run: `.venv/bin/ruff check scripts/soak/pg_observer.py && .venv/bin/python -c "from scripts.soak import pg_observer; print('ok')"`
Expected: no lint errors; prints `ok`.

- [ ] **Step 3: Commit**

```bash
git add scripts/soak/pg_observer.py
git commit -m "feat(soak): pg observer sampling runtime (psql-over-docker, csv output)"
```

---

## Task 5: Enable pg_stat_statements in compose

**Files:**
- Modify: `docker-compose.yml` (the `db` service)
- Test: `tests/test_soak_docs.py`

- [ ] **Step 1: Write the failing consistency test**

Create `tests/test_soak_docs.py`:

```python
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def test_compose_enables_pg_stat_statements():
    compose = (_ROOT / "docker-compose.yml").read_text()
    assert "shared_preload_libraries=pg_stat_statements" in compose


def test_runbook_documents_prereqs_and_commands():
    doc = (_ROOT / "docs" / "soak-testing.md").read_text()
    for needle in ("pg_stat_statements", "--force-recreate db",
                   "soak_driver.py", "pg_observer.py", "make soak-load", "make soak-observe"):
        assert needle in doc, f"runbook missing: {needle}"
```

- [ ] **Step 2: Run, verify failure**

Run: `.venv/bin/python -m pytest tests/test_soak_docs.py -q`
Expected: FAIL (compose lacks the setting; runbook not created yet).

- [ ] **Step 3: Edit `docker-compose.yml`**

In the `db` service, after `image: postgres:16` and before `environment:`, add:

```yaml
    command:
      - "postgres"
      - "-c"
      - "shared_preload_libraries=pg_stat_statements"
      - "-c"
      - "pg_stat_statements.track=all"
```

- [ ] **Step 4: Verify compose still parses**

Run: `docker compose config >/dev/null && echo COMPOSE_OK` (skip if Docker unavailable in dev; the test in Step 1 covers the string).
Expected: `COMPOSE_OK` (or skip). The first test now passes; the runbook test still fails until Task 6.

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml tests/test_soak_docs.py
git commit -m "feat(soak): enable pg_stat_statements on the db service"
```

---

## Task 6: Runbook + Makefile targets

**Files:**
- Create: `docs/soak-testing.md`
- Modify: `Makefile`

- [ ] **Step 1: Write the runbook**

Create `docs/soak-testing.md` covering, in order:
1. **What this is** — the H2 soak; stability + latency validation against real Postgres on the ThinkPad.
2. **Prereqs** — deploy up via `scripts/start-waypoint.ps1`; crime/calls/arrests data ingested; **one-time** `docker compose --env-file .env.deploy up -d --force-recreate db` to load `pg_stat_statements`; Python 3 on the host; run both commands from the repo root.
3. **First-run recipe** — the concrete starting point:
   ```
   # terminal 1 (observer):
   make soak-observe OUT=soak-out DURATION=2h
   # terminal 2 (load):
   make soak-load USERS=25 DURATION=2h OUT=soak-out
   ```
   "Start at 25 VUs / 2h. If clean, raise `USERS` (50, 100) on the next run."
4. **Outputs** — `soak-out/requests.csv`, `summary.json`, `pg_stats.csv`, `pg_summary.json`.
5. **What to watch** — the threshold table from the spec (connections plateau vs creep → pool leak; idle-in-transaction sustained → uncommitted session; latency drift >~1.3× → plan/bloat/cache; not-granted locks > 0 → contention; cache hit ratio falling → working set > shared_buffers; temp_bytes climbing → disk spill; deadlocks > 0 → bug; pg_stat_statements slow query; hot-table size growth).
6. **Pass criteria** — survives full duration; error-rate ≈ 0; no connection/idle-in-txn creep; drift within budget; no deadlocks/contention.

Include the literal strings the test checks: `pg_stat_statements`, `--force-recreate db`, `soak_driver.py`, `pg_observer.py`, `make soak-load`, `make soak-observe`.

- [ ] **Step 2: Add Makefile targets**

Add `soak-load soak-observe` to the `.PHONY` line, and at the end of the Makefile:

```makefile
soak-load:
	.venv/bin/python scripts/soak/soak_driver.py --users $${USERS:-25} --duration $${DURATION:-2h} --out $${OUT:-soak-out}

soak-observe:
	.venv/bin/python scripts/soak/pg_observer.py --interval $${INTERVAL:-15} --duration $${DURATION:-2h} --out $${OUT:-soak-out}
```

- [ ] **Step 3: Run the docs test, verify pass**

Run: `.venv/bin/python -m pytest tests/test_soak_docs.py -q`
Expected: PASS (2 tests).

- [ ] **Step 4: Commit**

```bash
git add docs/soak-testing.md Makefile
git commit -m "docs(soak): runbook + make soak-load/soak-observe targets"
```

---

## Task 7: Tick the roadmap + full verification

**Files:**
- Modify: `docs/ROADMAP.md`

- [ ] **Step 1: Update the H2 entry**

Find the H2 line in `docs/ROADMAP.md` (grep `H2`) and mark it done, pointing at the harness — e.g. append: `— soak harness shipped: scripts/soak/ (driver + pg observer), docs/soak-testing.md; run on the ThinkPad.` Match the file's existing check/format style (`- [x]` or the table cell convention used there).

- [ ] **Step 2: Run the full verification gate**

Run: `make test-all`
Expected: pytest green (≈ 500 tests incl. the 14 new), ruff clean, frontend tests pass, build succeeds. Fix anything red before proceeding.

- [ ] **Step 3: Commit**

```bash
git add docs/ROADMAP.md
git commit -m "docs(soak): tick H2 (long-run Postgres validation) in the roadmap"
```

---

## Self-review notes

- **Spec coverage:** load driver (Tasks 1–2), pg observer (Tasks 3–4), pg_stat_statements enablement (Task 5), runbook incl. first-run recipe + threshold table + pass criteria (Task 6), make targets + unit tests (Tasks 1/3/5/6), ROADMAP tick (Task 7). All spec sections mapped.
- **Contract safety:** `build_body` is validated against the real `Dashboard*Request` Pydantic models (Task 1) so the driver can't silently drift from the API.
- **Type consistency:** `RequestRecord` fields (`ts, vu, endpoint, status, latency_ms, ok`) are used identically in the recorder, reporter, and `summarize`. Observer column lists match each SQL's SELECT order. `parse_duration` is defined in `soak_driver` and imported by the observer (single source).
- **No live-DB in CI:** every DB/subprocess/HTTP path is behind a thin shim; only pure functions are tested, keeping `make test-all` SQLite-only and green.
