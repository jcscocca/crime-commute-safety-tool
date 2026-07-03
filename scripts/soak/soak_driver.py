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
