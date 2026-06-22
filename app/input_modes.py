from __future__ import annotations


def supported_input_modes() -> list[dict[str, object]]:
    return [
        {
            "id": "personal_timeline",
            "label": "Personal timeline upload",
            "privacy_level": "high",
            "description": "Google Timeline JSON, raw point CSV, GeoJSON, or GPX.",
            "required_columns": [],
            "optional_columns": [],
            "sample_csv": "",
        },
        {
            "id": "recurring_places_csv",
            "label": "Generalized recurring places CSV",
            "privacy_level": "low",
            "description": "Upload only recurring places or areas to analyze.",
            "required_columns": ["display_label", "latitude", "longitude"],
            "optional_columns": [
                "visit_count",
                "total_dwell_minutes",
                "median_dwell_minutes",
                "typical_days",
                "typical_hours",
                "sensitivity_class",
            ],
            "sample_csv": (
                "display_label,latitude,longitude,visit_count,total_dwell_minutes\n"
                "Downtown transfer stop,47.609,-122.333,12,360\n"
            ),
        },
        {
            "id": "public_commute_scenario",
            "label": "Public commute scenario",
            "privacy_level": "very_low",
            "description": "Model a commute using generalized Seattle areas.",
            "required_columns": ["origin_area", "destination_area", "mode"],
            "optional_columns": ["usual_departure_time", "frequency_per_week"],
            "sample_csv": (
                "origin_area,destination_area,mode,usual_departure_time,frequency_per_week\n"
                "Capitol Hill,Downtown Seattle,transit,08:00,4\n"
            ),
        },
    ]
