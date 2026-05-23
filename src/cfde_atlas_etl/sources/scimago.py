"""Scimago Journal Rank CSV downloader + parser.

The Scimago "xls" export is actually a semicolon-delimited CSV. They rate-limit
and sometimes outright ban CI IPs — callers should cache the raw bytes.
"""

from __future__ import annotations

import csv
import io
from typing import Any

import httpx

RANKS_URL = "https://www.scimagojr.com/journalrank.php?out=xls"


async def fetch_csv_bytes(*, client: httpx.AsyncClient | None = None) -> bytes:
    own_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=120.0, follow_redirects=True)
    try:
        response = await client.get(RANKS_URL)
        response.raise_for_status()
        return response.content
    finally:
        if own_client:
            await client.aclose()


def parse_csv(content: bytes) -> list[dict[str, Any]]:
    """Parse the semicolon-delimited Scimago dump.

    Numeric columns arrive with comma decimal separators (European convention).
    Issn arrives as space-separated multi-issn strings; we split into a list.
    """
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    records: list[dict[str, Any]] = []
    for row in reader:
        normalized: dict[str, Any] = {}
        for k, v in row.items():
            if k is None:
                continue
            v = (v or "").strip()
            if v == "":
                normalized[k] = None
            else:
                normalized[k] = v
        # Multi-issn: "12345678, 87654321" or "1234-5678 8765-4321" depending on year.
        issn_raw = normalized.get("Issn") or ""
        issns = [
            t.replace("-", "").strip() for t in issn_raw.replace(",", " ").split() if t.strip()
        ]
        normalized["issns"] = issns
        records.append(normalized)
    return records


async def fetch(*, client: httpx.AsyncClient | None = None) -> list[dict[str, Any]]:
    content = await fetch_csv_bytes(client=client)
    return parse_csv(content)
