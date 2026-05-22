"""Fetch JSON outputs from nih-cfde/icc-eval-core via raw GitHub.

The icc-eval-core repository publishes gathered evaluation data as JSON files
under /data/output/. This module pulls those files as-is. Transformation lives
in cfde_atlas_etl.transform.
"""

from __future__ import annotations

from typing import Any

import httpx

from cfde_atlas_etl.config import get_settings

OUTPUT_FILES = (
    "analytics-overview.json",
    "analytics.json",
    "core-projects.json",
    "drc-code.json",
    "drc-dcc.json",
    "drc-file.json",
    "journals.json",
    "opportunities.json",
    "pdfs.json",
    "projects.json",
    "publications.json",
    "repo-overview.json",
    "repos.json",
)


async def fetch_output(filename: str, *, client: httpx.AsyncClient | None = None) -> Any:
    """Fetch a single /data/output/*.json file from icc-eval-core.

    Args:
        filename: One of OUTPUT_FILES (e.g. "publications.json").
        client: Optional httpx.AsyncClient for connection reuse across calls.

    Returns:
        Decoded JSON. Shape depends on the source file.
    """
    if filename not in OUTPUT_FILES:
        raise ValueError(f"Unknown output file: {filename!r}. Expected one of {OUTPUT_FILES}.")

    settings = get_settings()
    url = f"{settings.icc_eval_core_output_url}/{filename}"

    if client is None:
        async with httpx.AsyncClient(timeout=60.0) as owned:
            response = await owned.get(url)
    else:
        response = await client.get(url)

    response.raise_for_status()
    return response.json()
