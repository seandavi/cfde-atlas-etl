"""Postgres sinks for the GitHub raw layer.

Kept in a separate module from sinks.postgres to avoid bloating that file —
GitHub introduces 9 upsert helpers.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from cfde_atlas_etl.sinks.postgres import _executemany

UPSERT_REPOS = """
INSERT INTO raw.github_repos (repo_id, full_name, source, fetched_at)
VALUES (%(repo_id)s, %(full_name)s, %(source)s, NOW())
ON CONFLICT (repo_id) DO UPDATE SET
    full_name = EXCLUDED.full_name,
    source = EXCLUDED.source,
    fetched_at = NOW();
"""

UPSERT_REPO_CORE_LINKS = """
INSERT INTO raw.github_repo_core_projects (repo_id, core_project_number, discovered_at)
VALUES (%(repo_id)s, %(core_project_number)s, NOW())
ON CONFLICT (repo_id, core_project_number) DO UPDATE SET discovered_at = NOW();
"""

UPSERT_STARS = """
INSERT INTO raw.github_stars (repo_id, user_id, starred_at, source, fetched_at)
VALUES (%(repo_id)s, %(user_id)s, %(starred_at)s, %(source)s, NOW())
ON CONFLICT (repo_id, user_id) DO UPDATE SET
    starred_at = EXCLUDED.starred_at,
    source = EXCLUDED.source,
    fetched_at = NOW();
"""

UPSERT_FORKS = """
INSERT INTO raw.github_forks (fork_id, parent_repo_id, created_at, source, fetched_at)
VALUES (%(fork_id)s, %(parent_repo_id)s, %(created_at)s, %(source)s, NOW())
ON CONFLICT (fork_id) DO UPDATE SET
    parent_repo_id = EXCLUDED.parent_repo_id,
    created_at = EXCLUDED.created_at,
    source = EXCLUDED.source,
    fetched_at = NOW();
"""

UPSERT_COMMITS = """
INSERT INTO raw.github_commits (repo_id, sha, committed_at, source, fetched_at)
VALUES (%(repo_id)s, %(sha)s, %(committed_at)s, %(source)s, NOW())
ON CONFLICT (repo_id, sha) DO UPDATE SET
    committed_at = EXCLUDED.committed_at,
    source = EXCLUDED.source,
    fetched_at = NOW();
"""

UPSERT_ISSUES = """
INSERT INTO raw.github_issues
    (repo_id, number, is_pull_request, state, created_at, closed_at, source, fetched_at)
VALUES
    (%(repo_id)s, %(number)s, %(is_pull_request)s, %(state)s, %(created_at)s, %(closed_at)s, %(source)s, NOW())
ON CONFLICT (repo_id, number) DO UPDATE SET
    is_pull_request = EXCLUDED.is_pull_request,
    state = EXCLUDED.state,
    created_at = EXCLUDED.created_at,
    closed_at = EXCLUDED.closed_at,
    source = EXCLUDED.source,
    fetched_at = NOW();
"""

UPSERT_CONTRIBUTORS = """
INSERT INTO raw.github_contributors (repo_id, login, contributions, source, fetched_at)
VALUES (%(repo_id)s, %(login)s, %(contributions)s, %(source)s, NOW())
ON CONFLICT (repo_id, login) DO UPDATE SET
    contributions = EXCLUDED.contributions,
    source = EXCLUDED.source,
    fetched_at = NOW();
"""

UPSERT_LANGUAGES = """
INSERT INTO raw.github_languages (repo_id, language, bytes, fetched_at)
VALUES (%(repo_id)s, %(language)s, %(bytes)s, NOW())
ON CONFLICT (repo_id, language) DO UPDATE SET
    bytes = EXCLUDED.bytes,
    fetched_at = NOW();
"""

UPSERT_RELEASES = """
INSERT INTO raw.github_releases
    (repo_id, tag_name, name, published_at, is_draft, is_prerelease, source, fetched_at)
VALUES
    (%(repo_id)s, %(tag_name)s, %(name)s, %(published_at)s, %(is_draft)s, %(is_prerelease)s, %(source)s, NOW())
ON CONFLICT (repo_id, tag_name) DO UPDATE SET
    name = EXCLUDED.name,
    published_at = EXCLUDED.published_at,
    is_draft = EXCLUDED.is_draft,
    is_prerelease = EXCLUDED.is_prerelease,
    source = EXCLUDED.source,
    fetched_at = NOW();
"""


def _dump(record: dict[str, Any]) -> str:
    return json.dumps(record)


async def upsert_repos(records: Iterable[dict[str, Any]]) -> int:
    payloads: list[dict[str, object]] = [
        {"repo_id": r["id"], "full_name": r["full_name"], "source": _dump(r)} for r in records
    ]
    return await _executemany(UPSERT_REPOS, payloads)


async def upsert_repo_core_links(repo_id: int, core_project_numbers: Iterable[str]) -> int:
    payloads: list[dict[str, object]] = [
        {"repo_id": repo_id, "core_project_number": c} for c in core_project_numbers
    ]
    return await _executemany(UPSERT_REPO_CORE_LINKS, payloads)


async def upsert_stars(repo_id: int, records: Iterable[dict[str, Any]]) -> int:
    payloads: list[dict[str, object]] = []
    for r in records:
        user = r.get("user") or {}
        user_id = user.get("id")
        starred_at = r.get("starred_at")
        if user_id is None or not starred_at:
            continue
        payloads.append(
            {
                "repo_id": repo_id,
                "user_id": user_id,
                "starred_at": starred_at,
                "source": _dump(r),
            }
        )
    return await _executemany(UPSERT_STARS, payloads)


async def upsert_forks(parent_repo_id: int, records: Iterable[dict[str, Any]]) -> int:
    payloads: list[dict[str, object]] = []
    for r in records:
        fork_id = r.get("id")
        created_at = r.get("created_at")
        if fork_id is None or not created_at:
            continue
        payloads.append(
            {
                "fork_id": fork_id,
                "parent_repo_id": parent_repo_id,
                "created_at": created_at,
                "source": _dump(r),
            }
        )
    return await _executemany(UPSERT_FORKS, payloads)


async def upsert_commits(repo_id: int, records: Iterable[dict[str, Any]]) -> int:
    payloads: list[dict[str, object]] = []
    for r in records:
        sha = r.get("sha")
        if not sha:
            continue
        commit = r.get("commit") or {}
        committer = commit.get("committer") or {}
        committed_at = committer.get("date")
        payloads.append(
            {
                "repo_id": repo_id,
                "sha": sha,
                "committed_at": committed_at,
                "source": _dump(r),
            }
        )
    return await _executemany(UPSERT_COMMITS, payloads)


async def upsert_issues(repo_id: int, records: Iterable[dict[str, Any]]) -> int:
    payloads: list[dict[str, object]] = []
    for r in records:
        number = r.get("number")
        if number is None:
            continue
        payloads.append(
            {
                "repo_id": repo_id,
                "number": number,
                "is_pull_request": r.get("pull_request") is not None,
                "state": r.get("state"),
                "created_at": r.get("created_at"),
                "closed_at": r.get("closed_at"),
                "source": _dump(r),
            }
        )
    return await _executemany(UPSERT_ISSUES, payloads)


async def upsert_contributors(repo_id: int, records: Iterable[dict[str, Any]]) -> int:
    payloads: list[dict[str, object]] = []
    for r in records:
        login = r.get("login")
        if not login:
            continue
        payloads.append(
            {
                "repo_id": repo_id,
                "login": login,
                "contributions": r.get("contributions") or 0,
                "source": _dump(r),
            }
        )
    return await _executemany(UPSERT_CONTRIBUTORS, payloads)


async def upsert_languages(repo_id: int, languages: dict[str, int]) -> int:
    payloads: list[dict[str, object]] = [
        {"repo_id": repo_id, "language": lang, "bytes": byts} for lang, byts in languages.items()
    ]
    return await _executemany(UPSERT_LANGUAGES, payloads)


async def upsert_releases(repo_id: int, records: Iterable[dict[str, Any]]) -> int:
    payloads: list[dict[str, object]] = []
    for r in records:
        tag = r.get("tag_name")
        if not tag:
            continue
        payloads.append(
            {
                "repo_id": repo_id,
                "tag_name": tag,
                "name": r.get("name"),
                "published_at": r.get("published_at"),
                "is_draft": bool(r.get("draft", False)),
                "is_prerelease": bool(r.get("prerelease", False)),
                "source": _dump(r),
            }
        )
    return await _executemany(UPSERT_RELEASES, payloads)
