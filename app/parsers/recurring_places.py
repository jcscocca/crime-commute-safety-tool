from __future__ import annotations

import csv
from io import StringIO
from typing import Any

from app.normalization.geo import is_valid_coordinate, snap_to_grid
from app.parsers.base import SourceParser, stable_record_hash
from app.schemas import DirectPlaceClusterInput, DirectPlaceImportResult

REQUIRED_COLUMNS = {"display_label", "latitude", "longitude"}


class RecurringPlacesParser(SourceParser):
    source_type = "recurring_places_csv"

    def can_parse(self, payload: bytes, filename: str) -> bool:
        if not filename.lower().endswith(".csv"):
            return False
        fieldnames = _fieldnames(payload)
        return REQUIRED_COLUMNS.issubset(fieldnames)

    def parse_bytes(self, payload: bytes, filename: str) -> DirectPlaceImportResult:
        reader = csv.DictReader(StringIO(payload.decode("utf-8-sig")))
        places = []
        for row in reader:
            latitude = _float_or_none(row.get("latitude"))
            longitude = _float_or_none(row.get("longitude"))
            if not is_valid_coordinate(latitude, longitude):
                continue
            display_latitude, display_longitude = snap_to_grid(latitude, longitude)
            places.append(
                DirectPlaceClusterInput(
                    source_type=self.source_type,
                    display_label=(row.get("display_label") or "Recurring area").strip(),
                    latitude=latitude,
                    longitude=longitude,
                    display_latitude=display_latitude,
                    display_longitude=display_longitude,
                    visit_count=_int_or_default(row.get("visit_count"), default=1),
                    total_dwell_minutes=_float_or_none(row.get("total_dwell_minutes")),
                    median_dwell_minutes=_float_or_none(row.get("median_dwell_minutes")),
                    dominant_days=_empty_to_none(row.get("typical_days")),
                    dominant_hours=_empty_to_none(row.get("typical_hours")),
                    sensitivity_class=_empty_to_none(row.get("sensitivity_class")) or "normal",
                    source_record_hash=stable_record_hash(row),
                )
            )
        return DirectPlaceImportResult(
            source_type=self.source_type,
            detected_schema="recurring_places_csv",
            parser_version=self.parser_version,
            direct_place_clusters=places,
        )


def _fieldnames(payload: bytes) -> set[str]:
    reader = csv.DictReader(StringIO(payload[:1000].decode("utf-8-sig", errors="ignore")))
    return {field.strip().lower() for field in (reader.fieldnames or [])}


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _int_or_default(value: Any, default: int) -> int:
    if value is None or value == "":
        return default
    return int(float(value))


def _empty_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None
