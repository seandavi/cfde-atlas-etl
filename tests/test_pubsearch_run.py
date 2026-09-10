"""Tests for flows.pubsearch_run: run_id, query rendering, and the flow with network + DB mocked."""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from prefect.testing.utilities import prefect_test_harness

from cfde_atlas_etl.flows import pubsearch_run as mod
from cfde_atlas_etl.pubsearch.models import SeedRow
from cfde_atlas_etl.pubsearch.seeds import PROGRAMS_DIR

SEEDS = [
    SeedRow("Awardee", "OT2", "*OD030596", notes="analytics.core_projects"),
    SeedRow("User", "Program_Name", "CFDE", "Methods", and_terms="Common Fund"),
    SeedRow("Broader.Influence", "Cites_Awardee_Paper", "37788089_med", "Cites"),
]


def test_yaml_sha_is_git_blob_sha_and_deterministic() -> None:
    data = (PROGRAMS_DIR / "cfde.yaml").read_bytes()
    blob = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
    assert mod.yaml_sha("cfde") == blob == mod.yaml_sha("cfde")


def test_run_id_format() -> None:
    now = datetime(2026, 9, 10, 15, 4, 5, tzinfo=UTC)
    assert mod.make_run_id("cfde", "d50f8c8c9edab3bf", now) == "cfde-20260910T150405-d50f8c8"


def test_render_query_with_and_terms_and_window() -> None:
    assert (
        mod.render_query(SEEDS[1], (2019, 2026))
        == '(METHODS:("CFDE") AND "Common Fund" AND (FIRST_PDATE:[2019 TO 2026]))'
    )
    assert mod.render_query(SEEDS[0], None) == "(*OD030596)"


def test_query_rows_numbering_and_columns() -> None:
    rows = mod.query_rows(SEEDS, "cfde", (2019, 2026))
    assert [r["query_no"] for r in rows] == [1, 2, 3]
    assert rows[0]["epmc_query"] == "(*OD030596 AND (FIRST_PDATE:[2019 TO 2026]))"
    assert rows[0]["hit_count"] is None
    assert rows[1]["and_search_field"] == "" and rows[1]["program"] == "cfde"


@pytest.fixture(scope="module")
def prefect() -> Iterator[None]:
    with prefect_test_harness():
        yield


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """No network, no DB: hits per query = query_no rows; sinks record what they were given."""
    calls: dict[str, Any] = {"runs": [], "queries": {}, "hits": {}, "finished": []}

    async def build_seeds(program: str) -> list[SeedRow]:
        return SEEDS

    async def hit_count(query: str, *, client: Any = None) -> int:
        return int(query[1]) if query[1].isdigit() else 0

    async def search(query: str, *, client: Any = None, **_: Any) -> AsyncIterator[dict[str, Any]]:
        n = int(query.split("q")[1][0]) if "q" in query else 0
        for i in range(n):
            yield {
                "id": f"{query}-{i}",
                "source": "MED" if i else "PPR",
                "pmid": str(i) if i else None,
            }

    async def insert_run(run: dict[str, Any]) -> int:
        calls["runs"].append(run)
        return 1

    async def upsert_queries(run_id: str, rows: list[dict[str, Any]]) -> int:
        for r in rows:
            calls["queries"][r["query_no"]] = dict(r)
        return len(rows)

    async def upsert_hits(run_id: str, query_no: int, hits: list[Any]) -> int:
        calls["hits"][query_no] = hits
        return len(hits)

    async def finish_run(run_id: str) -> int:
        calls["finished"].append(run_id)
        return 1

    def render_query(row: SeedRow, window: Any) -> str:  # 'q<n>' so the fakes can size answers
        return f"q{SEEDS.index(row) + 1}"

    for fn in (
        build_seeds,
        hit_count,
        search,
        insert_run,
        upsert_queries,
        upsert_hits,
        finish_run,
        render_query,
    ):
        monkeypatch.setattr(mod, fn.__name__, fn)
    return calls


@pytest.mark.asyncio
async def test_flow_numbers_queries_and_writes_hits(prefect: None, fake: dict[str, Any]) -> None:
    out = await mod.pubsearch_run("cfde", date_window=(2019, 2026))

    assert out["run_id"].startswith("cfde-") and out["run_id"].endswith(mod.yaml_sha("cfde")[:7])
    assert out["query_count"] == 3 and out["hit_rows"] == 6 and out["distinct_pmids"] == 2
    assert sorted(fake["queries"]) == [1, 2, 3]
    assert {q: len(h) for q, h in fake["hits"].items()} == {1: 1, 2: 2, 3: 3}
    assert {q: r["hit_count"] for q, r in fake["queries"].items()} == {1: 1, 2: 2, 3: 3}
    assert fake["queries"][2]["search_terms"] == "CFDE"
    assert fake["runs"][0]["date_window_start"] == 2019 and fake["runs"][0]["program"] == "cfde"
    assert fake["finished"] == [out["run_id"]]


@pytest.mark.asyncio
async def test_flow_limit(prefect: None, fake: dict[str, Any]) -> None:
    out = await mod.pubsearch_run("cfde", limit=2)
    assert out["query_count"] == 2 and sorted(fake["queries"]) == [1, 2]
    assert out["hit_rows"] == 3
