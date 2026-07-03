from datetime import date

from app.analysis.divergence import (
    SAMPLE_STEP_M,
    densify_polyline,
    divergent_exposure_square_km_days,
    divergent_length_km,
    divergent_share,
)
from app.normalization.geo import haversine_m

VERTICAL_1KM = [(47.600, -122.340), (47.610, -122.340)]
VERTICAL_2KM = [(47.600, -122.340), (47.620, -122.340)]


def test_densify_polyline_keeps_endpoints_and_spacing():
    dense = densify_polyline(VERTICAL_1KM)

    assert dense[0] == VERTICAL_1KM[0]
    assert dense[-1] == VERTICAL_1KM[-1]
    assert len(dense) > 40  # ~1113 m at 25 m steps
    for start, end in zip(dense, dense[1:], strict=False):
        assert haversine_m(start[0], start[1], end[0], end[1]) <= SAMPLE_STEP_M + 0.001


def test_densify_polyline_degenerate_inputs_pass_through():
    assert densify_polyline([]) == []
    assert densify_polyline([(47.6, -122.34)]) == [(47.6, -122.34)]


def test_divergent_length_is_zero_for_identical_polylines():
    assert divergent_length_km(VERTICAL_1KM, VERTICAL_1KM, radius_m=250) == 0.0


def test_divergent_length_is_full_length_for_far_apart_polylines():
    other = [(47.600, -122.300), (47.610, -122.300)]  # ~3 km east

    result = divergent_length_km(VERTICAL_1KM, other, radius_m=250)

    assert abs(result - 1.113) < 0.06


def test_divergent_length_partial_overlap_excludes_shared_stretch():
    # Other covers the northern half of self; southern samples beyond 250 m diverge.
    other = [(47.610, -122.340), (47.620, -122.340)]

    result = divergent_length_km(VERTICAL_2KM, other, radius_m=250)

    # ~1.113 km southern half minus the 250 m radius apron ≈ 0.863 km.
    assert 0.75 < result < 0.95


def test_divergent_length_handles_multiple_divergent_runs():
    # Other covers only the middle; self diverges at both ends (diverge/rejoin/diverge).
    self_points = [(47.600, -122.340), (47.630, -122.340)]
    other = [(47.610, -122.340), (47.620, -122.340)]

    result = divergent_length_km(self_points, other, radius_m=250)

    # Two runs of ~(1.113 - 0.25) km each.
    assert 1.55 < result < 1.9


def test_divergent_length_degenerate_inputs_are_zero():
    assert divergent_length_km([(47.6, -122.34)], VERTICAL_1KM, radius_m=250) == 0.0
    assert divergent_length_km(VERTICAL_1KM, [], radius_m=250) == 0.0


def test_divergent_share_is_ratio_of_route_length():
    assert divergent_share(VERTICAL_1KM, 0.0) == 0.0
    assert abs(divergent_share(VERTICAL_2KM, 1.113) - 0.5) < 0.01
    assert abs(divergent_share(VERTICAL_1KM, 1.113) - 1.0) < 0.01
    assert divergent_share([(47.6, -122.34)], 1.0) == 0.0


def test_divergent_exposure_is_length_times_width_times_days():
    result = divergent_exposure_square_km_days(
        length_km=2.0,
        radius_m=250,
        analysis_start_date=date(2024, 1, 1),
        analysis_end_date=date(2024, 1, 30),
    )

    assert result == 2.0 * 2 * 0.25 * 30
