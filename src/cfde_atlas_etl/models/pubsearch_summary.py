"""Per-program pubsearch summary document rendered by the cfde-atlas report page.

Schema is committed to docs/pubsearch/summary.schema.json (see
pubsearch/summary_json.py). Bump ``schema_version`` on any breaking change.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Tier = Literal["Awardee", "User", "Broader.Influence"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RunBlock(_Strict):
    run_id: str
    program: str
    display_name: str
    program_yaml_sha: str | None = None
    date_window: tuple[int | None, int | None] = Field(
        description="[first_year, last_year] inclusive; null = unbounded"
    )
    started_at: datetime
    finished_at: datetime | None = None
    query_count: int
    hit_count: int
    unique_pmids: int
    preprint_hits: int


class TierBlock(_Strict):
    tier: Tier
    papers: int
    papers_excl_preprints: int
    pmids: int


class ClusterBlock(_Strict):
    cluster: str
    impact_category: Tier | None = None
    papers: int
    papers_excl_preprints: int
    pmids: int
    query_count: int


class YearBlock(_Strict):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    year: int
    awardee: int = Field(0, alias="Awardee")
    user: int = Field(0, alias="User")
    broader_influence: int = Field(0, alias="Broader.Influence")


class JournalBlock(_Strict):
    journal: str
    papers: int


class RcrBlock(_Strict):
    n: int
    median: float
    q1: float
    q3: float
    max: float


class OverridesBlock(_Strict):
    count: int
    by_tier: dict[str, int]


class PubsearchSummary(_Strict):
    schema_version: Literal[1] = 1
    run: RunBlock
    tiers: list[TierBlock]
    clusters: list[ClusterBlock]
    by_year: list[YearBlock] = Field(
        description="Paper counts per year per final tier, preprints excluded"
    )
    top_journals: list[JournalBlock] = Field(
        description="Top 15 journals among matrix papers joined to analytics.publications"
    )
    rcr: RcrBlock | None = Field(
        description="relative_citation_ratio distribution over joined papers; null if none"
    )
    overrides: OverridesBlock
    notes: list[str]
