from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def limited_client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("MCA_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("MCA_RATE_LIMIT_SESSIONS_PER_HOUR", "3")
    monkeypatch.setenv("MCA_TRUST_PROXY_HEADERS", "false")
    app = create_app(f"sqlite+pysqlite:///{tmp_path}/rl.sqlite3")
    return TestClient(app)


def test_session_creation_capped(limited_client: TestClient) -> None:
    for _ in range(3):
        assert limited_client.post("/sessions").status_code == 200
    response = limited_client.post("/sessions")
    assert response.status_code == 429
    assert "Retry-After" in response.headers
    detail = response.json()["detail"].lower()
    # invariant-safe copy: about request limits, never place characteristics
    assert "request" in detail or "limit" in detail


def test_spoofed_proxy_header_ignored_without_trust(limited_client: TestClient) -> None:
    # All 4 calls come from the same socket peer; the spoofed header must NOT
    # give each call a fresh bucket.
    for i in range(3):
        assert (
            limited_client.post("/sessions", headers={"CF-Connecting-IP": f"8.8.8.{i}"}).status_code
            == 200
        )
    assert (
        limited_client.post("/sessions", headers={"CF-Connecting-IP": "8.8.9.9"}).status_code
        == 429
    )


def test_trusted_proxy_header_separates_clients(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MCA_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("MCA_RATE_LIMIT_SESSIONS_PER_HOUR", "1")
    monkeypatch.setenv("MCA_TRUST_PROXY_HEADERS", "true")
    app = create_app(f"sqlite+pysqlite:///{tmp_path}/rl2.sqlite3")
    client = TestClient(app)
    assert client.post("/sessions", headers={"CF-Connecting-IP": "8.8.8.1"}).status_code == 200
    assert client.post("/sessions", headers={"CF-Connecting-IP": "8.8.8.2"}).status_code == 200
    assert client.post("/sessions", headers={"CF-Connecting-IP": "8.8.8.1"}).status_code == 429


def test_limiter_off_by_default(tmp_path) -> None:
    app = create_app(f"sqlite+pysqlite:///{tmp_path}/rl3.sqlite3")
    client = TestClient(app)
    for _ in range(25):
        assert client.post("/sessions").status_code == 200


def test_assistant_global_daily_cap(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MCA_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("MCA_RATE_LIMIT_ASSISTANT_GLOBAL_PER_DAY", "0")
    app = create_app(f"sqlite+pysqlite:///{tmp_path}/rl4.sqlite3")
    client = TestClient(app)
    client.post("/sessions")
    response = client.post(
        "/assistant/chat",
        json={"messages": [{"role": "user", "content": "hi"}], "dashboard_state": {}},
    )
    assert response.status_code == 429
    detail = response.json()["detail"].lower()
    assert "analyst" in detail and ("limit" in detail or "capacity" in detail)
