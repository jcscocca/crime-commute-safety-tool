from __future__ import annotations

import math
from datetime import date

from app.analysis.exposure import analysis_days, point_to_route_distance_m, route_length_km
from app.normalization.geo import haversine_m

SAMPLE_STEP_M = 25.0
IDENTICAL_DIVERGENT_SHARE = 0.02


def densify_polyline(
    points: list[tuple[float, float]],
    step_m: float = SAMPLE_STEP_M,
) -> list[tuple[float, float]]:
    if len(points) < 2:
        return list(points)
    dense: list[tuple[float, float]] = [points[0]]
    for start, end in zip(points, points[1:], strict=False):
        span_m = haversine_m(start[0], start[1], end[0], end[1])
        segment_count = max(1, math.ceil(span_m / step_m))
        for index in range(1, segment_count + 1):
            fraction = index / segment_count
            dense.append(
                (
                    start[0] + (end[0] - start[0]) * fraction,
                    start[1] + (end[1] - start[1]) * fraction,
                )
            )
    return dense


def divergent_length_km(
    self_points: list[tuple[float, float]],
    other_points: list[tuple[float, float]],
    radius_m: int,
    step_m: float = SAMPLE_STEP_M,
) -> float:
    if len(self_points) < 2 or not other_points:
        return 0.0
    samples = densify_polyline(self_points, step_m)
    outside = [
        point_to_route_distance_m(latitude, longitude, other_points) > radius_m
        for latitude, longitude in samples
    ]
    total_m = 0.0
    for index in range(len(samples) - 1):
        # A span counts as divergent only when BOTH endpoints clear the radius — the
        # conservative side of the boundary spans next to the shared region.
        if outside[index] and outside[index + 1]:
            start = samples[index]
            end = samples[index + 1]
            total_m += haversine_m(start[0], start[1], end[0], end[1])
    return total_m / 1000


def divergent_share(
    self_points: list[tuple[float, float]],
    divergent_km: float,
) -> float:
    total_km = route_length_km(self_points)
    if total_km <= 0:
        return 0.0
    return min(1.0, divergent_km / total_km)


def divergent_exposure_square_km_days(
    *,
    length_km: float,
    radius_m: int,
    analysis_start_date: date,
    analysis_end_date: date,
) -> float:
    # No pi*r^2 end-cap term: divergent runs border the shared region, so the caps
    # largely fall inside corridor already covered. Documented in
    # docs/analysis/statistical-route-place-comparison.md.
    radius_km = radius_m / 1000
    return length_km * 2 * radius_km * analysis_days(analysis_start_date, analysis_end_date)
