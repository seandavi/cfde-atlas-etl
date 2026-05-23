"""Tests for the RePORTER paginator. pytest-httpx mocks all network."""

from __future__ import annotations

import json

import httpx
import pytest

from cfde_atlas_etl.sources.reporter import BASE_URL, search_all


@pytest.mark.asyncio
async def test_search_paginates_until_meta_total(httpx_mock: object) -> None:
    # pytest-httpx fixture type is opaque; cast for typecheckers
    from pytest_httpx import HTTPXMock

    assert isinstance(httpx_mock, HTTPXMock)

    url = f"{BASE_URL}/projects/search"
    page_size = 500

    def make_page(offset: int, total: int) -> dict[str, object]:
        remaining = max(0, total - offset)
        n = min(remaining, page_size)
        return {
            "meta": {"total": total},
            "results": [{"project_num": f"P{offset + i:05d}"} for i in range(n)],
        }

    total = 750
    httpx_mock.add_response(method="POST", url=url, json=make_page(0, total))
    httpx_mock.add_response(method="POST", url=url, json=make_page(500, total))

    async with httpx.AsyncClient(timeout=5.0) as client:
        records = await search_all(
            "projects", {"opportunity_numbers": ["RFA-RM-24-006"]}, client=client
        )

    assert len(records) == total
    assert records[0]["project_num"] == "P00000"
    assert records[-1]["project_num"] == "P00749"


@pytest.mark.asyncio
async def test_search_stops_when_results_empty(httpx_mock: object) -> None:
    from pytest_httpx import HTTPXMock

    assert isinstance(httpx_mock, HTTPXMock)

    url = f"{BASE_URL}/projects/search"
    httpx_mock.add_response(method="POST", url=url, json={"meta": {"total": 0}, "results": []})

    async with httpx.AsyncClient(timeout=5.0) as client:
        records = await search_all("projects", {"opportunity_numbers": []}, client=client)

    assert records == []


@pytest.mark.asyncio
async def test_search_sends_offset_and_limit(httpx_mock: object) -> None:
    from pytest_httpx import HTTPXMock

    assert isinstance(httpx_mock, HTTPXMock)

    url = f"{BASE_URL}/publications/search"
    httpx_mock.add_response(
        method="POST", url=url, json={"meta": {"total": 1}, "results": [{"pmid": 1}]}
    )

    async with httpx.AsyncClient(timeout=5.0) as client:
        await search_all("publications", {"core_project_nums": ["U54OD036472"]}, client=client)

    sent = httpx_mock.get_requests()[0]
    body = json.loads(sent.content)
    assert body["limit"] == 500
    assert body["offset"] == 0
    assert body["criteria"] == {"core_project_nums": ["U54OD036472"]}
