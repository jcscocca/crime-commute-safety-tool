import sqlite3
from pathlib import Path

import pytest

from app.analysis.beat_baselines import (
    NON_GEOGRAPHIC_BEATS,
    load_beat_areas,
    missing_beat_areas,
)

DEV_DB = Path(__file__).resolve().parent.parent / "localagent-output" / "mobility.sqlite3"


def _write_csv(tmp_path, rows):
    path = tmp_path / "areas.csv"
    path.write_text("beat,area_km2\n" + "".join(f"{b},{a}\n" for b, a in rows), encoding="utf-8")
    return path


def test_load_beat_areas_returns_positive_floats(tmp_path):
    path = _write_csv(tmp_path, [("K3", "3.10"), ("Q3", "2.04")])
    areas = load_beat_areas(path)
    assert areas == {"K3": 3.10, "Q3": 2.04}


def test_load_beat_areas_rejects_nonpositive(tmp_path):
    path = _write_csv(tmp_path, [("K3", "0")])
    with pytest.raises(ValueError):
        load_beat_areas(path)


def test_missing_beat_areas_reports_uncovered():
    areas = {"K3": 3.1}
    assert missing_beat_areas(["K3", "Q3", None, "Q3"], areas) == {"Q3"}


def test_missing_beat_areas_skips_non_geographic_sentinels():
    # "-" (untagged) and "OOJ" (out-of-jurisdiction) are placeholder codes, not real
    # police beats, so they have no polygon and must not be flagged as missing coverage.
    areas = {"K3": 3.1}
    assert missing_beat_areas(["K3", "-", "OOJ"], areas) == set()
    assert {"-", "OOJ"} <= NON_GEOGRAPHIC_BEATS


def test_shipped_csv_loads_and_is_well_formed():
    areas = load_beat_areas()
    assert len(areas) >= 50
    assert all(value > 0 for value in areas.values())
    # Every beat area is a plausible Seattle-scale polygon (downtown beats are sub-km^2;
    # the largest are marine/harbor beats around ~90 km^2), never a degenerate or runaway value.
    assert all(0.1 < value < 150.0 for value in areas.values())
    # K3 is a small dense downtown beat (< 1 km^2); pin it so a wrong endpoint/units regress here.
    assert 0.5 < areas["K3"] < 1.5


@pytest.mark.skipif(not DEV_DB.exists(), reason="dev DB not present")
def test_shipped_csv_covers_every_real_beat_in_dev_db():
    con = sqlite3.connect(DEV_DB)
    try:
        db_beats = [
            row[0]
            for row in con.execute(
                "SELECT DISTINCT beat FROM crime_incidents WHERE beat IS NOT NULL AND beat<>''"
            )
        ]
    finally:
        con.close()
    assert missing_beat_areas(db_beats, load_beat_areas()) == set()
