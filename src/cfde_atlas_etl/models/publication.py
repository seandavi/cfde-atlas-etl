"""Source models for publication-related upstream APIs.

Two separate guards because the raw layer stores both shapes separately
(see migrations/0008 and 0009) and the analytics view joins them.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


def _coerce_int_list(v: Any) -> Any:
    """iCite returns cited_by/references as None (no relations), a space-separated
    string ('12345 67890'), or already a list. Normalize to list[int]."""
    if v is None or v == "":
        return []
    if isinstance(v, str):
        return [int(x) for x in v.split() if x.strip().isdigit()]
    return v


NullableIntList = Annotated[list[int], BeforeValidator(_coerce_int_list)]


def _coerce_authors(v: Any) -> Any:
    """iCite returns authors as a comma-separated string ('Smith J, Jones K').
    Normalize to a list[str] so the raw jsonb stays consistent."""
    if v is None or v == "":
        return []
    if isinstance(v, str):
        return [a.strip() for a in v.split(",") if a.strip()]
    return v


AuthorsField = Annotated[list[Any], BeforeValidator(_coerce_authors)]


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
    authors: AuthorsField = Field(default_factory=list)
    cited_by: NullableIntList = Field(default_factory=list)
    references: NullableIntList = Field(default_factory=list)
