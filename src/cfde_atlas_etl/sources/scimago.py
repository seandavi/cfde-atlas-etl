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

# Scimago serves 403 to default httpx User-Agent and to anything that smells
# like a bot. Use a desktop browser UA. Cache the bytes locally on success so
# repeat runs do not need to hit Scimago at all.
BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": BROWSER_UA,
    "Accept": "text/csv,application/vnd.ms-excel,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}


async def fetch_csv_bytes(*, client: httpx.AsyncClient | None = None) -> bytes:
    own_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=120.0, follow_redirects=True)
    try:
        response = await client.get(RANKS_URL, headers=HEADERS)
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
