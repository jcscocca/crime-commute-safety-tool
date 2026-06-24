from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import get_sessionmaker
from app.main import create_app
from app.models import CrimeIncident
from app.schemas import CrimeIncidentData
from app.services.crime_ingestion_service import ingest_crime_incidents


def test_ingest_crime_incidents_upserts_by_external_id(tmp_path):
    create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'mca.sqlite3'}")
    session = get_sessionmaker()()
    incidents = [
        CrimeIncidentData(
            external_incident_id="spd-1",
            offense_start_utc=datetime(2024, 1, 10, tzinfo=UTC),
            offense_category="PROPERTY",
            latitude=47.609,
            longitude=-122.333,
        ),
        CrimeIncidentData(
            external_incident_id="spd-1",
            offense_start_utc=datetime(2024, 1, 10, tzinfo=UTC),
            offense_category="PROPERTY",
            latitude=47.609,
            longitude=-122.333,
        ),
    ]

    result = ingest_crime_incidents(session, incidents)

    assert result == {"inserted_count": 1, "skipped_count": 1}
    session.close()


def test_ingest_crime_incidents_skips_missing_external_incident_ids(tmp_path):
    create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'mca.sqlite3'}")
    session = get_sessionmaker()()
    incidents = [
        CrimeIncidentData(
            external_incident_id=None,
            offense_start_utc=datetime(2024, 1, 10, tzinfo=UTC),
            offense_category="PROPERTY",
            latitude=47.609,
            longitude=-122.333,
        ),
        CrimeIncidentData(
            external_incident_id=None,
            offense_start_utc=datetime(2024, 1, 10, tzinfo=UTC),
            offense_category="PROPERTY",
            latitude=47.609,
            longitude=-122.333,
        ),
        CrimeIncidentData(
            external_incident_id="spd-keep",
            offense_start_utc=datetime(2024, 1, 11, tzinfo=UTC),
            offense_category="PERSON",
            latitude=47.61,
            longitude=-122.34,
        ),
    ]

    result = ingest_crime_incidents(session, incidents)

    assert result == {"inserted_count": 1, "skipped_count": 2}
    rows = session.scalars(select(CrimeIncident)).all()
    assert [row.external_incident_id for row in rows] == ["spd-keep"]
    session.close()


def test_ingest_crime_incidents_skips_insert_conflicts_without_rolling_back_new_rows(
    tmp_path,
    monkeypatch,
):
    create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'mca.sqlite3'}")
    sessionmaker = get_sessionmaker()
    seed_session = sessionmaker()
    seed_session.add(
        CrimeIncident(
            external_incident_id="spd-race",
            offense_start_utc=datetime(2024, 1, 9, tzinfo=UTC),
            offense_category="PROPERTY",
            latitude=47.608,
            longitude=-122.332,
        )
    )
    seed_session.commit()
    seed_session.close()

    session = sessionmaker()
    monkeypatch.setattr(session, "scalar", lambda statement: None)
    incidents = [
        CrimeIncidentData(
            external_incident_id="spd-race",
            offense_start_utc=datetime(2024, 1, 10, tzinfo=UTC),
            offense_category="PROPERTY",
            latitude=47.609,
            longitude=-122.333,
        ),
        CrimeIncidentData(
            external_incident_id="spd-new",
            offense_start_utc=datetime(2024, 1, 11, tzinfo=UTC),
            offense_category="PERSON",
            latitude=47.61,
            longitude=-122.34,
        ),
    ]

    result = ingest_crime_incidents(session, incidents)

    assert result == {"inserted_count": 1, "skipped_count": 1}
    session.close()

    verify_session = sessionmaker()
    external_ids = verify_session.scalars(
        select(CrimeIncident.external_incident_id).order_by(CrimeIncident.external_incident_id)
    ).all()
    assert external_ids == ["spd-new", "spd-race"]
    verify_session.close()


def test_admin_socrata_ingest_requires_configured_matching_token(tmp_path, monkeypatch):
    monkeypatch.delenv("MCA_ADMIN_INGEST_TOKEN", raising=False)
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'mca.sqlite3'}")
    client = TestClient(app)

    no_token_response = client.post("/admin/crime/ingest/socrata")

    assert no_token_response.status_code == 403
    assert no_token_response.json()["detail"] == "Admin token required"

    monkeypatch.setenv("MCA_ADMIN_INGEST_TOKEN", "secret-token")
    mismatch_response = client.post(
        "/admin/crime/ingest/socrata",
        headers={"X-Admin-Token": "wrong-token"},
    )

    assert mismatch_response.status_code == 403
    assert mismatch_response.json()["detail"] == "Admin token required"


def test_admin_socrata_ingest_rejects_negative_limit_without_fetching(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("MCA_ADMIN_INGEST_TOKEN", "secret-token")

    def fail_fetch_page(self, limit: int, offset: int) -> list[CrimeIncidentData]:
        raise AssertionError("fetch_page should not be called for invalid pagination")

    monkeypatch.setattr(
        "app.api.routes_admin_crime.SeattleSocrataClient.fetch_page",
        fail_fetch_page,
    )
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'mca.sqlite3'}")
    client = TestClient(app)

    response = client.post(
        "/admin/crime/ingest/socrata?limit=-1&offset=0",
        headers={"X-Admin-Token": "secret-token"},
    )

    assert response.status_code == 422


def test_admin_socrata_ingest_rejects_negative_offset_without_fetching(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("MCA_ADMIN_INGEST_TOKEN", "secret-token")

    def fail_fetch_page(self, limit: int, offset: int) -> list[CrimeIncidentData]:
        raise AssertionError("fetch_page should not be called for invalid pagination")

    monkeypatch.setattr(
        "app.api.routes_admin_crime.SeattleSocrataClient.fetch_page",
        fail_fetch_page,
    )
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'mca.sqlite3'}")
    client = TestClient(app)

    response = client.post(
        "/admin/crime/ingest/socrata?limit=25&offset=-1",
        headers={"X-Admin-Token": "secret-token"},
    )

    assert response.status_code == 422


def test_admin_socrata_ingest_fetches_page_and_returns_ingestion_result(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("MCA_ADMIN_INGEST_TOKEN", "secret-token")
    calls = []

    def fake_fetch_page(self, limit: int, offset: int) -> list[CrimeIncidentData]:
        calls.append(
            {
                "base_url": self.base_url,
                "dataset_id": self.dataset_id,
                "app_token": self.app_token,
                "limit": limit,
                "offset": offset,
            }
        )
        return [
            CrimeIncidentData(
                external_incident_id="spd-2",
                offense_start_utc=datetime(2024, 1, 11, tzinfo=UTC),
                offense_category="PERSON",
                latitude=47.61,
                longitude=-122.34,
            )
        ]

    monkeypatch.setattr(
        "app.api.routes_admin_crime.SeattleSocrataClient.fetch_page",
        fake_fetch_page,
    )
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'mca.sqlite3'}")
    client = TestClient(app)

    response = client.post(
        "/admin/crime/ingest/socrata?limit=25&offset=50",
        headers={"X-Admin-Token": "secret-token"},
    )

    assert response.status_code == 200
    assert response.json() == {"inserted_count": 1, "skipped_count": 0}
    assert calls == [
        {
            "base_url": "https://data.seattle.gov/resource",
            "dataset_id": "tazs-3rd5",
            "app_token": None,
            "limit": 25,
            "offset": 50,
        }
    ]
