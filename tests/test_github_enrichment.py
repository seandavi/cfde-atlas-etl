"""Tests for the GitHub enrichment additions (README, CITATION.cff, community profile)."""

from __future__ import annotations

import base64

import httpx
import pytest
from pytest_httpx import HTTPXMock

from cfde_atlas_etl.sinks.github import _extract_doi, _extract_pmid
from cfde_atlas_etl.sources.github import (
    README_MAX_BYTES,
    REST_BASE,
    get_citation_cff,
    get_community_profile,
    get_readme,
    get_workflow_files_count,
)


@pytest.mark.asyncio
async def test_get_readme_decodes_base64(httpx_mock: HTTPXMock) -> None:
    encoded = base64.b64encode(b"# Hello\n\nProject docs.").decode()
    httpx_mock.add_response(
        method="GET",
        url=f"{REST_BASE}/repos/foo/bar/readme",
        json={"path": "README.md", "sha": "abc", "content": encoded, "encoding": "base64"},
    )
    async with httpx.AsyncClient(timeout=5.0) as client:
        result = await get_readme("foo", "bar", client=client)
    assert result is not None
    assert result["content"] == "# Hello\n\nProject docs."
    assert result["truncated"] is False
    assert result["path"] == "README.md"


@pytest.mark.asyncio
async def test_get_readme_truncates_long_content(httpx_mock: HTTPXMock) -> None:
    big = ("A" * (README_MAX_BYTES + 1000)).encode()
    encoded = base64.b64encode(big).decode()
    httpx_mock.add_response(
        method="GET",
        url=f"{REST_BASE}/repos/foo/bar/readme",
        json={"path": "README.md", "sha": "abc", "content": encoded, "encoding": "base64"},
    )
    async with httpx.AsyncClient(timeout=5.0) as client:
        result = await get_readme("foo", "bar", client=client)
    assert result is not None
    assert result["truncated"] is True
    assert len(result["content"] or "") == README_MAX_BYTES


@pytest.mark.asyncio
async def test_get_readme_returns_none_on_404(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=f"{REST_BASE}/repos/foo/bar/readme",
        status_code=404,
        json={"message": "Not Found"},
    )
    async with httpx.AsyncClient(timeout=5.0) as client:
        assert await get_readme("foo", "bar", client=client) is None


@pytest.mark.asyncio
async def test_get_community_profile_returns_files(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=f"{REST_BASE}/repos/foo/bar/community/profile",
        json={
            "files": {
                "readme": {"url": "..."},
                "contributing": None,
                "code_of_conduct": {"url": "..."},
                "license": {"url": "..."},
            }
        },
    )
    async with httpx.AsyncClient(timeout=5.0) as client:
        result = await get_community_profile("foo", "bar", client=client)
    files = result["files"]
    assert files["readme"] is not None
    assert files["contributing"] is None


@pytest.mark.asyncio
async def test_get_citation_cff_parses_yaml(httpx_mock: HTTPXMock) -> None:
    cff = """
cff-version: 1.2.0
title: My Tool
version: 1.0.0
identifiers:
  - type: doi
    value: 10.1234/abc
preferred-citation:
  title: A paper
  journal: Nature
  year: 2024
  pmid: 12345678
"""
    encoded = base64.b64encode(cff.encode()).decode()
    httpx_mock.add_response(
        method="GET",
        url=f"{REST_BASE}/repos/foo/bar/contents/CITATION.cff",
        json={"content": encoded, "encoding": "base64"},
    )
    async with httpx.AsyncClient(timeout=5.0) as client:
        parsed = await get_citation_cff("foo", "bar", client=client)
    assert parsed is not None
    assert parsed["title"] == "My Tool"
    assert _extract_doi(parsed) == "10.1234/abc"
    assert _extract_pmid(parsed) == 12345678


def test_extract_doi_falls_back_through_identifiers() -> None:
    cff = {"identifiers": [{"type": "doi", "value": "10.5/foo"}]}
    assert _extract_doi(cff) == "10.5/foo"


def test_extract_doi_returns_none_when_absent() -> None:
    assert _extract_doi({}) is None
    assert _extract_pmid({}) is None


@pytest.mark.asyncio
async def test_get_workflow_files_count_returns_count(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=f"{REST_BASE}/repos/foo/bar/contents/.github/workflows",
        json=[
            {"name": "ci.yml", "type": "file"},
            {"name": "release.yml", "type": "file"},
            {"name": "scripts", "type": "dir"},
        ],
    )
    async with httpx.AsyncClient(timeout=5.0) as client:
        assert await get_workflow_files_count("foo", "bar", client=client) == 2


@pytest.mark.asyncio
async def test_get_workflow_files_count_returns_zero_on_404(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=f"{REST_BASE}/repos/foo/bar/contents/.github/workflows",
        status_code=404,
        json={"message": "Not Found"},
    )
    async with httpx.AsyncClient(timeout=5.0) as client:
        assert await get_workflow_files_count("foo", "bar", client=client) == 0
