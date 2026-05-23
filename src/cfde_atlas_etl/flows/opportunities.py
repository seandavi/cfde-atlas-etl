"""Prefect flow: load PR-curated FOAs from config.yaml into raw.opportunities.

The commonfund.nih.gov scrape was removed in favor of a static curated list
(see issue #33 and config.yaml). When a new CFDE FOA is announced, add it
to config.yaml in a PR.
"""

from __future__ import annotations

from prefect import flow, get_run_logger, task

from cfde_atlas_etl.curated import load_opportunities as load_opportunities_yaml
from cfde_atlas_etl.models.opportunity import CommonFundOpportunity
from cfde_atlas_etl.sinks.postgres import upsert_raw_opportunities


@task
def read_curated_opportunities() -> list[CommonFundOpportunity]:
    return load_opportunities_yaml()


@task
async def write_raw_opportunities(records: list[CommonFundOpportunity]) -> int:
    return await upsert_raw_opportunities(records)


@flow(name="load-opportunities")
async def load_opportunities_flow() -> int:
    logger = get_run_logger()

    records = read_curated_opportunities()
    logger.info("Loaded %d curated opportunities from config.yaml", len(records))

    written = await write_raw_opportunities(records)
    logger.info("Upserted %d rows into raw.opportunities", written)

    return written


# Backwards-compatible alias used by flows.load_all.
load_opportunities = load_opportunities_flow


if __name__ == "__main__":
    import asyncio

    asyncio.run(load_opportunities_flow())
