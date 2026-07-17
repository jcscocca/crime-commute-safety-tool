from datetime import UTC, date, datetime

import pytest

from app.db import get_sessionmaker
from app.main import create_app
from app.models import CrimeIncident
from app.services.trends_service import (
    reset_trends_cache,
    trends_for_mcpp,
    window_bounds,
)

TODAY = date(2026, 7, 16)


@pytest.fixture
def seeded_session(tmp_path):
    create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'trends.sqlite3'}")
    session = get_sessionmaker()()
    session.add_all(
        [
            # TEST HILL (beat M3): two PROPERTY rows in 2026-01, one PERSON row in 2026-03.
            CrimeIncident(
                id="a1", offense_start_utc=datetime(2026, 1, 5, tzinfo=UTC),
                offense_category="PROPERTY", beat="M3", mcpp="TEST HILL",
                latitude=47.60945, longitude=-122.33595,
            ),
            CrimeIncident(
                id="a2", offense_start_utc=datetime(2026, 1, 20, tzinfo=UTC),
                offense_category="PROPERTY", beat="M3", mcpp="TEST HILL",
                latitude=47.60945, longitude=-122.33595,
            ),
            CrimeIncident(
                id="a3", offense_start_utc=datetime(2026, 3, 9, tzinfo=UTC),
                offense_category="PERSON", beat="M3", mcpp="TEST HILL",
                latitude=47.60945, longitude=-122.33595,
            ),
            # Other beat/mcpp in 2026-02 — counts citywide but not toward TEST HILL.
            CrimeIncident(
                id="c1", offense_start_utc=datetime(2026, 2, 14, tzinfo=UTC),
                offense_category="PROPERTY", beat="K1", mcpp="DOWNTOWN COMMERCIAL",
                latitude=47.61, longitude=-122.33,
            ),
        ]
    )
    session.commit()
    yield session
    session.close()


def test_window_bounds_reported_is_60_complete_months():
    start, end = window_bounds("reported", TODAY)
    assert end == date(2026, 6, 30)          # last complete month
    assert start == date(2021, 7, 1)          # 60 months inclusive


def test_window_bounds_calls_clamped_to_rolling_floor():
    start, end = window_bounds("calls", TODAY)
    assert end == date(2026, 6, 30)
    assert start == date(2024, 7, 1)          # calls_data_floor(TODAY)


def test_series_are_zero_filled_and_aligned(seeded_session):
    payload = trends_for_mcpp(
        seeded_session, mcpp="TEST HILL", layer="reported",
        offense_category=None, today=TODAY,
    )
    months = payload["months"]
    assert len(months) == 60 == len(payload["area_counts"]) == len(payload["citywide_counts"])
    assert months[0] == "2021-07" and months[-1] == "2026-06"
    by_month = dict(zip(months, payload["area_counts"], strict=True))
    assert by_month["2026-01"] == 2
    assert by_month["2026-02"] == 0            # zero-filled, not missing
    assert by_month["2026-03"] == 1
    city = dict(zip(months, payload["citywide_counts"], strict=True))
    assert city["2026-02"] == 1                # other-beat incident counts citywide
    assert payload["mcpp"] == "TEST HILL" and payload["mcpp_label"] == "Test Hill"


def test_category_filter_applies(seeded_session):
    payload = trends_for_mcpp(
        seeded_session, mcpp="TEST HILL", layer="reported",
        offense_category="PROPERTY", today=TODAY,
    )
    assert sum(payload["area_counts"]) == 2  # the two PROPERTY-seeded TEST HILL rows


def test_citywide_series_is_shared_across_mcpps(seeded_session, monkeypatch):
    import app.services.trends_service as trends_service

    calls: list[object] = []
    real = trends_service.area_month_counts

    def counting(session, column, *args, **kwargs):
        calls.append(column)
        return real(session, column, *args, **kwargs)

    monkeypatch.setattr(trends_service, "area_month_counts", counting)
    first = trends_for_mcpp(
        seeded_session, mcpp="TEST HILL", layer="reported",
        offense_category=None, today=TODAY,
    )
    second = trends_for_mcpp(
        seeded_session, mcpp="DOWNTOWN COMMERCIAL", layer="reported",
        offense_category=None, today=TODAY,
    )
    assert second["citywide_counts"] is first["citywide_counts"]
    assert calls.count(CrimeIncident.mcpp) == 2   # one area query per MCPP
    assert calls.count(CrimeIncident.beat) == 1   # citywide computed once, then shared


def test_cache_hit_and_reset(seeded_session):
    clock = iter([0.0, 1.0, 2.0, 5000.0]).__next__
    first = trends_for_mcpp(seeded_session, mcpp="TEST HILL", layer="reported",
                            offense_category=None, today=TODAY, now=clock)
    second = trends_for_mcpp(seeded_session, mcpp="TEST HILL", layer="reported",
                             offense_category=None, today=TODAY, now=clock)
    assert second is first                     # served from cache
    reset_trends_cache()
