"""GitHub REST + GraphQL client.

Auth: GITHUB_TOKEN env. Without one, GitHub allows 60 req/hr unauthenticated;
this flow will hit the limit immediately. Always set GITHUB_TOKEN in prod.

This module is intentionally thin — it returns raw decoded JSON so the flow
can store it as jsonb. Pagination follows Link headers.

Rate limits: 5000 req/hr authenticated. Use a small concurrency cap in the
flow; this module does no global throttling.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any

import httpx

REST_BASE = "https://api.github.com"
GRAPHQL_URL = "https://api.github.com/graphql"

USER_AGENT = "cfde-atlas-etl/0.1 (+https://github.com/seandavi/cfde-atlas-etl)"


def _headers(*, accept: str = "application/vnd.github+json") -> dict[str, str]:
    headers = {
        "Accept": accept,
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _next_link(link_header: str | None) -> str | None:
    if not link_header:
        return None
    for part in link_header.split(","):
        segments = part.strip().split(";")
        if len(segments) < 2:
            continue
        url_part = segments[0].strip()
        rel_part = segments[1].strip()
        if rel_part == 'rel="next"' and url_part.startswith("<") and url_part.endswith(">"):
            return url_part[1:-1]
    return None


async def _paginate(
    url: str,
    *,
    client: httpx.AsyncClient,
    params: dict[str, Any] | None = None,
    accept: str = "application/vnd.github+json",
) -> AsyncIterator[dict[str, Any]]:
    next_url: str | None = url
    next_params: dict[str, Any] | None = params
    while next_url:
        response = await client.get(next_url, params=next_params, headers=_headers(accept=accept))
        response.raise_for_status()
        # GitHub returns 204 No Content (empty body) for endpoints like
        # /contributors when the repo has no recorded contributors. Treat as
        # empty iteration rather than letting json() raise.
        if response.status_code == 204 or not response.content:
            return
        payload = response.json()
        items = payload if isinstance(payload, list) else payload.get("items") or []
        for item in items:
            yield item
        next_url = _next_link(response.headers.get("link"))
        next_params = None


async def search_repos(query: str, *, client: httpx.AsyncClient) -> list[dict[str, Any]]:
    """Search GitHub repositories for a free-text query (e.g. a core_project_number)."""
    results: list[dict[str, Any]] = []
    async for item in _paginate(
        f"{REST_BASE}/search/repositories",
        client=client,
        params={"q": query, "per_page": 100},
    ):
        results.append(item)
    return results


async def get_repo(owner: str, name: str, *, client: httpx.AsyncClient) -> dict[str, Any]:
    response = await client.get(f"{REST_BASE}/repos/{owner}/{name}", headers=_headers())
    response.raise_for_status()
    if not response.content:
        return {}
    return response.json()


async def get_stargazers(
    owner: str, name: str, *, client: httpx.AsyncClient
) -> list[dict[str, Any]]:
    """Per-star timestamps require the v3.star+json accept header."""
    results: list[dict[str, Any]] = []
    async for item in _paginate(
        f"{REST_BASE}/repos/{owner}/{name}/stargazers",
        client=client,
        params={"per_page": 100},
        accept="application/vnd.github.v3.star+json",
    ):
        results.append(item)
    return results


async def get_forks(owner: str, name: str, *, client: httpx.AsyncClient) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    async for item in _paginate(
        f"{REST_BASE}/repos/{owner}/{name}/forks",
        client=client,
        params={"per_page": 100},
    ):
        results.append(item)
    return results


async def get_commits(owner: str, name: str, *, client: httpx.AsyncClient) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    async for item in _paginate(
        f"{REST_BASE}/repos/{owner}/{name}/commits",
        client=client,
        params={"per_page": 100},
    ):
        results.append(item)
    return results


async def get_issues(owner: str, name: str, *, client: httpx.AsyncClient) -> list[dict[str, Any]]:
    """All issues incl. PRs (REST treats PRs as a sub-type of issue)."""
    results: list[dict[str, Any]] = []
    async for item in _paginate(
        f"{REST_BASE}/repos/{owner}/{name}/issues",
        client=client,
        params={"state": "all", "per_page": 100},
    ):
        results.append(item)
    return results


async def get_contributors(
    owner: str, name: str, *, client: httpx.AsyncClient
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    async for item in _paginate(
        f"{REST_BASE}/repos/{owner}/{name}/contributors",
        client=client,
        params={"per_page": 100, "anon": "false"},
    ):
        results.append(item)
    return results


async def get_languages(owner: str, name: str, *, client: httpx.AsyncClient) -> dict[str, int]:
    response = await client.get(
        f"{REST_BASE}/repos/{owner}/{name}/languages",
        headers=_headers(),
    )
    response.raise_for_status()
    if not response.content:
        return {}
    return response.json()


async def get_releases(owner: str, name: str, *, client: httpx.AsyncClient) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    async for item in _paginate(
        f"{REST_BASE}/repos/{owner}/{name}/releases",
        client=client,
        params={"per_page": 100},
    ):
        results.append(item)
    return results


async def file_exists(owner: str, name: str, path: str, *, client: httpx.AsyncClient) -> bool:
    response = await client.get(
        f"{REST_BASE}/repos/{owner}/{name}/contents/{path}",
        headers=_headers(),
    )
    if response.status_code == 404:
        return False
    response.raise_for_status()
    return True


README_MAX_BYTES = 256 * 1024


async def get_readme(owner: str, name: str, *, client: httpx.AsyncClient) -> dict[str, Any] | None:
    """Fetch + decode the canonical README. Returns None when missing or binary."""
    import base64

    response = await client.get(
        f"{REST_BASE}/repos/{owner}/{name}/readme",
        headers=_headers(),
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    if not response.content:
        return None
    payload = response.json()
    encoded = (payload.get("content") or "").encode("ascii", errors="ignore")
    try:
        raw = base64.b64decode(encoded)
    except (ValueError, TypeError):
        return {
            "path": payload.get("path"),
            "sha": payload.get("sha"),
            "content": None,
            "truncated": False,
        }
    truncated = len(raw) > README_MAX_BYTES
    if truncated:
        raw = raw[:README_MAX_BYTES]
    try:
        text: str | None = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = None
    return {
        "path": payload.get("path"),
        "sha": payload.get("sha"),
        "content": text,
        "truncated": truncated,
    }


async def get_community_profile(
    owner: str, name: str, *, client: httpx.AsyncClient
) -> dict[str, Any]:
    """Returns GitHub's per-repo community-profile blob.

    Notable fields: `files.{readme,code_of_conduct,contributing,license,issue_template,pull_request_template}`.
    Each file entry is null when absent. Returns an empty dict on 404.
    """
    response = await client.get(
        f"{REST_BASE}/repos/{owner}/{name}/community/profile",
        headers=_headers(accept="application/vnd.github.scarlet-witch-preview+json"),
    )
    if response.status_code == 404:
        return {}
    response.raise_for_status()
    if not response.content:
        return {}
    return response.json()


async def get_citation_cff(
    owner: str, name: str, *, client: httpx.AsyncClient
) -> dict[str, Any] | None:
    """Fetch + parse CITATION.cff from the default branch. Returns None when absent or unparseable."""
    import base64

    import yaml

    response = await client.get(
        f"{REST_BASE}/repos/{owner}/{name}/contents/CITATION.cff",
        headers=_headers(),
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    if not response.content:
        return None
    payload = response.json()
    encoded = (payload.get("content") or "").encode("ascii", errors="ignore")
    try:
        raw = base64.b64decode(encoded).decode("utf-8")
    except (ValueError, TypeError, UnicodeDecodeError):
        return None
    try:
        parsed = yaml.safe_load(raw)
    except yaml.YAMLError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


async def get_workflow_files_count(owner: str, name: str, *, client: httpx.AsyncClient) -> int:
    """Count files in .github/workflows/. Returns 0 when directory is absent."""
    response = await client.get(
        f"{REST_BASE}/repos/{owner}/{name}/contents/.github/workflows",
        headers=_headers(),
    )
    if response.status_code == 404:
        return 0
    response.raise_for_status()
    if not response.content:
        return 0
    payload = response.json()
    if isinstance(payload, list):
        return sum(1 for f in payload if f.get("type") == "file")
    return 0
