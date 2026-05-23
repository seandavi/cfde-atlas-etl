"""Source model for NIH RePORTER project records.

extra="allow" is essential — RePORTER returns dozens of fields we don't pin.
We validate only the keys we actually use downstream.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ReporterProject(BaseModel):
    model_config = ConfigDict(extra="allow")

    project_num: str = Field(..., description="Full project number, the PK")
    core_project_num: str | None = Field(None, description="Core project number, e.g. U54OD036472")
    project_title: str | None = None
    appl_id: int | None = None
    award_amount: float | None = None
    activity_code: str | None = None
    agency_code: str | None = None
    opportunity_number: str | None = None
    project_start_date: str | None = None
    project_end_date: str | None = None
    is_active: bool | None = None
    principal_investigators: list[dict[str, Any]] | None = None
    organization: dict[str, Any] | None = None
