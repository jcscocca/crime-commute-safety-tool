from datetime import UTC, date, datetime

from app.analysis.exposure import (
    analysis_days,
    count_incidents_in_place_buffer,
    place_exposure_square_km_days,
    trim_partial_edge_months,
)
from app.analysis.rate_tests import dispersion_status
from app.schemas import CrimeIncidentData


def test_analysis_days_is_inclusive():
    assert analysis_days(date(2024, 1, 1), date(2024, 1, 30)) == 30


def test_trim_keeps_full_month_boundary_windows_unchanged():
    # Jan 1 → Jun 30: both edges are full calendar months, so nothing is trimmed.
    counts = [10, 8, 12, 9, 11, 7]
    assert trim_partial_edge_months(counts, date(2026, 1, 1), date(2026, 6, 30)) == counts


def test_trim_drops_a_partial_trailing_month():
    # Jan 1 → Jul 5 (the default "since Jan 1" shape): the short July bin is dropped.
    counts = [10, 8, 12, 9, 11, 7, 1]  # 7 bins Jan..Jul
    trimmed = trim_partial_edge_months(counts, date(2026, 1, 1), date(2026, 7, 5))
    assert trimmed == [10, 8, 12, 9, 11, 7]


def test_trim_drops_a_partial_leading_month():
    counts = [2, 8, 12, 9, 11, 7]  # Jan..Jun, window starts Jan 15
    trimmed = trim_partial_edge_months(counts, date(2026, 1, 15), date(2026, 6, 30))
    assert trimmed == [8, 12, 9, 11, 7]


def test_trim_keeps_all_bins_when_trimming_would_leave_fewer_than_two():
    # Jan 15 → Mar 5: both edges partial; dropping both would leave one bin, so keep all three.
    counts = [3, 9, 1]
    assert trim_partial_edge_months(counts, date(2026, 1, 15), date(2026, 3, 5)) == counts
    # A single-bin series is returned untouched.
    assert trim_partial_edge_months([5], date(2026, 1, 15), date(2026, 1, 20)) == [5]


def test_trim_lowers_dispersion_inflated_by_a_partial_trailing_month():
    # A steady process (all full months ~10) with a depressed partial trailing month (1) reads
    # as more dispersed if the short bin is kept, but matches the clean series once it's trimmed.
    full = [10, 10, 10, 10, 10, 10]
    with_partial = full + [1]
    inflated = dispersion_status(with_partial)
    corrected = dispersion_status(
        trim_partial_edge_months(with_partial, date(2026, 1, 1), date(2026, 7, 5))
    )
    assert inflated.phi > corrected.phi
    assert corrected.phi == dispersion_status(full).phi  # trimmed == the full-month series


def test_place_exposure_uses_buffer_area_times_days():
    exposure = place_exposure_square_km_days(
        radius_m=500,
        analysis_start_date=date(2024, 1, 1),
        analysis_end_date=date(2024, 1, 30),
    )

    assert round(exposure, 3) == 23.562


def test_count_incidents_in_place_buffer_uses_haversine_distance():
    incidents = [
        CrimeIncidentData(
            id="near",
            offense_start_utc=datetime(2024, 1, 15, tzinfo=UTC),
            offense_category="PROPERTY",
            latitude=47.6117,
            longitude=-122.3371,
        ),
        CrimeIncidentData(
            id="far",
            offense_start_utc=datetime(2024, 1, 15, tzinfo=UTC),
            offense_category="PROPERTY",
            latitude=47.7000,
            longitude=-122.4000,
        ),
    ]

    result = count_incidents_in_place_buffer(
        incidents=incidents,
        latitude=47.6116,
        longitude=-122.3372,
        radius_m=250,
        analysis_start_date=date(2024, 1, 1),
        analysis_end_date=date(2024, 1, 31),
        offense_category="PROPERTY",
        offense_subcategory=None,
        nibrs_group=None,
    )

    assert [incident.id for incident in result] == ["near"]
