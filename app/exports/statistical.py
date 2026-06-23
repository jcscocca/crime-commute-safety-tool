from __future__ import annotations

import csv
from collections.abc import Iterable, Mapping
from io import StringIO
from typing import Any

STATISTICAL_COMPARISON_COLUMNS = [
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
]


def build_statistical_comparisons_csv(rows: Iterable[Mapping[str, Any]]) -> str:
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=STATISTICAL_COMPARISON_COLUMNS,
        extrasaction="ignore",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                column: _csv_value(row.get(column))
                for column in STATISTICAL_COMPARISON_COLUMNS
            }
        )
    return output.getvalue()


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    return value
