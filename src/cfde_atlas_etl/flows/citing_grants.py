"""Prefect flow: NIH grants supporting publications that cite CFDE work.

Pipeline:
1. Read distinct citing_pmids from raw.icite_citations (populated by #12).
2. Query RePORTER /v2/publications/search in chunks of 1000 pmids per call
   (RePORTER's criteria.pmids can take large arrays but we keep chunks
   modest to bound per-request size and improve retry granularity).
3. Upsert each (citing_pmid, downstream_core_project_number) into
   raw.reporter_citing_publications.
"""

from __future__ import annotations

import asyncio

import psycopg
from prefect import flow, get_run_logger, task

from cfde_atlas_etl.config import get_settings
from cfde_atlas_etl.models.publication import ReporterPublication
from cfde_atlas_etl.sinks.postgres import upsert_raw_reporter_citing_publications
from cfde_atlas_etl.sources.reporter import search_all as reporter_search_all

PMID_CHUNK = 1000


@task
async def load_citing_pmids() -> list[int]:
    settings = get_settings()
    async with (
        await psycopg.AsyncConnection.connect(settings.database_url) as conn,
        conn.cursor() as cur,
    ):
        await cur.execute(
            "SELECT DISTINCT citing_pmid FROM raw.icite_citations ORDER BY citing_pmid"
        )
        rows = await cur.fetchall()
    return [int(r[0]) for r in rows]


@task(retries=3, retry_delay_seconds=15)
async def search_chunk(pmids: list[int]) -> list[ReporterPublication]:
    raw = await reporter_search_all("publications", {"pmids": pmids})
    return [ReporterPublication.model_validate(r) for r in raw]


@task
async def write_citing_grants(records: list[ReporterPublication]) -> int:
    return await upsert_raw_reporter_citing_publications(records)


@flow(name="load-citing-grants")
async def load_citing_grants() -> int:
    logger = get_run_logger()

    pmids = await load_citing_pmids()
    logger.info("Looking up RePORTER grants for %d citing pmids", len(pmids))

    chunks = [pmids[i : i + PMID_CHUNK] for i in range(0, len(pmids), PMID_CHUNK)]
    results: list[list[ReporterPublication]] = await asyncio.gather(
        *(search_chunk(chunk) for chunk in chunks)
    )
    flattened: list[ReporterPublication] = [rec for batch in results for rec in batch]
    logger.info("Fetched %d (pmid, core_project_number) grant rows", len(flattened))

    written = await write_citing_grants(flattened)
    logger.info("Upserted %d rows into raw.reporter_citing_publications", written)
    return written


if __name__ == "__main__":
    asyncio.run(load_citing_grants())
