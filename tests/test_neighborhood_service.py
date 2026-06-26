from datetime import date

from app.services.neighborhood_service import neighborhood_analysis_for_places
from tests.helpers_dashboard import session_with_places_and_beat_crime


def test_known_beat_returns_place_and_beat_rates(tmp_path):
    session, user_hash, place_id = session_with_places_and_beat_crime(tmp_path)
    result = neighborhood_analysis_for_places(
        session=session,
        user_id_hash=user_hash,
        place_ids=[place_id],
        radius_m=250,
        analysis_start_date=date(2026, 1, 1),
        analysis_end_date=date(2026, 6, 30),
        offense_category=None,
        offense_subcategory=None,
        nibrs_group=None,
        area_lookup={"M2": 3.0},
    )
    place = result["places"][0]
    assert place["beat"] == "M2"
    assert place["baseline_available"] is True
    assert place["place_rate"] > 0 and place["beat_rate"] > 0


def test_unknown_beat_marks_baseline_unavailable(tmp_path):
    session, user_hash, place_id = session_with_places_and_beat_crime(tmp_path)
    result = neighborhood_analysis_for_places(
        session=session,
        user_id_hash=user_hash,
        place_ids=[place_id],
        radius_m=250,
        analysis_start_date=date(2026, 1, 1),
        analysis_end_date=date(2026, 6, 30),
        offense_category=None,
        offense_subcategory=None,
        nibrs_group=None,
        area_lookup={},
    )
    assert result["places"][0]["baseline_available"] is False


def test_short_range_returns_insufficient_data(tmp_path):
    session, user_hash, place_id = session_with_places_and_beat_crime(tmp_path)
    result = neighborhood_analysis_for_places(
        session=session,
        user_id_hash=user_hash,
        place_ids=[place_id],
        radius_m=250,
        analysis_start_date=date(2026, 6, 1),
        analysis_end_date=date(2026, 6, 10),
        offense_category=None,
        offense_subcategory=None,
        nibrs_group=None,
        area_lookup={"M2": 3.0},
    )
    assert result["places"][0]["decision"] == "insufficient_data"
