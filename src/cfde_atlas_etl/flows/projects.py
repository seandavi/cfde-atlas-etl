"""Prefect flow: fetch NIH RePORTER projects + upsert into raw.reporter_projects.

Input:
- opportunity numbers from raw.opportunities (populated by flows.opportunities,
  which now reads config.yaml).
- manual core_project_nums from config.yaml's `core_projects:` section
  (those not reachable via any FOA in our curated list).

Output: one row per project_num in raw.reporter_projects.
"""

from __future__ import annotations

import psycopg
from prefect import flow, get_run_logger, task

from cfde_atlas_etl.config import get_settings
from cfde_atlas_etl.curated import load_core_projects
from cfde_atlas_etl.models.project import ReporterProject
from cfde_atlas_etl.sinks.postgres import upsert_raw_reporter_projects
from cfde_atlas_etl.sources.reporter import search_all


@task
async def load_opportunity_numbers() -> list[str]:
    """Pull the opportunity_number list from raw.opportunities (loaded by flows.opportunities)."""
    settings = get_settings()
    async with (
        await psycopg.AsyncConnection.connect(settings.database_url) as conn,
        conn.cursor() as cur,
    ):
        await cur.execute("SELECT id FROM raw.opportunities ORDER BY id")
        rows = await cur.fetchall()
    return [row[0] for row in rows]


@task
def read_curated_core_projects() -> list[str]:
    return load_core_projects()


@task(retries=3, retry_delay_seconds=15)
async def search_by_opportunities(opportunities: list[str]) -> list[ReporterProject]:
    if not opportunities:
        return []
    raw = await search_all("projects", {"opportunity_numbers": opportunities})
    return [ReporterProject.model_validate(r) for r in raw]


@task(retries=3, retry_delay_seconds=15)
async def search_by_core_projects(core_projects: list[str]) -> list[ReporterProject]:
    if not core_projects:
        return []
    raw = await search_all("projects", {"project_nums": core_projects})
    return [ReporterProject.model_validate(r) for r in raw]


@task
def dedupe_projects(*batches: list[ReporterProject]) -> list[ReporterProject]:
    by_num: dict[str, ReporterProject] = {}
    for batch in batches:
        for p in batch:
            by_num[p.project_num] = p
    return list(by_num.values())


@task
async def write_raw_projects(projects: list[ReporterProject]) -> int:
    return await upsert_raw_reporter_projects(projects)


@flow(name="load-projects")
async def load_projects() -> int:
    logger = get_run_logger()

    opportunities = await load_opportunity_numbers()
    manual_cores = read_curated_core_projects()
    logger.info(
        "Searching RePORTER with %d opportunities + %d curated core projects",
        len(opportunities),
        len(manual_cores),
    )

    by_opp = await search_by_opportunities(opportunities)
    by_core = await search_by_core_projects(manual_cores)
    merged = dedupe_projects(by_opp, by_core)
    logger.info("Fetched %d unique projects", len(merged))

    written = await write_raw_projects(merged)
    logger.info("Upserted %d rows into raw.reporter_projects", written)

    return written


if __name__ == "__main__":
    import asyncio

    asyncio.run(load_projects())
