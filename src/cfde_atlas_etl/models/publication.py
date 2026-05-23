"""Source models for publication-related upstream APIs.

Two separate guards because the raw layer stores both shapes separately
(see migrations/0008 and 0009) and the analytics view joins them.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ReporterPublication(BaseModel):
    model_config = ConfigDict(extra="allow")

    pmid: int = Field(..., description="PubMed ID")
    coreproject: str | None = Field(None, description="RePORTER core_project_num")
    applid: int | None = None
    pub_title: str | None = None
    journal_title: str | None = None
    pub_year: int | None = None
    doi: str | None = None


class IcitePublication(BaseModel):
    model_config = ConfigDict(extra="allow")

    pmid: int = Field(..., description="PubMed ID")
    title: str | None = None
    journal: str | None = None
    year: int | None = None
    doi: str | None = None
    last_modified: str | None = None
    relative_citation_ratio: float | None = None
    citation_count: int | None = None
    citations_per_year: float | None = None
    authors: list[dict[str, Any]] = Field(default_factory=list)
    cited_by: list[int] = Field(default_factory=list)
    references: list[int] = Field(default_factory=list)
