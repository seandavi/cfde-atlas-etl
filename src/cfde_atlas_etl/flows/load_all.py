"""Top-level Prefect orchestration.

Dep graph:

    opportunities -> projects -> publications -> journals
                          \\                  \\
                           \\                   -> citing_publications -> citing_grants
                            -> github
                            -> ga (manual crosswalk)
    drc (independent)

Concurrent branches:
- After projects lands: publications, github launch in parallel.
- After publications lands: journals, citing_publications launch in parallel.
- citing_grants waits on citing_publications.
- ga + drc are entirely independent and run concurrently with the main chain.

A leaf flow failure is logged but does not abort the run — load_all returns
a per-flow status dict so the operator can see what succeeded.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from prefect import flow, get_run_logger

from cfde_atlas_etl.flows.citing_grant_details import load_citing_grant_details
from cfde_atlas_etl.flows.citing_grants import load_citing_grants
from cfde_atlas_etl.flows.citing_publications import load_citing_publications
from cfde_atlas_etl.flows.drc import load_drc
from cfde_atlas_etl.flows.ga import load_ga
from cfde_atlas_etl.flows.github import load_github
from cfde_atlas_etl.flows.journals import load_journals
from cfde_atlas_etl.flows.opportunities import load_opportunities
from cfde_atlas_etl.flows.projects import load_projects
from cfde_atlas_etl.flows.publications import load_publications


async def _safe(name: str, awaitable: Callable[[], Awaitable[Any]]) -> tuple[str, Any | Exception]:
    logger = get_run_logger()
    try:
        return name, await awaitable()
    except Exception as exc:
        logger.exception("Subflow %s failed: %s", name, exc)
        return name, exc


@flow(name="load-all")
async def load_all() -> dict[str, Any]:
    """Run every source flow in dep order with safe per-flow isolation."""
    logger = get_run_logger()
    results: dict[str, Any] = {}

    # Independent branches start immediately.
    drc_task = asyncio.create_task(_safe("drc", load_drc))
    ga_task = asyncio.create_task(_safe("ga", load_ga))

    # Main dependency chain.
    name, opps = await _safe("opportunities", load_opportunities)
    results[name] = opps
    if isinstance(opps, Exception):
        logger.warning("opportunities failed — skipping projects/publications/journals chain")
    else:
        name, proj = await _safe("projects", load_projects)
        results[name] = proj
        if isinstance(proj, Exception):
            logger.warning("projects failed — skipping publications/journals/github chain")
        else:
            # publications and github can run concurrently once projects is in.
            pubs_task = asyncio.create_task(_safe("publications", load_publications))
            github_task = asyncio.create_task(_safe("github", load_github))

            name, pubs = await pubs_task
            results[name] = pubs

            if isinstance(pubs, Exception):
                logger.warning("publications failed — skipping journals + citing chain")
            else:
                # journals + citing_publications fan out post-publications.
                journals_task = asyncio.create_task(_safe("journals", load_journals))
                citing_pubs_task = asyncio.create_task(
                    _safe("citing_publications", load_citing_publications)
                )

                name, citing_pubs = await citing_pubs_task
                results[name] = citing_pubs

                if isinstance(citing_pubs, Exception):
                    logger.warning("citing_publications failed — skipping citing_grants chain")
                else:
                    name, cg = await _safe("citing_grants", load_citing_grants)
                    results[name] = cg
                    if isinstance(cg, Exception):
                        logger.warning("citing_grants failed — skipping citing_grant_details")
                    else:
                        name, cgd = await _safe("citing_grant_details", load_citing_grant_details)
                        results[name] = cgd

                name, j = await journals_task
                results[name] = j

            name, gh = await github_task
            results[name] = gh

    name, drc = await drc_task
    results[name] = drc
    name, ga = await ga_task
    results[name] = ga

    summary = {
        k: ("ok" if not isinstance(v, Exception) else f"failed: {type(v).__name__}")
        for k, v in results.items()
    }
    logger.info("load_all complete. status: %s", summary)
    return results


if __name__ == "__main__":
    asyncio.run(load_all())
