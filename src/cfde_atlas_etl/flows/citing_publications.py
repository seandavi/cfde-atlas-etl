"""Prefect flow: forward citations of CFDE publications.

Pipeline:
1. Read cited_by lists from raw.icite (one cfde_pmid -> many citing_pmids).
2. Upsert the (cfde_pmid, citing_pmid) edges into raw.icite_citations.
3. Look up iCite metadata for the union of all citing_pmids, in chunks.
4. Upsert into raw.icite_citing_pubs.
"""

from __future__ import annotations

import asyncio
from typing import cast

import psycopg
from prefect import flow, get_run_logger, task

from cfde_atlas_etl.config import get_settings
from cfde_atlas_etl.models.publication import IcitePublication
from cfde_atlas_etl.sinks.postgres import (
    upsert_raw_icite_citations,
    upsert_raw_icite_citing_pubs,
)
from cfde_atlas_etl.sources.icite import fetch_all as icite_fetch_all


@task
async def load_citation_edges() -> list[tuple[int, int]]:
    """Pull (cfde_pmid, citing_pmid) edges out of raw.icite.source -> cited_by[]."""
    settings = get_settings()
    async with (
        await psycopg.AsyncConnection.connect(settings.database_url) as conn,
        conn.cursor() as cur,
    ):
        await cur.execute(
            "SELECT pmid, jsonb_array_elements_text(COALESCE(source -> 'cited_by', '[]'::JSONB))::INTEGER "
            "FROM raw.icite "
            "WHERE source ? 'cited_by'"
        )
        rows = await cur.fetchall()
    return [(cast(int, r[0]), cast(int, r[1])) for r in rows]


@task
async def write_edges(edges: list[tuple[int, int]]) -> int:
    return await upsert_raw_icite_citations(edges)


@task(retries=3, retry_delay_seconds=15)
async def fetch_citing_metadata(pmids: list[int]) -> list[IcitePublication]:
    if not pmids:
        return []
    raw = await icite_fetch_all(pmids)
    return [IcitePublication.model_validate(r) for r in raw]


@task
async def write_citing_pubs(records: list[IcitePublication]) -> int:
    return await upsert_raw_icite_citing_pubs(records)


@flow(name="load-citing-publications")
async def load_citing_publications() -> tuple[int, int]:
    logger = get_run_logger()

    edges = await load_citation_edges()
    logger.info("Extracted %d (cfde_pmid, citing_pmid) edges from raw.icite", len(edges))

    written_edges = await write_edges(edges)

    citing_pmids = sorted({citing for _, citing in edges})
    logger.info("Fetching iCite metadata for %d unique citing pmids", len(citing_pmids))

    citing_records = await fetch_citing_metadata(citing_pmids)
    written_pubs = await write_citing_pubs(citing_records)

    logger.info("Upserted %d edges + %d citing-pub rows", written_edges, written_pubs)
    return written_edges, written_pubs


if __name__ == "__main__":
    asyncio.run(load_citing_publications())
