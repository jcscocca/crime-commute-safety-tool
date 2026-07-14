#!/usr/bin/env python3
"""Sustained-load driver for CompCat's Postgres soak test (H2).

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
    # Compare the first vs last window's p95. Cap at 1h for long runs; for shorter runs use
    # each half so the windows stay disjoint (a fixed 1h window would overlap and report a
    # false ~1.0 drift, hiding real growth). Skip if the run is too short to split.
    span = t_end - t0
    window = min(3600.0, span / 2)

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
        if window > 0:
            first = [r.latency_ms for r in ep_rows if r.ok and r.ts <= t0 + window]
            last = [r.latency_ms for r in ep_rows if r.ok and r.ts >= t_end - window]
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


# --------------------------------------------------------------------------- #
# Runtime (I/O glue over the pure helpers above)
# --------------------------------------------------------------------------- #

import argparse  # noqa: E402
import csv  # noqa: E402
import http.cookiejar  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import sys  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import urllib.error  # noqa: E402
import urllib.request  # noqa: E402

_DEFAULT_BUDGETS: dict[str, float] = {
    "analyze": 400.0, "neighborhood": 800.0, "incidents": 400.0,
    "compare": 600.0, "summary": 300.0, "freshness": 100.0, "export": 500.0,
}


class _Recorder:
    """Thread-safe: append rows to memory + stream to a CSV file handle."""

    def __init__(self, csv_path: str) -> None:
        self._lock = threading.Lock()
        self._closed = False
        self.rows: list[RequestRecord] = []
        self._fh = open(csv_path, "w", newline="")
        self._writer = csv.writer(self._fh)
        self._writer.writerow(["ts", "vu", "endpoint", "status", "latency_ms", "ok"])

    def add(self, rec: RequestRecord) -> None:
        with self._lock:
            if self._closed:  # a VU still finishing after shutdown — drop, don't crash
                return
            self.rows.append(rec)
            self._writer.writerow([f"{rec.ts:.3f}", rec.vu, rec.endpoint, rec.status,
                                   f"{rec.latency_ms:.1f}", int(rec.ok)])
            self._fh.flush()

    def snapshot(self) -> list[RequestRecord]:
        with self._lock:
            return list(self.rows)

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._fh.close()


class _Counter:
    """Thread-safe live-VU counter so the reporter can show actual vs requested load."""

    def __init__(self) -> None:
        self._n = 0
        self._lock = threading.Lock()

    def inc(self) -> None:
        with self._lock:
            self._n += 1

    def dec(self) -> None:
        with self._lock:
            self._n -= 1

    def get(self) -> int:
        with self._lock:
            return self._n


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
        _timed_request(opener, "POST", base_url + "/places", {
            "display_label": f"Soak {label}", "latitude": lat, "longitude": lon, "visit_count": 3,
        })
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


def _run_vu(vu_id, base_url, deadline, think_time, seed, recorder, ramp_delay, stop, counter):
    if stop.wait(ramp_delay):  # interruptible ramp-up
        return
    rng = random.Random(seed + vu_id)
    opener = _new_opener()
    _timed_request(opener, "POST", base_url + "/sessions")
    place_ids: list[str] = []
    for _ in range(3):  # transient slowness during ramp shouldn't silently kill the VU
        place_ids = _seed_places(opener, base_url, rng)
        if place_ids or stop.is_set() or time.monotonic() >= deadline:
            break
        stop.wait(1.0)
    if not place_ids:
        print(f"[vu {vu_id}] could not seed places — dropping out", flush=True)
        return
    counter.inc()
    try:
        while not stop.is_set() and time.monotonic() < deadline:
            ep = choose_endpoint(rng, _ENDPOINT_WEIGHTS)
            if ep in _POST_PATHS:
                status, ms = _timed_request(opener, "POST", base_url + _POST_PATHS[ep],
                                            build_body(ep, rng, place_ids))
            else:
                status, ms = _timed_request(opener, "GET", base_url + _GET_PATHS[ep])
            recorder.add(RequestRecord(time.time(), vu_id, ep, status, ms, 200 <= status < 400))
            if think_time:
                stop.wait(rng.uniform(0, think_time))
    finally:
        counter.dec()


def _reporter(recorder, deadline, stop, counter, requested):
    while not stop.is_set() and time.monotonic() < deadline:
        if stop.wait(30):
            break
        rows = recorder.snapshot()
        recent = [r for r in rows if r.ts >= time.time() - 30]
        lat = [r.latency_ms for r in recent if r.ok]
        errs = sum(1 for r in recent if not r.ok)
        print(f"[{time.strftime('%H:%M:%S')}] vus={counter.get()}/{requested} total={len(rows)} "
              f"last30s: n={len(recent)} err={errs} "
              f"p50={percentile(lat, 50)} p95={percentile(lat, 95)} p99={percentile(lat, 99)}",
              flush=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="CompCat Postgres soak load driver")
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
        with open(args.budgets) as fh:
            budgets.update(json.load(fh))

    os.makedirs(args.out, exist_ok=True)
    base = args.base_url.rstrip("/")
    duration = parse_duration(args.duration)
    recorder = _Recorder(os.path.join(args.out, "requests.csv"))
    deadline = time.monotonic() + duration
    stop = threading.Event()

    counter = _Counter()
    print(f"Soak: {args.users} VUs, ramp {args.ramp}s, duration {duration}s → {base}", flush=True)
    rep = threading.Thread(target=_reporter, args=(recorder, deadline, stop, counter, args.users),
                           daemon=True)
    rep.start()
    threads = []
    for i in range(args.users):
        ramp_delay = (args.ramp * i / args.users) if args.users else 0
        t = threading.Thread(
            target=_run_vu,
            args=(i, base, deadline, args.think_time, args.seed, recorder, ramp_delay,
                  stop, counter),
            daemon=True)
        t.start()
        threads.append(t)
    try:
        while any(t.is_alive() for t in threads):
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("interrupted — stopping VUs, writing partial summary", flush=True)
    stop.set()
    for t in threads:  # let VUs notice `stop` and exit before we close the file
        t.join(timeout=10)

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
