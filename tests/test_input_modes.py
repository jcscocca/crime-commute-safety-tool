from fastapi.testclient import TestClient

from app.main import create_app


def test_input_modes_endpoint_describes_all_three_modes(tmp_path):
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'mca.sqlite3'}")
    client = TestClient(app)

    response = client.get("/input-modes")

    assert response.status_code == 200
    payload = response.json()
    ids = [mode["id"] for mode in payload["modes"]]
    assert ids == ["personal_timeline", "recurring_places_csv", "public_commute_scenario"]
    recurring = payload["modes"][1]
    assert recurring["privacy_level"] == "low"
    assert "display_label" in recurring["required_columns"]
    assert "latitude" in recurring["sample_csv"]
