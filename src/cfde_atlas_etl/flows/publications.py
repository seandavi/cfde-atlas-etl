"""Prefect flow: load icc-eval-core publications into raw.publications.

ELT shape:
    fetch JSON -> validate source schema -> upsert raw -> (downstream)
                                                          analytics.publications view
                                                          serves cfde-atlas
"""

from __future__ import annotations

from prefect import flow, get_run_logger, task

from cfde_atlas_etl.models.publications import IccEvalPublication
from cfde_atlas_etl.sinks.postgres import upsert_raw_publications
from cfde_atlas_etl.sources.icc_eval_core import fetch_output


@task(retries=3, retry_delay_seconds=10)
async def fetch_publications() -> list[IccEvalPublication]:
    """Fetch publications.json and validate against the source schema.

    Source validation is a guard, not a contract: it catches upstream breakage
    loud rather than silently loading malformed data into the raw layer.
    """
    raw = await fetch_output("publications.json")
    return [IccEvalPublication.model_validate(r) for r in raw]


@task
async def write_raw_publications(sources: list[IccEvalPublication]) -> int:
    return await upsert_raw_publications(sources)


@flow(name="load-publications")
async def load_publications() -> int:
    """Top-level flow: fetch -> validate source -> upsert raw layer."""
    logger = get_run_logger()

    sources = await fetch_publications()
    logger.info("Fetched %d source publications", len(sources))

    written = await write_raw_publications(sources)
    logger.info("Upserted %d raw publications", written)

    return written


if __name__ == "__main__":
    import asyncio

    asyncio.run(load_publications())
