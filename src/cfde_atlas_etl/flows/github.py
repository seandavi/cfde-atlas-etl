"""Prefect flow: GitHub activity per CFDE core project.

Discovery: search GitHub repositories by core_project_number. Each match
becomes one row in raw.github_repo_core_projects (many-to-many; one repo
can match multiple core projects).

Per-repo: pull repo meta, stars (with per-star timestamps), forks, commits,
issues+PRs, contributors, languages, releases.

Requires GITHUB_TOKEN in env. Without one, the unauthenticated rate limit
(60/hr) makes this flow useless.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx
import psycopg
from prefect import flow, get_run_logger, task
from prefect.cache_policies import NO_CACHE

from cfde_atlas_etl.config import get_settings
from cfde_atlas_etl.sinks.github import (
    update_features,
    upsert_citation,
    upsert_commits,
    upsert_contributors,
    upsert_forks,
    upsert_issues,
    upsert_languages,
    upsert_readme,
    upsert_releases,
    upsert_repo_core_links,
    upsert_repos,
    upsert_stars,
)
from cfde_atlas_etl.sources.github import (
    get_citation_cff,
    get_commits,
    get_community_profile,
    get_contributors,
    get_forks,
    get_issues,
    get_languages,
    get_readme,
    get_releases,
    get_repo,
    get_stargazers,
    get_workflow_files_count,
    search_repos,
)

REPO_CONCURRENCY = int(os.environ.get("CFDE_GITHUB_REPO_CONCURRENCY", "4"))
# GitHub search API has its own rate limit independent of core REST:
# 30 req/min authenticated, 10 req/min unauth. Serialize search calls
# with a wall-clock gap to stay under the cap.
SEARCH_MIN_INTERVAL = 2.1  # seconds between consecutive search calls -> ~28 req/min


@task
async def load_core_project_numbers() -> list[str]:
    settings = get_settings()
    async with (
        await psycopg.AsyncConnection.connect(settings.database_url) as conn,
        conn.cursor() as cur,
    ):
        await cur.execute(
            "SELECT DISTINCT core_project_number "
            "FROM raw.reporter_projects "
            "WHERE core_project_number IS NOT NULL"
        )
        rows = await cur.fetchall()
    return [r[0] for r in rows]


@task(retries=3, retry_delay_seconds=30, cache_policy=NO_CACHE)
async def discover_repos(
    core_project_number: str,
    client: httpx.AsyncClient,
) -> tuple[str, list[dict[str, Any]]]:
    hits = await search_repos(core_project_number, client=client)
    return core_project_number, hits


@task(retries=3, retry_delay_seconds=30, cache_policy=NO_CACHE)
async def load_repo_details(
    repo: dict[str, Any],
    discovered_under: list[str],
    client: httpx.AsyncClient,
) -> int:
    owner = (repo.get("owner") or {}).get("login")
    name = repo.get("name")
    if not owner or not name:
        return 0

    full = await get_repo(owner, name, client=client)
    repo_id = int(full["id"])

    # Split the gather into two batches so pyrefly can unify return types per batch:
    # batch_lists is uniformly list[dict[str, Any]]; languages is dict[str, int].
    stars, forks, commits, issues, contributors, releases = await asyncio.gather(
        get_stargazers(owner, name, client=client),
        get_forks(owner, name, client=client),
        get_commits(owner, name, client=client),
        get_issues(owner, name, client=client),
        get_contributors(owner, name, client=client),
        get_releases(owner, name, client=client),
    )
    languages = await get_languages(owner, name, client=client)

    await upsert_repos([full])
    await upsert_repo_core_links(repo_id, discovered_under)
    await upsert_stars(repo_id, stars)
    await upsert_forks(repo_id, forks)
    await upsert_commits(repo_id, commits)
    await upsert_issues(repo_id, issues)
    await upsert_contributors(repo_id, contributors)
    await upsert_languages(repo_id, languages)
    await upsert_releases(repo_id, releases)

    # Enrichment: README + CITATION.cff + sustainability flags.
    # Each is best-effort; per-call failure leaves the corresponding flag NULL/false.
    profile = await get_community_profile(owner, name, client=client)
    files = (profile.get("files") or {}) if isinstance(profile, dict) else {}

    readme_payload = await get_readme(owner, name, client=client)
    if readme_payload is not None:
        await upsert_readme(repo_id, readme_payload)

    cff = await get_citation_cff(owner, name, client=client)
    if cff is not None:
        await upsert_citation(repo_id, cff)

    workflow_files = await get_workflow_files_count(owner, name, client=client)

    features = {
        "has_readme": bool(files.get("readme")) or readme_payload is not None,
        "has_security": bool(files.get("security")),
        "has_contributing": bool(files.get("contributing")),
        "has_coc": bool(files.get("code_of_conduct")),
        "has_citation": cff is not None,
        "has_funding": bool(files.get("funding")),
        "workflow_files": workflow_files,
    }
    await update_features(repo_id, features)

    return repo_id


@flow(name="load-github")
async def load_github() -> int:
    logger = get_run_logger()
    if not os.environ.get("GITHUB_TOKEN"):
        logger.warning(
            "GITHUB_TOKEN not set — skipping the GitHub flow entirely. "
            "Unauthenticated GH search is capped at 60 req/hr; running this flow "
            "without a token just burns retry budget without producing rows."
        )
        return 0

    core_projects = await load_core_project_numbers()
    logger.info("Discovering GitHub repos for %d core projects", len(core_projects))

    async with httpx.AsyncClient(timeout=60.0) as client:
        # Serialize discovery — GH search caps at 30 req/min auth and concurrent
        # bursts trip 403 even with a token.
        discovery_results: list[tuple[str, list[dict[str, Any]]]] = []
        for i, cp in enumerate(core_projects):
            if i > 0:
                await asyncio.sleep(SEARCH_MIN_INTERVAL)
            try:
                discovery_results.append(await discover_repos(cp, client))
            except Exception as exc:
                logger.warning("discover_repos failed for %s: %s", cp, exc)

        # Group: repo_id -> (repo_dict, [core_project_numbers, ...])
        groups: dict[int, tuple[dict[str, Any], list[str]]] = {}
        for cp, hits in discovery_results:
            for repo in hits:
                rid = int(repo["id"])
                if rid not in groups:
                    groups[rid] = (repo, [])
                groups[rid][1].append(cp)

        logger.info(
            "Resolved %d unique repos across %d core projects", len(groups), len(core_projects)
        )

        sem = asyncio.Semaphore(REPO_CONCURRENCY)

        async def one(repo: dict[str, Any], cps: list[str]) -> int:
            async with sem:
                try:
                    return await load_repo_details(repo, cps, client)
                except Exception as exc:
                    logger.warning(
                        "load_repo_details failed for %s: %s",
                        repo.get("full_name"),
                        exc,
                    )
                    return 0

        outcomes = await asyncio.gather(*(one(r, sorted(set(cps))) for r, cps in groups.values()))
        ok = sum(1 for x in outcomes if x)

    logger.info("GitHub flow complete: %d of %d repos landed", ok, len(groups))
    return ok


if __name__ == "__main__":
    asyncio.run(load_github())
