"""Tests for the scimago + entrez sources."""

from __future__ import annotations

import httpx
import pytest
from pytest_httpx import HTTPXMock

from cfde_atlas_etl.sources.entrez import ESEARCH, ESUMMARY, lookup_journal
from cfde_atlas_etl.sources.scimago import parse_csv

SCIMAGO_FIXTURE = (
    b"Rank;Sourceid;Title;Type;Issn;SJR;SJR Best Quartile;Country\n"
    b"1;28773;Nature;journal;0028-0836, 14764687;100,5;Q1;United Kingdom\n"
    b"2;19434;Cell;journal;00928674;90,2;Q1;United States\n"
)


def test_parse_csv_splits_multi_issn() -> None:
    records = parse_csv(SCIMAGO_FIXTURE)
    assert len(records) == 2
    nature = records[0]
    assert nature["Sourceid"] == "28773"
    assert nature["Title"] == "Nature"
    assert set(nature["issns"]) == {"00280836", "14764687"}
    cell = records[1]
    assert cell["issns"] == ["00928674"]
    assert cell["SJR"] == "90,2"


@pytest.mark.asyncio
async def test_lookup_journal_returns_full_name_and_issn(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=httpx.URL(ESEARCH, params={"retmode": "json", "db": "pubmed", "term": "Nature[TA]"}),
        json={"esearchresult": {"idlist": ["12345"]}},
    )
    httpx_mock.add_response(
        method="GET",
        url=httpx.URL(ESUMMARY, params={"retmode": "json", "db": "pubmed", "id": "12345"}),
        json={"result": {"12345": {"fulljournalname": "Nature", "essn": "1476-4687"}}},
    )

    async with httpx.AsyncClient(timeout=5.0) as client:
        result = await lookup_journal("Nature", client=client)

    assert result == {"abbrev": "Nature", "name": "Nature", "issn": "14764687"}


@pytest.mark.asyncio
async def test_lookup_journal_falls_back_when_no_pubmed_hit(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=httpx.URL(ESEARCH, params={"retmode": "json", "db": "pubmed", "term": "Bogus[TA]"}),
        json={"esearchresult": {"idlist": []}},
    )

    async with httpx.AsyncClient(timeout=5.0) as client:
        result = await lookup_journal("Bogus", client=client)

    assert result == {"abbrev": "Bogus", "name": "Bogus", "issn": ""}
