from fastapi.testclient import TestClient

from app.main import create_app


def _client(tmp_path) -> TestClient:
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'mca.sqlite3'}")
    client = TestClient(app)
    client.post("/sessions")
    return client


def test_create_update_list_and_delete_public_place(tmp_path):
    client = _client(tmp_path)

    create_response = client.post(
        "/places",
        json={
            "display_label": "Downtown transfer stop",
            "latitude": 47.609,
            "longitude": -122.333,
            "visit_count": 12,
            "total_dwell_minutes": 360,
            "median_dwell_minutes": 30,
            "typical_days": "weekday",
            "typical_hours": "8-9",
            "sensitivity_class": "normal",
        },
    )

    assert create_response.status_code == 201
    place_id = create_response.json()["id"]
    assert create_response.json()["display_label"] == "Downtown transfer stop"
    assert create_response.json()["latitude"] == 47.609
    assert create_response.json()["longitude"] == -122.333

    update_response = client.patch(
        f"/places/{place_id}",
        json={"visit_count": 20, "display_label": "Downtown station area"},
    )

    assert update_response.status_code == 200
    assert update_response.json()["visit_count"] == 20
    assert update_response.json()["display_label"] == "Downtown station area"

    list_response = client.get("/places")
    assert list_response.status_code == 200
    assert list_response.json()["count"] == 1
    assert list_response.json()["places"][0]["id"] == place_id

    delete_response = client.delete(f"/places/{place_id}")
    assert delete_response.status_code == 204
    assert client.get("/places").json()["count"] == 0


def test_public_places_are_scoped_to_session(tmp_path):
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'mca.sqlite3'}")
    first = TestClient(app)
    second = TestClient(app)
    first.post("/sessions")
    second.post("/sessions")

    first.post(
        "/places",
        json={
            "display_label": "Library",
            "latitude": 47.621,
            "longitude": -122.321,
            "visit_count": 4,
        },
    )

    assert first.get("/places").json()["count"] == 1
    assert second.get("/places").json()["count"] == 0


def test_public_place_write_requires_session_cookie(tmp_path):
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'mca.sqlite3'}")
    client = TestClient(app)

    response = client.post(
        "/places",
        json={
            "display_label": "Library",
            "latitude": 47.621,
            "longitude": -122.321,
            "visit_count": 4,
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Public session required"
