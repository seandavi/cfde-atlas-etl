"""Prefect flow: DRC TSV manifests -> raw.drc_{dcc,file,code}.

Three independent subflows, run in parallel since none depend on each other.
"""

from __future__ import annotations

import asyncio

import httpx
from prefect import flow, get_run_logger, task

from cfde_atlas_etl.models.drc import DrcCodeAsset, DrcDccAsset, DrcFileAsset
from cfde_atlas_etl.sinks.postgres import (
    upsert_raw_drc_code,
    upsert_raw_drc_dcc,
    upsert_raw_drc_file,
)
from cfde_atlas_etl.sources.drc import fetch as fetch_drc


@task(retries=2, retry_delay_seconds=30)
async def load_dcc_assets(client: httpx.AsyncClient) -> int:
    rows = await fetch_drc("dcc", client=client)
    records = [DrcDccAsset.model_validate(r) for r in rows if r.get("link")]
    return await upsert_raw_drc_dcc(records)


@task(retries=2, retry_delay_seconds=30)
async def load_file_assets(client: httpx.AsyncClient) -> int:
    rows = await fetch_drc("file", client=client)
    records = [DrcFileAsset.model_validate(r) for r in rows if r.get("link")]
    return await upsert_raw_drc_file(records)


@task(retries=2, retry_delay_seconds=30)
async def load_code_assets(client: httpx.AsyncClient) -> int:
    rows = await fetch_drc("code", client=client)
    records = [DrcCodeAsset.model_validate(r) for r in rows if r.get("link")]
    return await upsert_raw_drc_code(records)


@flow(name="load-drc")
async def load_drc() -> tuple[int, int, int]:
    logger = get_run_logger()
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        dcc, files, code = await asyncio.gather(
            load_dcc_assets(client),
            load_file_assets(client),
            load_code_assets(client),
        )
    logger.info("DRC: %d dcc + %d file + %d code rows upserted", dcc, files, code)
    return dcc, files, code


if __name__ == "__main__":
    asyncio.run(load_drc())
