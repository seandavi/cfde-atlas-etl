"""Prefect flow: fetch project-side detail for downstream citing grants.

Pipeline:
1. Read distinct downstream core_project_numbers from raw.reporter_citing_publications.
2. POST RePORTER /v2/projects/search with criteria.project_nums (chunked).
3. Upsert into raw.reporter_citing_projects.

Surfaces PI, institution, mechanism, and award amount for downstream grants
through analytics.citing_grant_details + analytics.citing_grants_full.
"""

from __future__ import annotations

import asyncio

import psycopg
from prefect import flow, get_run_logger, task

from cfde_atlas_etl.config import get_settings
from cfde_atlas_etl.models.project import ReporterProject
from cfde_atlas_etl.sinks.postgres import upsert_raw_reporter_citing_projects
from cfde_atlas_etl.sources.reporter import search_all as reporter_search_all

# RePORTER /v2/projects/search returns 400 on project_nums arrays larger than
# ~200 in practice (docs don't pin it). Stay well under.
CORE_PROJECT_CHUNK = 100
# 7000+ downstream cores → ~70 chunks. Cap concurrency so RePORTER doesn't 429.
CONCURRENCY = 4


@task
async def load_downstream_core_project_numbers() -> list[str]:
    settings = get_settings()
    async with (
        await psycopg.AsyncConnection.connect(settings.database_url) as conn,
        conn.cursor() as cur,
    ):
        await cur.execute(
            "SELECT DISTINCT core_project_number FROM raw.reporter_citing_publications "
            "WHERE core_project_number IS NOT NULL ORDER BY core_project_number"
        )
        rows = await cur.fetchall()
    return [r[0] for r in rows]


@task(retries=3, retry_delay_seconds=15)
async def search_chunk(core_project_numbers: list[str]) -> list[ReporterProject]:
    if not core_project_numbers:
        return []
    raw = await reporter_search_all("projects", {"project_nums": core_project_numbers})
    return [ReporterProject.model_validate(r) for r in raw]


@task
async def write_citing_projects(records: list[ReporterProject]) -> int:
    return await upsert_raw_reporter_citing_projects(records)


@flow(name="load-citing-grant-details")
async def load_citing_grant_details() -> int:
    logger = get_run_logger()

    cores = await load_downstream_core_project_numbers()
    logger.info("Resolving project-side detail for %d downstream core projects", len(cores))

    chunks = [cores[i : i + CORE_PROJECT_CHUNK] for i in range(0, len(cores), CORE_PROJECT_CHUNK)]
    sem = asyncio.Semaphore(CONCURRENCY)

    async def bounded(chunk: list[str]) -> list[ReporterProject]:
        async with sem:
            return await search_chunk(chunk)

    results: list[list[ReporterProject]] = await asyncio.gather(*(bounded(c) for c in chunks))
    flattened: list[ReporterProject] = [rec for batch in results for rec in batch]
    logger.info("Fetched %d downstream project records", len(flattened))

    written = await write_citing_projects(flattened)
    logger.info("Upserted %d rows into raw.reporter_citing_projects", written)
    return written


if __name__ == "__main__":
    asyncio.run(load_citing_grant_details())
