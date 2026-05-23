"""Source model for Common Fund opportunities.

Guard at the fetch boundary. `extra="allow"` so adding fields upstream
(e.g. a future scraped due-date) doesn't break the loader.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CommonFundOpportunity(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(..., description="Opportunity number, e.g. RFA-RM-24-006")
    prefix: str = Field(..., description="One of RFA / NOT / OTA")
    activity_code: str = Field("", description="NIH activity code (e.g. U54, R03); empty for PDFs")
    source_url: str = Field(..., description="URL where this opportunity was parsed from")
