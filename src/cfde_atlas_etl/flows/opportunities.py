"""Prefect flow: scrape Common Fund FOAs and upsert into raw.opportunities."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from prefect import flow, get_run_logger, task

from cfde_atlas_etl.models.opportunity import CommonFundOpportunity
from cfde_atlas_etl.sinks.postgres import upsert_raw_opportunities
from cfde_atlas_etl.sources.commonfund import gather_opportunities

MANUAL_OPPORTUNITIES_PATH = Path("raw/manual-opportunities.yaml")


@task(retries=3, retry_delay_seconds=10)
async def scrape_opportunities() -> list[CommonFundOpportunity]:
    raw = await gather_opportunities()
    return [CommonFundOpportunity.model_validate(r) for r in raw]


@task
def load_manual_opportunities(
    path: Path = MANUAL_OPPORTUNITIES_PATH,
) -> list[CommonFundOpportunity]:
    if not path.exists():
        return []
    payload: dict[str, Any] = yaml.safe_load(path.read_text()) or {}
    items = payload.get("opportunities") or []
    return [CommonFundOpportunity.model_validate(r) for r in items]


@task
def merge_opportunities(
    scraped: list[CommonFundOpportunity],
    manual: list[CommonFundOpportunity],
) -> list[CommonFundOpportunity]:
    """Manual overrides win when ids collide."""
    by_id: dict[str, CommonFundOpportunity] = {o.id: o for o in scraped}
    for o in manual:
        by_id[o.id] = o
    return list(by_id.values())


@task
async def write_raw_opportunities(records: list[CommonFundOpportunity]) -> int:
    return await upsert_raw_opportunities(records)


@flow(name="load-opportunities")
async def load_opportunities() -> int:
    logger = get_run_logger()

    scraped = await scrape_opportunities()
    logger.info("Scraped %d opportunities from commonfund.nih.gov", len(scraped))

    manual = load_manual_opportunities()
    logger.info("Loaded %d manual opportunities", len(manual))

    merged = merge_opportunities(scraped, manual)
    logger.info("Merged to %d unique opportunities", len(merged))

    written = await write_raw_opportunities(merged)
    logger.info("Upserted %d rows into raw.opportunities", written)

    return written


if __name__ == "__main__":
    import asyncio

    asyncio.run(load_opportunities())
