from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def new_id() -> str:
    return str(uuid4())


class LocationObservation(BaseModel):
    source_type: str
    source_record_type: str
    source_record_hash: str | None = None
    observed_at_utc: datetime | None = None
    start_time_utc: datetime | None = None
    end_time_utc: datetime | None = None
    latitude: float | None = None
    longitude: float | None = None
    accuracy_m: float | None = None
    activity_type: str | None = None
    confidence_score: float | None = None


class SourceStop(BaseModel):
    source_type: str
    source_record_type: str
    source_record_hash: str | None = None
    start_time_utc: datetime
    end_time_utc: datetime
    latitude: float
    longitude: float
    accuracy_m: float | None = None
    activity_type: str | None = None
    confidence_score: float | None = None
    display_label: str | None = None


class ParseResult(BaseModel):
    source_type: str
    detected_schema: str
    parser_version: str
    observations: list[LocationObservation] = Field(default_factory=list)
    source_stops: list[SourceStop] = Field(default_factory=list)


class DirectPlaceClusterInput(BaseModel):
    source_type: str
    display_label: str
    latitude: float
    longitude: float
    display_latitude: float | None = None
    display_longitude: float | None = None
    visit_count: int = 1
    total_dwell_minutes: float | None = None
    median_dwell_minutes: float | None = None
    dominant_days: str | None = None
    dominant_hours: str | None = None
    inferred_place_type: str = "unknown"
    sensitivity_class: str = "normal"
    source_record_hash: str | None = None


class DirectPlaceImportResult(BaseModel):
    source_type: str
    detected_schema: str
    parser_version: str
    direct_place_clusters: list[DirectPlaceClusterInput] = Field(default_factory=list)


class StopVisitData(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    id: str = Field(default_factory=new_id)
    import_id: str
    user_id_hash: str
    place_cluster_id: str | None = None
    start_time_utc: datetime
    end_time_utc: datetime
    duration_minutes: float
    local_date: date | None = None
    local_day_of_week: int | None = None
    local_hour_start: int | None = None
    centroid_latitude: float
    centroid_longitude: float
    radius_m: float | None = None
    accuracy_median_m: float | None = None
    source_basis: str
    point_count_used: int | None = None
    confidence_score: float | None = None
    display_label: str | None = None


class PlaceClusterData(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    id: str = Field(default_factory=new_id)
    user_id_hash: str
    cluster_version: str
    cluster_method: str
    centroid_latitude: float
    centroid_longitude: float
    display_latitude: float | None = None
    display_longitude: float | None = None
    cluster_radius_m: float | None = None
    visit_count: int
    total_dwell_minutes: float | None = None
    median_dwell_minutes: float | None = None
    first_seen_utc: datetime | None = None
    last_seen_utc: datetime | None = None
    dominant_days: str | None = None
    dominant_hours: str | None = None
    inferred_place_type: str = "unknown"
    sensitivity_class: str = "normal"
    display_label: str | None = None
    label_source: str | None = None


class CrimeIncidentData(BaseModel):
    id: str = Field(default_factory=new_id)
    external_incident_id: str | None = None
    report_number: str | None = None
    offense_id: str | None = None
    offense_start_utc: datetime | None = None
    offense_end_utc: datetime | None = None
    report_utc: datetime | None = None
    offense_category: str | None = None
    offense_subcategory: str | None = None
    nibrs_group: str | None = None
    precinct: str | None = None
    sector: str | None = None
    beat: str | None = None
    mcpp: str | None = None
    block_address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    source_dataset: str = "seattle_spd_crime"
    snapshot_at: datetime | None = None


class PlaceCrimeSummaryData(BaseModel):
    id: str = Field(default_factory=new_id)
    user_id_hash: str
    place_cluster_id: str
    radius_m: int
    analysis_start_date: date
    analysis_end_date: date
    offense_category: str | None = None
    offense_subcategory: str | None = None
    nibrs_group: str | None = None
    incident_count: int
    nearest_incident_m: float | Decimal | None = None
    incidents_per_visit: float | Decimal | None = None
    incidents_per_hour_dwell: float | Decimal | None = None
    layer: str | None = None
