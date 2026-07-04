from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.routes_public_dashboard import get_geocode_provider
from app.geocoding.providers import GeocodeHit, GeocoderUpstreamError
from app.main import create_app


class FakeProvider:
    def __init__(self, hits, *, error=None):
        self.hits = hits
        self.error = error

    def search(self, query):
        if self.error is not None:
            raise self.error
        return list(self.hits)


@pytest.fixture()
def app_and_client(tmp_path, monkeypatch):
    monkeypatch.setenv("MCA_GEOCODER_MIN_INTERVAL_S", "0")
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'geo.sqlite3'}")
    client = TestClient(app)
    return app, client


def test_geocode_requires_public_session(app_and_client):
    _, client = app_and_client
    response = client.get("/dashboard/geocode", params={"q": "pike place"})
    assert response.status_code == 401


def test_geocode_returns_results(app_and_client):
    app, client = app_and_client
    client.post("/sessions")
    hit = GeocodeHit(
        label="Pike Place Market", latitude=47.6097, longitude=-122.3331, source="nominatim"
    )
    app.dependency_overrides[get_geocode_provider] = lambda: FakeProvider([hit])
    try:
        response = client.get("/dashboard/geocode", params={"q": "pike place"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == [
        {"label": "Pike Place Market", "latitude": 47.6097, "longitude": -122.3331, "source": "nominatim"}  # noqa: E501
    ]


def test_geocode_empty_query_returns_empty_list(app_and_client):
    app, client = app_and_client
    client.post("/sessions")
    app.dependency_overrides[get_geocode_provider] = lambda: FakeProvider([])
    try:
        response = client.get("/dashboard/geocode", params={"q": "   "})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == []


def test_geocode_rejects_overlong_query(app_and_client):
    # A multi-KB q must be rejected before it reaches the upstream geocoder (cache-bypass abuse).
    app, client = app_and_client
    client.post("/sessions")
    app.dependency_overrides[get_geocode_provider] = lambda: FakeProvider([])
    try:
        response = client.get("/dashboard/geocode", params={"q": "a" * 201})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_geocode_upstream_error_returns_502(app_and_client):
    app, client = app_and_client
    client.post("/sessions")
    app.dependency_overrides[get_geocode_provider] = lambda: FakeProvider(
        [], error=GeocoderUpstreamError("down")
    )
    try:
        response = client.get("/dashboard/geocode", params={"q": "pike place"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 502
