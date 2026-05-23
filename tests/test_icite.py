"""Tests for the iCite client. pytest-httpx mocks all network."""

from __future__ import annotations

import httpx
import pytest
from pytest_httpx import HTTPXMock

from cfde_atlas_etl.sources.icite import CHUNK_SIZE, ENDPOINT, fetch_all


@pytest.mark.asyncio
async def test_fetch_all_dedupes_and_yields_records(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=f"{ENDPOINT}?pmids=1,2,3&fl=all",
        json={"data": [{"pmid": 1}, {"pmid": 2}, {"pmid": 3}]},
    )

    async with httpx.AsyncClient(timeout=5.0) as client:
        records = await fetch_all([1, 2, 2, 3, 1], client=client)

    assert [r["pmid"] for r in records] == [1, 2, 3]


@pytest.mark.asyncio
async def test_fetch_all_chunks_at_max_size(httpx_mock: HTTPXMock) -> None:
    pmids = list(range(1, CHUNK_SIZE + 2))

    # First chunk: ids 1..CHUNK_SIZE
    first_chunk = ",".join(str(p) for p in pmids[:CHUNK_SIZE])
    second_chunk = ",".join(str(p) for p in pmids[CHUNK_SIZE:])

    httpx_mock.add_response(
        method="GET",
        url=f"{ENDPOINT}?pmids={first_chunk}&fl=all",
        json={"data": [{"pmid": p} for p in pmids[:CHUNK_SIZE]]},
    )
    httpx_mock.add_response(
        method="GET",
        url=f"{ENDPOINT}?pmids={second_chunk}&fl=all",
        json={"data": [{"pmid": p} for p in pmids[CHUNK_SIZE:]]},
    )

    async with httpx.AsyncClient(timeout=5.0) as client:
        records = await fetch_all(pmids, client=client)

    assert len(records) == len(pmids)


@pytest.mark.asyncio
async def test_fetch_all_empty_input_returns_empty(httpx_mock: HTTPXMock) -> None:
    async with httpx.AsyncClient(timeout=5.0) as client:
        records = await fetch_all([], client=client)
    assert records == []
    assert httpx_mock.get_requests() == []
