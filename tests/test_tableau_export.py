from datetime import date

from app.exports.tableau import build_place_summary_csv
from app.schemas import PlaceClusterData, PlaceCrimeSummaryData


def test_tableau_export_excludes_sensitive_clusters_by_default_and_uses_display_coordinates():
    normal = PlaceClusterData(
        id="normal-cluster",
        user_id_hash="user-hash",
        cluster_version="v1",
        cluster_method="pure_python_radius",
        centroid_latitude=47.609512,
        centroid_longitude=-122.333123,
        display_latitude=47.61,
        display_longitude=-122.333,
        cluster_radius_m=30,
        visit_count=3,
        total_dwell_minutes=90,
        median_dwell_minutes=30,
        display_label="Recurring area",
    )
    sensitive = PlaceClusterData(
        id="home-cluster",
        user_id_hash="user-hash",
        cluster_version="v1",
        cluster_method="pure_python_radius",
        centroid_latitude=47.650123,
        centroid_longitude=-122.350123,
        cluster_radius_m=20,
        visit_count=5,
        total_dwell_minutes=2400,
        median_dwell_minutes=480,
        sensitivity_class="home_candidate",
    )
    summary = PlaceCrimeSummaryData(
        id="summary-1",
        user_id_hash="user-hash",
        place_cluster_id="normal-cluster",
        radius_m=250,
        analysis_start_date=date(2024, 1, 1),
        analysis_end_date=date(2024, 1, 31),
        offense_category="PROPERTY",
        offense_subcategory="THEFT",
        nibrs_group="A",
        incident_count=2,
        nearest_incident_m=12.4,
        incidents_per_visit=0.6667,
        incidents_per_hour_dwell=1.3333,
    )

    csv_text = build_place_summary_csv([normal, sensitive], [summary], tableau_safe=True)

    assert "normal-cluster" in csv_text
    assert "home-cluster" not in csv_text
    assert "47.61" in csv_text
    assert "47.609512" not in csv_text
    assert "PROPERTY" in csv_text


def test_tableau_export_accepts_direct_input_mode_clusters():
    cluster = PlaceClusterData(
        id="scenario-cluster",
        user_id_hash="user-hash",
        cluster_version="direct-1",
        cluster_method="direct_user_input",
        centroid_latitude=47.609,
        centroid_longitude=-122.333,
        display_latitude=47.609,
        display_longitude=-122.333,
        cluster_radius_m=100,
        visit_count=4,
        total_dwell_minutes=None,
        median_dwell_minutes=None,
        display_label="Downtown Seattle destination area",
    )

    csv_text = build_place_summary_csv([cluster], [], tableau_safe=True)

    assert "Downtown Seattle destination area" in csv_text
    assert "scenario-cluster" in csv_text
