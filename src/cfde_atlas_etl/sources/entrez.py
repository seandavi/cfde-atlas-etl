"""NCBI Entrez E-utilities client.

For each journal abbreviation, esearch PubMed for `<abbrev>[TA]`, take the
first hit, then esummary to extract `fulljournalname` and `essn` (electronic
ISSN). Mirrors icc-eval-core's getFullJournalName logic.

Rate limits: NCBI enforces 3 req/s wall-clock without NCBI_API_KEY, 10 req/s
with one. The cap is per-request, not per logical operation — and each
lookup_journal call makes TWO requests (esearch + esummary). The
module-level asyncio.Lock + last_call timestamp gate every request and
guarantee >= NCBI_MIN_INTERVAL between consecutive network calls regardless
of concurrent callers.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

import httpx

ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"

NCBI_MIN_INTERVAL = 0.12 if os.environ.get("NCBI_API_KEY") else 0.4

_rate_lock = asyncio.Lock()
_last_call_monotonic = 0.0


async def _gated_get(client: httpx.AsyncClient, url: str, params: dict[str, str]) -> httpx.Response:
    """GET with a global gate ensuring >= NCBI_MIN_INTERVAL between requests."""
    global _last_call_monotonic
    async with _rate_lock:
        wait = NCBI_MIN_INTERVAL - (time.monotonic() - _last_call_monotonic)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_call_monotonic = time.monotonic()
    return await client.get(url, params=params)


def _params() -> dict[str, str]:
    params = {"retmode": "json", "db": "pubmed"}
    api_key = os.environ.get("NCBI_API_KEY")
    if api_key:
        params["api_key"] = api_key
    return params


async def lookup_journal(abbrev: str, *, client: httpx.AsyncClient | None = None) -> dict[str, Any]:
    """Return {"abbrev", "name", "issn"} for a journal abbreviation.

    On lookup miss (no pubmed hit), returns name=abbrev and issn="".
    Caller is responsible for catching httpx.HTTPError for upstream failures.
    """
    own_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=30.0)
    try:
        params = _params()
        search = await _gated_get(client, ESEARCH, {**params, "term": f"{abbrev}[TA]"})
        search.raise_for_status()
        ids = (search.json().get("esearchresult") or {}).get("idlist") or []
        if not ids:
            return {"abbrev": abbrev, "name": abbrev, "issn": ""}
        first_id = ids[0]

        summary = await _gated_get(client, ESUMMARY, {**params, "id": first_id})
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
