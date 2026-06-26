from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db import get_sessionmaker
from app.main import create_app
from app.models import CrimeIncident, PlaceCluster
from app.sessions import public_user_hash


def session_with_places_and_beat_crime(tmp_path) -> tuple[Session, str, str]:
    """Seed one place plus SPD beat-tagged crime for neighborhood analysis tests.

    Inserts a single ``PlaceCluster`` with display coordinates, several
    ``CrimeIncident`` rows WITHIN 250 m carrying ``beat="M2"`` (so the place's
    modal beat resolves to ``M2``), and additional ``beat="M2"`` rows OUTSIDE the
    250 m buffer (so the beat-wide incident count exceeds the place count). All
    incidents are dated across 2026-01..2026-06 so a full-range analysis has both
    positive place and beat rates while a short sub-range falls below the minimum
    analysis-window length.

    Returns ``(session, user_id_hash, place_id)``.
    """
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'neighborhood.sqlite3'}")
    sessionmaker = get_sessionmaker()

    # Establish a public session so we have a real user hash to scope the place to.
    from fastapi.testclient import TestClient

    client = TestClient(app)
    client.post("/sessions")
    user_hash = public_user_hash(client.cookies.get("mca_session"))
    assert user_hash is not None

    place_id = "neighborhood-place"
    place_lat = 47.6100
    place_lon = -122.3330

    session = sessionmaker()
    session.add(
        PlaceCluster(
            id=place_id,
            user_id_hash=user_hash,
            cluster_version="test",
            cluster_method="manual",
            centroid_latitude=47.5900,
            centroid_longitude=-122.2900,
            display_latitude=place_lat,
            display_longitude=place_lon,
            visit_count=8,
            inferred_place_type="manual_place",
            sensitivity_class="normal",
            display_label="Neighborhood place",
            label_source="test",
        )
    )

    # Incidents WITHIN ~250 m, beat "M2", spread across 2026-01..2026-06.
    # These count toward both the place (radius filter) and the beat (beat query).
    near_offsets = [
        (0.0005, 0.0),
        (0.0008, 0.0003),
        (0.0, 0.0010),
        (0.0012, 0.0),
        (-0.0007, 0.0005),
    ]
    near_months = [1, 2, 3, 4, 5]
    for index, ((dlat, dlon), month) in enumerate(zip(near_offsets, near_months, strict=True)):
        session.add(
            CrimeIncident(
                id=f"near-{index}",
                offense_start_utc=datetime(2026, month, 12, tzinfo=UTC),
                offense_category="PROPERTY",
                offense_subcategory="Theft",
                nibrs_group="PROPERTY",
                beat="M2",
                latitude=place_lat + dlat,
                longitude=place_lon + dlon,
            )
        )

    # Incidents OUTSIDE ~250 m, beat "M2", spread across 2026-01..2026-06. These
    # belong to the beat but not the place buffer, so beat_count > place_count.
    far_offsets = [
        (0.0040, 0.0),
        (0.0, 0.0060),
        (0.0045, 0.0030),
        (-0.0050, 0.0),
        (0.0050, -0.0040),
        (0.0, -0.0065),
        (-0.0048, 0.0035),
        (0.0042, 0.0042),
    ]
    far_months = [1, 2, 3, 4, 5, 6, 1, 3]
    for index, ((dlat, dlon), month) in enumerate(zip(far_offsets, far_months, strict=True)):
        session.add(
            CrimeIncident(
                id=f"far-{index}",
                offense_start_utc=datetime(2026, month, 18, tzinfo=UTC),
                offense_category="PROPERTY",
                offense_subcategory="Burglary",
                nibrs_group="PROPERTY",
                beat="M2",
                latitude=place_lat + dlat,
                longitude=place_lon + dlon,
            )
        )

    session.commit()
    return session, user_hash, place_id
