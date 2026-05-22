"""Pydantic source model for publications.

Only the source shape is modeled here. The target shape lives in
`migrations/` as a SQL view (`analytics.publications`), per the ELT pattern.

The source model is a guard, not a contract: validating at fetch time
catches upstream schema breakage loud rather than letting bad data into
the raw layer.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class IccEvalPublication(BaseModel):
    """Source record from icc-eval-core /data/output/publications.json."""

    model_config = ConfigDict(extra="allow")  # allow upstream to add fields without breaking us

    id: int = Field(..., description="PubMed ID")
    coreProject: str = Field(..., description="NIH core project number")
    application: int | None = None
    title: str
    authors: list[str] = Field(default_factory=list)
    journal: str
    year: int
    modified: datetime | None = None
    doi: str | None = None
    relativeCitationRatio: float | None = None
    citations: int = 0
    citationsPerYear: float | None = None
