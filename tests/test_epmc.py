"""Tests for the Europe PMC query builder and client. pytest-httpx mocks all network."""

from __future__ import annotations

import httpx
import pytest
from pytest_httpx import HTTPXMock

from cfde_atlas_etl.sources.epmc import (
    BASE_URL,
    EpmcHit,
    build_query,
    full_text_xml,
    hit_count,
    search,
)

W = (2015, 2025)

# Oracle strings from the Eval team's Kids First Query_Summary sheet.
ORACLES = [
    (dict(term="*DE030062"), "(*DE030062 AND (FIRST_PDATE:[2015 TO 2025]))"),
    (
        dict(term="Kids First Data Resource Center", section="Methods"),
        '(METHODS:("Kids First Data Resource Center") AND (FIRST_PDATE:[2015 TO 2025]))',
    ),
    (
        dict(term="portal.kidsfirstdrc.org"),
        '("portal.kidsfirstdrc.org" AND (FIRST_PDATE:[2015 TO 2025]))',
    ),
    (
        dict(term="Cavatica", and_terms="Kids First"),
        '("Cavatica" AND "Kids First" AND (FIRST_PDATE:[2015 TO 2025]))',
    ),
    (
        dict(term="37788089_med", section="Cites"),
        "(CITES:(37788089_med) AND (FIRST_PDATE:[2015 TO 2025]))",
    ),
    (dict(term="phs002517"), "(phs002517 AND (FIRST_PDATE:[2015 TO 2025]))"),
    (
        dict(term="Gabriella Miller Kids First", section="Title and Abstract"),
        '(TITLE_ABS:("Gabriella Miller Kids First") AND (FIRST_PDATE:[2015 TO 2025]))',
    ),
    # Eval team inputs arrive pre-quoted; must render identically.
    (
        dict(term='"Cavatica"', and_terms='"Kids First"'),
        '("Cavatica" AND "Kids First" AND (FIRST_PDATE:[2015 TO 2025]))',
    ),
]


@pytest.mark.parametrize(("kwargs", "expected"), ORACLES)
def test_build_query_oracles(kwargs: dict[str, str], expected: str) -> None:
    assert build_query(**kwargs, date_window=W) == expected


def test_build_query_comma_or() -> None:
    assert build_query("4D nucleome, 4DN") == '(("4D nucleome" OR 4DN))'
    assert (
        build_query("4D nucleome, 4DN", "Title and Abstract", date_window=W)
        == '(TITLE_ABS:("4D nucleome" OR 4DN) AND (FIRST_PDATE:[2015 TO 2025]))'
    )


def test_build_query_not_and_or_groups() -> None:
    assert (
        build_query(
            "OligoSTORM",
            "Methods",
            or_terms="ORCA",
            not_terms="Review",
            not_section="Publication Type",
            date_window=W,
        )
        == '(METHODS:("OligoSTORM") OR "ORCA" NOT PUB_TYPE:("Review") AND (FIRST_PDATE:[2015 TO 2025]))'
    )


def _page(ids: list[str], next_cursor: str) -> dict[str, object]:
    return {
        "hitCount": 3,
        "nextCursorMark": next_cursor,
        "resultList": {"result": [{"id": i, "source": "MED"} for i in ids]},
    }


async def test_search_follows_cursor_until_repeat(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(json=_page(["1", "2"], "AoE"))
    httpx_mock.add_response(json=_page(["3"], "AoE"))

    async with httpx.AsyncClient() as client:
        got = [r["id"] async for r in search("x", client=client)]

    assert got == ["1", "2", "3"]
    assert [r.url.params["cursorMark"] for r in httpx_mock.get_requests()] == ["*", "AoE"]
    first = httpx_mock.get_requests()[0].url.params
    assert first["format"] == "json"
    assert first["pageSize"] == "1000"
    assert first["resultType"] == "lite"


async def test_search_retries_on_5xx(
    httpx_mock: HTTPXMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cfde_atlas_etl.sources.epmc as m

    async def no_sleep(_: float) -> None:
        pass

    monkeypatch.setattr(m.asyncio, "sleep", no_sleep)
    httpx_mock.add_response(status_code=503)
    httpx_mock.add_response(json=_page(["1"], "*"))
    async with httpx.AsyncClient() as client:
        assert [r["id"] async for r in search("x", client=client)] == ["1"]


async def test_hit_count(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(json={"hitCount": 29, "resultList": {"result": []}})
    async with httpx.AsyncClient() as client:
        assert await hit_count("x", client=client) == 29
    assert httpx_mock.get_requests()[0].url.params["pageSize"] == "1"


async def test_full_text_xml_404_is_none(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=f"{BASE_URL}/PMC1/fullTextXML", status_code=404)
    httpx_mock.add_response(url=f"{BASE_URL}/PMC2/fullTextXML", text="<article/>")
    async with httpx.AsyncClient() as client:
        assert await full_text_xml("PMC1", client=client) is None
        assert await full_text_xml("PMC2", client=client) == "<article/>"


def test_epmc_hit_from_result() -> None:
    hit = EpmcHit.from_result(
        {
            "id": "1",
            "source": "MED",
            "pmid": "1",
            "pmcid": "PMC9",
            "pubYear": "2020",
            "isOpenAccess": "Y",
            "title": "T",
        }
    )
    assert hit.pub_year == 2020
    assert hit.is_open_access is True
    assert EpmcHit.from_result({"id": "PPR1", "source": "PPR"}).is_open_access is False
