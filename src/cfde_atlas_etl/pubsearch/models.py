"""Shared row model for the PPST Script_Input sheet. See docs/pubsearch/SPEC.md.

Column names mirror the Eval team's template exactly (dots and all) so the
export is a straight write. `notes` carries provenance: the source table or
`curated:<yaml path>`.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Literal

ImpactCategory = Literal["Awardee", "User", "Broader.Influence"]

# Values allowed in the template's Field_Search dropdown ('' = search everywhere).
SEARCH_FIELDS: tuple[str, ...] = (
    "",
    "Title",
    "Abstract",
    "Title and Abstract",
    "Author",
    "Result",
    "Supplemental",
    "Other",
    "Keyword",
    "Methods",
    "Introduction",
    "Discussion",
    "Conclusion",
    "Acknowledgement & Funding",
    "Abbreviation",
    "Cites",
    "References",
    "Publication Type",
)

TEMPLATE_COLUMNS: tuple[str, ...] = (
    "Impact.Category",
    "Query.Cluster",
    "Search.terms",
    "Search.Field",
    "OR.terms",
    "OR.Search.Field",
    "AND.terms",
    "AND.Search.Field",
    "NOT.terms",
    "NOT.Search.Field",
    "Notes",
)


@dataclass(frozen=True)
class SeedRow:
    impact_category: ImpactCategory
    query_cluster: str
    search_terms: str
    search_field: str = ""
    or_terms: str = ""
    or_search_field: str = ""
    and_terms: str = ""
    and_search_field: str = ""
    not_terms: str = ""
    not_search_field: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        for f in ("search_field", "or_search_field", "and_search_field", "not_search_field"):
            v = getattr(self, f)
            if v not in SEARCH_FIELDS:
                raise ValueError(f"{f}={v!r} not in template Field_Search dropdown")

    def as_template_row(self) -> list[str]:
        """Values in TEMPLATE_COLUMNS order."""
        return [getattr(self, f.name) for f in fields(self)]
