"""Source models for the journals flow."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ScimagoRank(BaseModel):
    model_config = ConfigDict(extra="allow")

    Sourceid: int = Field(..., description="Scimago internal source id; the PK")
    Title: str | None = None
    Type: str | None = None
    SJR: str | None = Field(None, description="SJR score as a string (European decimal comma)")
    issns: list[str] = Field(
        default_factory=list, description="Normalized ISSN list (hyphens removed)"
    )


class EntrezJournal(BaseModel):
    model_config = ConfigDict(extra="allow")

    abbrev: str = Field(..., description="Journal abbreviation (NLM TA field)")
    name: str = Field("", description="Full journal name (from PubMed esummary fulljournalname)")
    issn: str = Field("", description="Electronic ISSN with hyphens stripped")
