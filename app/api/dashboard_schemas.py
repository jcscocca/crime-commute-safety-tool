from __future__ import annotations

from datetime import date
from typing import Annotated

from pydantic import BaseModel, Field, field_validator

from app.crime.sources import LAYER_REPORTED, LAYERS

DashboardRadiusMeters = Annotated[int, Field(gt=0, le=5000)]


def _validate_layer(value: str) -> str:
    if value not in LAYERS:
        allowed = ", ".join(sorted(LAYERS))
        raise ValueError(f"layer must be one of: {allowed}")
    return value


class DashboardAnalyzeRequest(BaseModel):
    place_ids: list[str] = Field(min_length=1)
    analysis_start_date: date
    analysis_end_date: date
    radii_m: list[DashboardRadiusMeters] = Field(min_length=1)
    offense_category: str | None = None
    offense_subcategory: str | None = None
    nibrs_group: str | None = None
    # Which incident-context layer to query: "reported" (SPD crime + arrests, unioned) or
    # "calls" (911 calls for service). The two are mutually exclusive by design.
    layer: str = LAYER_REPORTED

    @field_validator("radii_m")
    @classmethod
    def radii_m_values_must_be_unique(cls, value: list[int]) -> list[int]:
        if len(value) != len(set(value)):
            raise ValueError("radii_m values must be unique")
        return value

    @field_validator("layer")
    @classmethod
    def layer_must_be_known(cls, value: str) -> str:
        return _validate_layer(value)


class DashboardCompareRequest(BaseModel):
    place_ids: list[str] = Field(min_length=2)
    analysis_start_date: date
    analysis_end_date: date
    radius_m: DashboardRadiusMeters
    offense_category: str | None = None
    offense_subcategory: str | None = None
    nibrs_group: str | None = None
    layer: str = LAYER_REPORTED

    @field_validator("layer")
    @classmethod
    def layer_must_be_known(cls, value: str) -> str:
        return _validate_layer(value)


class DashboardIncidentDetailsRequest(DashboardAnalyzeRequest):
    limit: int = Field(default=100, ge=1, le=500)


class GeocodeResultSchema(BaseModel):
    label: str
    latitude: float
    longitude: float
    source: str
