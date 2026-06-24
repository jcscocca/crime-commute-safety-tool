from fastapi.testclient import TestClient

from app.main import create_app


def test_public_session_endpoint_sets_cookie(tmp_path):
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'mca.sqlite3'}")
    client = TestClient(app)

    response = client.post("/sessions")

    assert response.status_code == 200
    assert response.json()["session_state"] == "created"
    assert "mca_session" in response.cookies
    assert "Max-Age=86400" in response.headers["set-cookie"]


def test_cookie_session_scopes_dashboard_data(tmp_path):
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'mca.sqlite3'}")
    first = TestClient(app)
    second = TestClient(app)

    first.post("/sessions")
    second.post("/sessions")

    first_response = first.get("/dashboard/summary")
    second_response = second.get("/dashboard/summary")

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first.cookies.get("mca_session") != second.cookies.get("mca_session")
