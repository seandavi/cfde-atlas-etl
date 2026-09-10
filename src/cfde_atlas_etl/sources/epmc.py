"""Europe PMC REST client + PPST-style query builder.

API docs: https://europepmc.org/RestfulWebService

`build_query` renders (term, section, AND/OR/NOT groups, date window) into the
exact string form the NIH OSC Eval team's PPST script emits, so hit counts are
directly comparable to a PPST run (see docs/pubsearch/SPEC.md).
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from typing import Any

import httpx
from pydantic import BaseModel

BASE_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest"
RETRIES = 3

# PPST template Field_Search names -> Europe PMC section prefixes.
SECTION_PREFIX: dict[str, str] = {
    "": "",
    "Title": "TITLE:",
    "Abstract": "ABSTRACT:",
    "Title and Abstract": "TITLE_ABS:",
    "Author": "AUTH:",
    "Result": "RESULTS:",
    "Supplemental": "SUPPL:",
    "Other": "OTHER:",
    "Keyword": "KEYWORD:",
    "Methods": "METHODS:",
    "Introduction": "INTRO:",
    "Discussion": "DISCUSS:",
    "Conclusion": "CONCL:",
    "Acknowledgement & Funding": "ACK_FUND:",
    "Abbreviation": "ABBR:",
    "Cites": "CITES:",
    "References": "REF:",
    "Publication Type": "PUB_TYPE:",
}

# Bare (unquoted) tokens: wildcard grant serials (*HL132363), and identifier-like
# tokens with a digit (phs001138, 37788089_med, 4DN). Everything else is quoted,
# which is what PPST inputs look like ("Cavatica", "Kids First").
_BARE = re.compile(r"^\*|^(?=.*\d)[A-Za-z0-9_]+$")


def _render_term(term: str) -> str:
    term = term.strip().strip('"')
    return term if _BARE.search(term) else f'"{term}"'


def _render_group(terms: str, section: str) -> str:
    rendered = [_render_term(t) for t in terms.split(",") if t.strip()]
    prefix = SECTION_PREFIX[section]
    inner = " OR ".join(rendered)
    if prefix:
        return f"{prefix}({inner})"
    return inner if len(rendered) == 1 else f"({inner})"


def build_query(
    term: str,
    section: str = "",
    *,
    and_terms: str = "",
    and_section: str = "",
    or_terms: str = "",
    or_section: str = "",
    not_terms: str = "",
    not_section: str = "",
    date_window: tuple[int, int] | None = None,
) -> str:
    """Render a PPST-style Europe PMC query.

    Comma-separated terms within a group are OR-ed; groups are appended with their
    operator in template column order (OR, AND, NOT); the date window is appended
    as `AND (FIRST_PDATE:[a TO b])`; the whole thing is wrapped in parentheses.
    """
    parts = [_render_group(term, section)]
    for op, terms, sec in (
        ("OR", or_terms, or_section),
        ("AND", and_terms, and_section),
        ("NOT", not_terms, not_section),
    ):
        if terms.strip():
            parts.append(f"{op} {_render_group(terms, sec)}")
    if date_window:
        parts.append(f"AND (FIRST_PDATE:[{date_window[0]} TO {date_window[1]}])")
    return f"({' '.join(parts)})"


class EpmcHit(BaseModel):
    id: str
    source: str
    pmid: str | None = None
    pmcid: str | None = None
    pub_year: int | None = None
    is_open_access: bool = False
    title: str | None = None

    @classmethod
    def from_result(cls, r: dict[str, Any]) -> EpmcHit:
        year = r.get("pubYear")
        return cls(
            id=str(r["id"]),
            source=r["source"],
            pmid=r.get("pmid"),
            pmcid=r.get("pmcid"),
            pub_year=int(year) if year else None,
            is_open_access=r.get("isOpenAccess") == "Y",
            title=r.get("title"),
        )


async def _get(client: httpx.AsyncClient, url: str, params: dict[str, Any]) -> httpx.Response:
    """GET with retries + exponential backoff on 5xx and connection errors."""
    for attempt in range(RETRIES):
        try:
            response = await client.get(url, params=params)
            if response.status_code < 500:
                return response
            if attempt == RETRIES - 1:
                response.raise_for_status()
        except httpx.TransportError:
            if attempt == RETRIES - 1:
                raise
        await asyncio.sleep(2**attempt)
    raise AssertionError("unreachable")


async def search(
    query: str,
    *,
    page_size: int = 1000,
    result_type: str = "lite",
    client: httpx.AsyncClient | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Yield every raw result dict for `query`, following cursorMark paging."""
    own_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=60.0)
    try:
        cursor = "*"
        while True:
            response = await _get(
                client,
                f"{BASE_URL}/search",
                {
                    "query": query,
                    "format": "json",
                    "resultType": result_type,
                    "pageSize": page_size,
                    "cursorMark": cursor,
                },
            )
            response.raise_for_status()
            payload = response.json()
            results = (payload.get("resultList") or {}).get("result") or []
            for r in results:
                yield r
            next_cursor = payload.get("nextCursorMark")
            if not results or not next_cursor or next_cursor == cursor:
                return
            cursor = next_cursor
    finally:
        if own_client:
            await client.aclose()


async def hit_count(query: str, *, client: httpx.AsyncClient | None = None) -> int:
    own_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=60.0)
    try:
        response = await _get(
            client,
            f"{BASE_URL}/search",
            {"query": query, "format": "json", "resultType": "lite", "pageSize": 1},
        )
        response.raise_for_status()
        return int(response.json()["hitCount"])
    finally:
        if own_client:
            await client.aclose()


async def full_text_xml(pmcid: str, *, client: httpx.AsyncClient | None = None) -> str | None:
    """Return the JATS XML for a PMCID, or None if Europe PMC has no full text (404)."""
    own_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=60.0)
    try:
        response = await _get(client, f"{BASE_URL}/{pmcid}/fullTextXML", {})
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.text
    finally:
        if own_client:
            await client.aclose()
