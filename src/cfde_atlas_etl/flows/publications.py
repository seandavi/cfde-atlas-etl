"""Prefect flow: RePORTER + iCite -> raw.reporter_publications + raw.icite.

Replaces the legacy icc-eval-core JSON passthrough (#9). The analytics view
in migrations/0010 joins the two raw tables and is what cfde-atlas reads.
"""

from __future__ import annotations

import psycopg
from prefect import flow, get_run_logger, task

from cfde_atlas_etl.config import get_settings
from cfde_atlas_etl.models.publication import IcitePublication, ReporterPublication
from cfde_atlas_etl.sinks.postgres import upsert_raw_icite, upsert_raw_reporter_publications
from cfde_atlas_etl.sources.icite import fetch_all as icite_fetch_all
from cfde_atlas_etl.sources.reporter import search_all as reporter_search_all


@task
async def load_core_project_numbers() -> list[str]:
    """Pull distinct core_project_numbers from raw.reporter_projects (loaded by flows.projects)."""
    settings = get_settings()
    async with (
        await psycopg.AsyncConnection.connect(settings.database_url) as conn,
        conn.cursor() as cur,
    ):
        await cur.execute(
            "SELECT DISTINCT core_project_number "
            "FROM raw.reporter_projects "
            "WHERE core_project_number IS NOT NULL "
            "ORDER BY core_project_number"
        )
        rows = await cur.fetchall()
    return [row[0] for row in rows]


@task(retries=3, retry_delay_seconds=15)
async def fetch_reporter_publications(core_project_numbers: list[str]) -> list[ReporterPublication]:
    if not core_project_numbers:
        return []
    raw = await reporter_search_all("publications", {"core_project_nums": core_project_numbers})
    return [ReporterPublication.model_validate(r) for r in raw]


@task(retries=3, retry_delay_seconds=15)
async def fetch_icite(pmids: list[int]) -> list[IcitePublication]:
    if not pmids:
        return []
    raw = await icite_fetch_all(pmids)
    return [IcitePublication.model_validate(r) for r in raw]


@task
async def write_reporter_publications(records: list[ReporterPublication]) -> int:
    return await upsert_raw_reporter_publications(records)


@task
async def write_icite(records: list[IcitePublication]) -> int:
    return await upsert_raw_icite(records)


@flow(name="load-publications")
async def load_publications() -> tuple[int, int]:
    logger = get_run_logger()

    core_projects = await load_core_project_numbers()
    logger.info("Found %d core projects to query for publications", len(core_projects))

    reporter_pubs = await fetch_reporter_publications(core_projects)
    logger.info("Fetched %d RePORTER publication rows", len(reporter_pubs))

    pmids = sorted({p.pmid for p in reporter_pubs})
    icite = await fetch_icite(pmids)
    logger.info("Fetched %d iCite records", len(icite))

    written_reporter = await write_reporter_publications(reporter_pubs)
    written_icite = await write_icite(icite)
    logger.info(
        "Upserted %d rows into raw.reporter_publications and %d into raw.icite",
        written_reporter,
        written_icite,
    )

    return written_reporter, written_icite


if __name__ == "__main__":
    import asyncio

    asyncio.run(load_publications())
