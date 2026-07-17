"""Monthly trend series for the Analyze 'volume over time' section.

Methodology: docs/analysis/trend-indexing-method.md (§8 implementation contract).
Raw series only — indexing/rolling are computed client-side.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from functools import lru_cache
from time import monotonic

from sqlalchemy.orm import Session

from app.analysis.area_baselines import mcpp_display_label
from app.analysis.beat_baselines import load_beat_areas
from app.crime.seattle_socrata import calls_data_floor, crime_data_floor
from app.crime.sources import LAYER_CALLS, sources_for_layer
from app.models import CrimeIncident
from app.services.neighborhood_service import area_month_counts, months_between

WINDOW_MONTHS = 60
TRENDS_CACHE_TTL_S = 3600.0

_trends_cache: dict[str, object] = {}
_trends_expires: dict[str, float] = {}


def reset_trends_cache() -> None:
    _trends_cache.clear()
    _trends_expires.clear()


@lru_cache(maxsize=1)
def _beat_names() -> tuple[str, ...]:
    return tuple(sorted(load_beat_areas()))


def window_bounds(layer: str, today: date) -> tuple[date, date]:
    end = today.replace(day=1) - timedelta(days=1)          # last complete month
    months_back = WINDOW_MONTHS - 1
    year = end.year - (months_back // 12)
    month = end.month - (months_back % 12)
    if month < 1:
        month += 12
        year -= 1
    start = date(year, month, 1)
    floor = calls_data_floor(today) if layer == LAYER_CALLS else crime_data_floor(today)
    return max(start, floor), end


def _cached_series(
    session: Session,
    key: str,
    column,
    values: tuple[str, ...],
    start: date,
    end: date,
    offense_category: str | None,
    sources: tuple[str, ...],
    month_keys: list[tuple[int, int]],
    now_s: float,
) -> list[int]:
    cached = _trends_cache.get(key)
    if cached is not None and now_s < _trends_expires.get(key, 0.0):
        return cached  # type: ignore[return-value]
    counts = area_month_counts(
        session, column, values, start, end, offense_category, None, None, sources=sources
    )
    series = [counts.get(k, 0) for k in month_keys]
    _trends_cache[key] = series
    _trends_expires[key] = now_s + TRENDS_CACHE_TTL_S
    return series


def trends_for_mcpp(
    session: Session,
    *,
    mcpp: str,
    layer: str,
    offense_category: str | None,
    today: date | None = None,
    now: Callable[[], float] = monotonic,
) -> dict[str, object]:
    sources = sources_for_layer(layer)
    effective_today = today or date.today()
    start, end = window_bounds(layer, effective_today)
    now_s = now()
    key = f"{layer}:{mcpp}:{offense_category or ''}:{start}:{end}"
    cached = _trends_cache.get(key)
    if cached is not None and now_s < _trends_expires.get(key, 0.0):
        return cached  # type: ignore[return-value]

    month_keys = months_between(start, end)
    area = _cached_series(
        session, f"area:{key}", CrimeIncident.mcpp, (mcpp,),
        start, end, offense_category, sources, month_keys, now_s,
    )
    city_key = f"city:{layer}:{offense_category or ''}:{start}:{end}"
    city = _cached_series(
        session, city_key, CrimeIncident.beat, _beat_names(),
        start, end, offense_category, sources, month_keys, now_s,
    )
    value: dict[str, object] = {
        "layer": layer,
        "mcpp": mcpp,
        "mcpp_label": mcpp_display_label(mcpp),
        "category": offense_category,
        "months": [f"{y:04d}-{m:02d}" for y, m in month_keys],
        "area_counts": area,
        "citywide_counts": city,
    }
    _trends_cache[key] = value
    _trends_expires[key] = now_s + TRENDS_CACHE_TTL_S
    return value
