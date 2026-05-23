"""NIH RePORTER v2 API client.

Generic paginator used by both projects and publications flows.

API docs: https://api.reporter.nih.gov/
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Literal

import httpx

BASE_URL = "https://api.reporter.nih.gov/v2"
PAGE_SIZE = 500
HARD_PAGE_LIMIT = 50  # safety cap; v2 hard-limits offset+limit < 14_999

Endpoint = Literal["projects", "publications"]


async def search(
    endpoint: Endpoint,
    criteria: dict[str, Any],
    *,
    client: httpx.AsyncClient | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Page through every result for a RePORTER search.

    Yields one record per result. Caller drains the iterator.

    Example:
        async for project in search("projects", {"opportunity_numbers": ["RFA-RM-24-006"]}):
            ...
    """
    url = f"{BASE_URL}/{endpoint}/search"
    own_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=60.0)

    try:
        for page in range(HARD_PAGE_LIMIT):
            offset = page * PAGE_SIZE
            body = {"criteria": criteria, "limit": PAGE_SIZE, "offset": offset}
            response = await client.post(
                url,
                json=body,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            )
            response.raise_for_status()
            payload = response.json()
            results: list[dict[str, Any]] = payload.get("results") or []
            for record in results:
                yield record
            total = (payload.get("meta") or {}).get("total") or 0
            if offset + PAGE_SIZE >= total:
                return
    finally:
        if own_client:
            await client.aclose()


async def search_all(
    endpoint: Endpoint,
    criteria: dict[str, Any],
    *,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    """Convenience: materialize search() into a list."""
    return [r async for r in search(endpoint, criteria, client=client)]
