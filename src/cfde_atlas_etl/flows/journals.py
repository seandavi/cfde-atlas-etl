"""Prefect flow: Scimago + Entrez -> raw.scimago_ranks + raw.entrez_journals.

Scimago ranks are downloaded as a semicolon-CSV (one-shot, large).
Entrez per-abbrev lookups are fan-out with a small semaphore to respect
NCBI rate limits (3/s without API key, 10/s with NCBI_API_KEY).
"""

from __future__ import annotations

import asyncio
import os

import httpx
import psycopg
from prefect import flow, get_run_logger, task

from cfde_atlas_etl.config import get_settings
from cfde_atlas_etl.models.journal import EntrezJournal, ScimagoRank
from cfde_atlas_etl.sinks.postgres import upsert_raw_entrez_journals, upsert_raw_scimago_ranks
from cfde_atlas_etl.sources.entrez import lookup_journal
from cfde_atlas_etl.sources.scimago import fetch as fetch_scimago

NCBI_CONCURRENCY = 10 if os.environ.get("NCBI_API_KEY") else 3


@task
async def load_journal_abbreviations() -> list[str]:
    """Pull the distinct journal abbreviations seen in raw.icite."""
    settings = get_settings()
    async with (
        await psycopg.AsyncConnection.connect(settings.database_url) as conn,
        conn.cursor() as cur,
    ):
        await cur.execute(
            "SELECT DISTINCT source ->> 'journal' AS abbrev "
            "FROM raw.icite "
            "WHERE source ->> 'journal' IS NOT NULL "
            "ORDER BY abbrev"
        )
        rows = await cur.fetchall()
    return [row[0] for row in rows if row[0]]


@task(retries=2, retry_delay_seconds=60)
async def fetch_scimago_ranks() -> list[ScimagoRank]:
    raw = await fetch_scimago()
    records: list[ScimagoRank] = []
    for r in raw:
        sourceid = r.get("Sourceid")
        if sourceid is None:
            continue
        try:
            r["Sourceid"] = int(sourceid)
        except (TypeError, ValueError):
            continue
        records.append(ScimagoRank.model_validate(r))
    return records


@task(retries=3, retry_delay_seconds=10)
async def fetch_entrez_journals(abbrevs: list[str]) -> list[EntrezJournal]:
    if not abbrevs:
        return []
    sem = asyncio.Semaphore(NCBI_CONCURRENCY)

    async with httpx.AsyncClient(timeout=30.0) as client:

        async def one(abbrev: str) -> EntrezJournal:
            async with sem:
                payload = await lookup_journal(abbrev, client=client)
                return EntrezJournal.model_validate(payload)

        return await asyncio.gather(*(one(a) for a in abbrevs))


@task
async def write_scimago(records: list[ScimagoRank]) -> int:
    return await upsert_raw_scimago_ranks(records)


@task
async def write_entrez(records: list[EntrezJournal]) -> int:
    return await upsert_raw_entrez_journals(records)


@flow(name="load-journals")
async def load_journals() -> tuple[int, int]:
    logger = get_run_logger()

    abbrevs = await load_journal_abbreviations()
    logger.info("Resolving %d distinct journal abbreviations from raw.icite", len(abbrevs))

    scimago, entrez = await asyncio.gather(
        fetch_scimago_ranks(),
        fetch_entrez_journals(abbrevs),
    )
    logger.info("Fetched %d Scimago rows + %d Entrez rows", len(scimago), len(entrez))

    written_scimago = await write_scimago(scimago)
    written_entrez = await write_entrez(entrez)
    logger.info("Upserted %d scimago + %d entrez rows", written_scimago, written_entrez)

    return written_scimago, written_entrez


if __name__ == "__main__":
    asyncio.run(load_journals())
