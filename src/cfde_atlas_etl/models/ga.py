"""Source models for GA properties + GA reports."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class GaProperty(BaseModel):
    model_config = ConfigDict(extra="allow")

    property_id: str = Field(..., description="GA4 numeric property id")
    display_name: str | None = None
    hostname: str | None = None
    core_project_number: str | None = None
    dcc: str | None = None
    granted_at: date | None = None


class GaReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    property_id: str
    report_kind: str
    period_start: date
    period_end: date
    response: dict[str, object]
