"""Tests for the GitHub source. All network mocked with pytest-httpx."""

from __future__ import annotations

import httpx
import pytest
from pytest_httpx import HTTPXMock

from cfde_atlas_etl.sources.github import (
    REST_BASE,
    _next_link,
    file_exists,
    get_languages,
    search_repos,
)


def test_next_link_extracts_next_url_only() -> None:
    header = (
        '<https://api.github.com/x?page=2>; rel="next", '
        '<https://api.github.com/x?page=5>; rel="last"'
    )
    assert _next_link(header) == "https://api.github.com/x?page=2"


def test_next_link_returns_none_when_absent() -> None:
    assert _next_link(None) is None
    assert _next_link('<https://api.github.com/x?page=5>; rel="last"') is None


@pytest.mark.asyncio
async def test_search_repos_paginates_via_link_header(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=httpx.URL(
            f"{REST_BASE}/search/repositories", params={"q": "U54OD036472", "per_page": 100}
        ),
        json={"items": [{"id": 1, "full_name": "foo/bar"}]},
        headers={
            "link": f'<{REST_BASE}/search/repositories?q=U54OD036472&per_page=100&page=2>; rel="next"'
        },
    )
    httpx_mock.add_response(
        method="GET",
        url=f"{REST_BASE}/search/repositories?q=U54OD036472&per_page=100&page=2",
        json={"items": [{"id": 2, "full_name": "baz/qux"}]},
    )

    async with httpx.AsyncClient(timeout=5.0) as client:
        results = await search_repos("U54OD036472", client=client)

    assert [r["id"] for r in results] == [1, 2]


@pytest.mark.asyncio
async def test_get_languages_returns_dict(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=f"{REST_BASE}/repos/foo/bar/languages",
        json={"Python": 1234, "TypeScript": 567},
    )

    async with httpx.AsyncClient(timeout=5.0) as client:
        result = await get_languages("foo", "bar", client=client)

    assert result == {"Python": 1234, "TypeScript": 567}


@pytest.mark.asyncio
async def test_file_exists_404_returns_false(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=f"{REST_BASE}/repos/foo/bar/contents/CITATION.cff",
        status_code=404,
        json={"message": "Not Found"},
    )

    async with httpx.AsyncClient(timeout=5.0) as client:
        assert await file_exists("foo", "bar", "CITATION.cff", client=client) is False


@pytest.mark.asyncio
async def test_file_exists_200_returns_true(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=f"{REST_BASE}/repos/foo/bar/contents/README.md",
        json={"name": "README.md"},
    )

    async with httpx.AsyncClient(timeout=5.0) as client:
        assert await file_exists("foo", "bar", "README.md", client=client) is True
