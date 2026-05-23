"""NIH iCite /api/pubs client.

Chunks pmid lists into batches of 1000 (the API's max). Returns one dict per
pmid.

API: https://icite.od.nih.gov/api
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from typing import Any

import httpx

ENDPOINT = "https://icite.od.nih.gov/api/pubs"
# 200 pmids * ~8 chars + commas + URL-encoding leaves us well under the ~8KB
# request URI cap; iCite documents 1000 but a GET with that many pmids 414s.
CHUNK_SIZE = 200


def _chunked(items: list[int], n: int) -> Iterable[list[int]]:
    for i in range(0, len(items), n):
        yield items[i : i + n]


async def fetch(
    pmids: Iterable[int],
    *,
    client: httpx.AsyncClient | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Yield iCite records for the given pmids. De-duplicates input pmids."""
    unique = sorted({int(p) for p in pmids if p})
    if not unique:
        return

    own_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=60.0)

    try:
        for chunk in _chunked(unique, CHUNK_SIZE):
            response = await client.get(
                ENDPOINT,
                params={"pmids": ",".join(str(p) for p in chunk), "fl": "all"},
            )
            response.raise_for_status()
            payload = response.json()
            for record in payload.get("data") or []:
                yield record
    finally:
        if own_client:
            await client.aclose()


async def fetch_all(
    pmids: Iterable[int],
    *,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    return [r async for r in fetch(pmids, client=client)]
