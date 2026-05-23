"""CFDE DRC asset manifest downloader.

Three TSVs at cfde-drc.s3.amazonaws.com/database/files/:

- current_dcc_assets.tsv   — per-DCC asset links (e.g. linkout templates)
- current_file_assets.tsv  — file downloads (C2M2 packages, etc.)
- current_code_assets.tsv  — code/API references (smartAPI, JSON-LD, scripts)

Schemas are not formally documented; columns inferred empirically.
"""

from __future__ import annotations

import csv
import io
from typing import Any, Literal

import httpx

BASE_URL = "https://cfde-drc.s3.amazonaws.com/database/files"

AssetKind = Literal["dcc", "file", "code"]

URLS: dict[AssetKind, str] = {
    "dcc": f"{BASE_URL}/current_dcc_assets.tsv",
    "file": f"{BASE_URL}/current_file_assets.tsv",
    "code": f"{BASE_URL}/current_code_assets.tsv",
}


def parse_tsv(content: bytes) -> list[dict[str, Any]]:
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    records: list[dict[str, Any]] = []
    for row in reader:
        normalized: dict[str, Any] = {}
        for k, v in row.items():
            if k is None:
                continue
            v = (v or "").strip()
            normalized[k] = v if v != "" else None
        records.append(normalized)
    return records


async def fetch(
    kind: AssetKind,
    *,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    url = URLS[kind]
    own_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=120.0, follow_redirects=True)
    try:
        response = await client.get(url)
        response.raise_for_status()
        return parse_tsv(response.content)
    finally:
        if own_client:
            await client.aclose()
