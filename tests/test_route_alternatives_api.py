from fastapi.testclient import TestClient

from app.main import create_app


def test_route_alternatives_api_creates_request_and_ranked_routes(tmp_path):
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'mca.sqlite3'}")
    client = TestClient(app)
    headers = {"X-Demo-User-Id": "route-user@example.com"}

    response = client.post(
        "/routes/alternatives",
        json={
            "origin_label": "Capitol Hill",
            "destination_label": "Downtown Seattle",
            "mode": "transit",
            "departure_date": "2024-01-15",
            "departure_time": "08:00",
            "time_window": "weekday_morning",
            "preferences": ["fewer_transfers"],
        },
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["request"]["origin"]["label"] == "Capitol Hill"
    assert payload["request"]["destination"]["label"] == "Downtown Seattle"
    assert payload["request"]["provider"] == "mock"
    assert len(payload["alternatives"]) >= 2
    assert payload["alternatives"][0]["rank"] == 1
    assert payload["alternatives"][0]["segments"]
    assert payload["context_summaries"] == []

    comparison = client.get(
        f"/routes/requests/{payload['request']['id']}/comparison",
        headers=headers,
    )

    assert comparison.status_code == 200
    assert comparison.json()["request"]["id"] == payload["request"]["id"]


def test_route_alternatives_api_rejects_unknown_origin(tmp_path):
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'mca.sqlite3'}")
    client = TestClient(app)

    response = client.post(
        "/routes/alternatives",
        json={
            "origin_label": "Not A Seattle Place",
            "destination_label": "Downtown Seattle",
            "mode": "transit",
        },
        headers={"X-Demo-User-Id": "route-user@example.com"},
    )

    assert response.status_code == 400
    assert "Unknown route place" in response.json()["detail"]


def test_route_comparison_is_scoped_to_request_user(tmp_path):
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'mca.sqlite3'}")
    client = TestClient(app)

    response = client.post(
        "/routes/alternatives",
        json={
            "origin_label": "Capitol Hill",
            "destination_label": "Downtown Seattle",
            "mode": "transit",
        },
        headers={"X-Demo-User-Id": "route-user@example.com"},
    )

    assert response.status_code == 200
    request_id = response.json()["request"]["id"]

    comparison = client.get(
        f"/routes/requests/{request_id}/comparison",
        headers={"X-Demo-User-Id": "different-user@example.com"},
    )

    assert comparison.status_code == 404
