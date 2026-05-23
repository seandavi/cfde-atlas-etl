"""NCBI Entrez E-utilities client.

For each journal abbreviation, esearch PubMed for `<abbrev>[TA]`, take the
first hit, then esummary to extract `fulljournalname` and `essn` (electronic
ISSN). Mirrors icc-eval-core's getFullJournalName logic.

Rate limits: 3 req/s without NCBI_API_KEY, 10 req/s with one. We respect
that with a token bucket-ish asyncio.Semaphore on the caller side, not here.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"


def _params() -> dict[str, str]:
    params = {"retmode": "json", "db": "pubmed"}
    api_key = os.environ.get("NCBI_API_KEY")
    if api_key:
        params["api_key"] = api_key
    return params


async def lookup_journal(abbrev: str, *, client: httpx.AsyncClient | None = None) -> dict[str, Any]:
    """Return {"abbrev", "name", "issn"} for a journal abbreviation.

    On lookup failure (no pubmed hit), returns name=abbrev and issn="".
    """
    own_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=30.0)
    try:
        params = _params()
        search = await client.get(ESEARCH, params={**params, "term": f"{abbrev}[TA]"})
        search.raise_for_status()
        ids = (search.json().get("esearchresult") or {}).get("idlist") or []
        if not ids:
            return {"abbrev": abbrev, "name": abbrev, "issn": ""}
        first_id = ids[0]

        summary = await client.get(ESUMMARY, params={**params, "id": first_id})
        summary.raise_for_status()
        result = (summary.json().get("result") or {}).get(first_id) or {}
        return {
            "abbrev": abbrev,
            "name": result.get("fulljournalname") or abbrev,
            "issn": (result.get("essn") or "").replace("-", ""),
        }
    finally:
        if own_client:
            await client.aclose()
