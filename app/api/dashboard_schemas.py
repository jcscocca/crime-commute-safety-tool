from __future__ import annotations

from datetime import date
from typing import Annotated

from pydantic import BaseModel, Field, field_validator

DashboardRadiusMeters = Annotated[int, Field(gt=0, le=5000)]


class DashboardAnalyzeRequest(BaseModel):
    place_ids: list[str] = Field(min_length=1)
    analysis_start_date: date
    analysis_end_date: date
    radii_m: list[DashboardRadiusMeters] = Field(min_length=1)
    offense_category: str | None = None
    offense_subcategory: str | None = None
    nibrs_group: str | None = None

    @field_validator("radii_m")
    @classmethod
    def radii_m_values_must_be_unique(cls, value: list[int]) -> list[int]:
        if len(value) != len(set(value)):
            raise ValueError("radii_m values must be unique")
        return value


class DashboardCompareRequest(BaseModel):
    place_ids: list[str] = Field(min_length=2)
    analysis_start_date: date
    analysis_end_date: date
    radius_m: DashboardRadiusMeters
    offense_category: str | None = None
    offense_subcategory: str | None = None
    nibrs_group: str | None = None


class DashboardIncidentDetailsRequest(DashboardAnalyzeRequest):
    limit: int = Field(default=100, ge=1, le=500)
