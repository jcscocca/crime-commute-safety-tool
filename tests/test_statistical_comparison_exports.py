import csv
from datetime import UTC, datetime
from io import StringIO

from fastapi.testclient import TestClient

from app.db import get_sessionmaker
from app.main import create_app
from app.models import CrimeIncident

STATISTICAL_COMPARISON_EXPORT_COLUMNS = {
    "comparison_id",
    "comparison_type",
    "option_a_id",
    "option_a_label",
    "option_b_id",
    "option_b_label",
    "winner_option_id",
    "winner_label",
    "decision_class",
    "method",
    "radius_m",
    "analysis_start_date",
    "analysis_end_date",
    "offense_category",
    "offense_subcategory",
    "incident_count_a",
    "incident_count_b",
    "exposure_a",
    "exposure_b",
    "exposure_unit",
    "rate_a",
    "rate_b",
    "rate_ratio",
    "ci_lower",
    "ci_upper",
    "p_value",
    "adjusted_p_value",
    "overdispersion_phi",
    "overdispersion_status",
    "minimum_data_status",
    "overview_summary_text",
    "caveat_text",
    "created_at",
}


def test_statistical_comparison_tableau_export_includes_site_pairwise_results(tmp_path):
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'mca.sqlite3'}")
    client = TestClient(app)
    headers = {"X-Demo-User-Id": "statistical-export-user@example.com"}

    session = get_sessionmaker()()
    session.add_all(
        [
            CrimeIncident(
                id=f"site-a-property-{index}",
                offense_start_utc=datetime(2024, 1, 1 + index, tzinfo=UTC),
                offense_category="PROPERTY",
                latitude=47.6116,
                longitude=-122.3372,
            )
            for index in range(8)
        ]
        + [
            CrimeIncident(
                id=f"site-b-property-{index}",
                offense_start_utc=datetime(2024, 1, 1 + index, tzinfo=UTC),
                offense_category="PROPERTY",
                latitude=47.6205,
                longitude=-122.3493,
            )
            for index in range(28)
        ]
    )
    session.commit()
    session.close()

    comparison_response = client.post(
        "/analysis/sites/compare",
        json={
            "analysis_start_date": "2024-01-01",
            "analysis_end_date": "2024-01-31",
            "offense_category": "PROPERTY",
            "options": [
                {
                    "id": "site-a",
                    "label": "Site A",
                    "latitude": 47.6116,
                    "longitude": -122.3372,
                    "radius_m": 250,
                },
                {
                    "id": "site-b",
                    "label": "Site B",
                    "latitude": 47.6205,
                    "longitude": -122.3493,
                    "radius_m": 250,
                },
            ],
        },
        headers=headers,
    )
    assert comparison_response.status_code == 200
    comparison_id = comparison_response.json()["id"]

    export_response = client.get(
        "/exports/tableau/statistical-comparisons.csv",
        headers=headers,
    )

    assert export_response.status_code == 200
    assert (
        export_response.headers["content-disposition"]
        == "attachment; filename=statistical-comparisons.csv"
    )
    rows = list(csv.DictReader(StringIO(export_response.text)))
    assert rows
    assert rows[0].keys() == STATISTICAL_COMPARISON_EXPORT_COLUMNS
    assert rows[0]["comparison_id"] == comparison_id
    assert rows[0]["decision_class"] in {
        "statistically_lower",
        "not_statistically_clear",
        "insufficient_data",
        "model_warning",
    }
