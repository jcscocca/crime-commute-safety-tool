from __future__ import annotations

import csv
from io import StringIO
from typing import Any

from app.data.seattle_area_centroids import SEATTLE_AREA_CENTROIDS
from app.normalization.geo import snap_to_grid
from app.parsers.base import SourceParser, stable_record_hash
from app.schemas import DirectPlaceClusterInput, DirectPlaceImportResult

REQUIRED_COLUMNS = {"origin_area", "destination_area", "mode"}


class CommuteScenarioParser(SourceParser):
    source_type = "public_commute_scenario"

    def can_parse(self, payload: bytes, filename: str) -> bool:
        if not filename.lower().endswith(".csv"):
            return False
        fieldnames = _fieldnames(payload)
        return REQUIRED_COLUMNS.issubset(fieldnames)

    def parse_bytes(self, payload: bytes, filename: str) -> DirectPlaceImportResult:
        reader = csv.DictReader(StringIO(payload.decode("utf-8-sig")))
        places: list[DirectPlaceClusterInput] = []
        seen: set[tuple[str, str]] = set()
        for row in reader:
            frequency = _int_or_default(row.get("frequency_per_week"), default=1)
            for role, area_key in (
                ("origin", row.get("origin_area")),
                ("destination", row.get("destination_area")),
            ):
                label = (area_key or "").strip()
                coordinates = SEATTLE_AREA_CENTROIDS.get(label.lower())
                if coordinates is None:
                    continue
                dedupe_key = (role, label.lower())
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                latitude, longitude = coordinates
                display_latitude, display_longitude = snap_to_grid(latitude, longitude)
                places.append(
                    DirectPlaceClusterInput(
                        source_type=self.source_type,
                        display_label=f"{label} {role} area",
                        latitude=latitude,
                        longitude=longitude,
                        display_latitude=display_latitude,
                        display_longitude=display_longitude,
                        visit_count=frequency,
                        total_dwell_minutes=None,
                        median_dwell_minutes=None,
                        dominant_hours=_empty_to_none(row.get("usual_departure_time")),
                        inferred_place_type="commute_area",
                        sensitivity_class="normal",
                        source_record_hash=stable_record_hash({"role": role, "row": row}),
                    )
                )
        return DirectPlaceImportResult(
            source_type=self.source_type,
            detected_schema="public_commute_scenario_csv",
            parser_version=self.parser_version,
            direct_place_clusters=places,
        )


def _fieldnames(payload: bytes) -> set[str]:
    reader = csv.DictReader(StringIO(payload[:1000].decode("utf-8-sig", errors="ignore")))
    return {field.strip().lower() for field in (reader.fieldnames or [])}


def _int_or_default(value: Any, default: int) -> int:
    if value is None or value == "":
        return default
    return int(float(value))


def _empty_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None
