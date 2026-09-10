"""Tests for the pubsearch evidence pass: JATS sectioning, exact matching, flow wiring."""

from __future__ import annotations

from pathlib import Path

import pytest

from cfde_atlas_etl.flows import pubsearch_evidence as flow_mod
from cfde_atlas_etl.pubsearch.evidence import evidence_for, find_sentence, sections

JATS = """<?xml version="1.0"?>
<article xmlns:xlink="http://www.w3.org/1999/xlink">
  <front>
    <article-meta>
      <title-group><article-title>Pediatric <italic>tumor</italic> genomes</article-title></title-group>
      <abstract><p>We sequenced 100 tumors. Results were striking.</p></abstract>
      <funding-group><award-group><award-id>U2COD026675</award-id></award-group></funding-group>
    </article-meta>
  </front>
  <body>
    <sec sec-type="intro"><title>Introduction</title><p>Childhood cancer is rare.</p></sec>
    <sec sec-type="methods"><title>Materials and Methods</title>
      <p>Samples were processed with Cavatica. Alignment used BWA.</p>
    </sec>
    <sec><title>Data Availability</title>
      <p>Data are deposited in dbGaP under phs001138.v1.p1 and can be browsed at
      <ext-link xlink:href="https://portal.kidsfirstdrc.org">portal.kidsfirstdrc.org</ext-link>.</p>
    </sec>
    <sec><title>Results and Discussion</title><p>We found 12 fusions.</p></sec>
    <sec><title>Weird heading</title><p>Unclassified prose here.</p></sec>
  </body>
  <back>
    <ack><p>We thank the Kids First Data Resource Center for hosting the data.</p></ack>
    <ref-list><ref id="r1"><mixed-citation><article-title>Cited paper</article-title> 2019</mixed-citation></ref></ref-list>
  </back>
</article>
"""


def test_sections_keys_and_content() -> None:
    s = sections(JATS)
    assert s["Title"] == "Pediatric tumor genomes"
    assert s["Abstract"].startswith("We sequenced 100 tumors.")
    assert s["Title and Abstract"].startswith("Pediatric tumor genomes We sequenced")
    assert "Childhood cancer" in s["Introduction"]
    assert "Cavatica" in s["Methods"]
    assert "phs001138.v1.p1" in s["Methods"]  # Data Availability -> Methods
    assert "12 fusions" in s["Results"]
    assert "Unclassified prose" in s["Other"]
    assert "Kids First Data Resource Center" in s["Acknowledgement & Funding"]
    assert "U2COD026675" in s["Acknowledgement & Funding"]
    assert "Cited paper" in s["References"]
    assert "Cited paper" not in s["Title"]  # ref article-title is not the paper title
    assert s["Discussion"] == "" and s["Supplemental"] == ""
    for part in ("Pediatric", "Cavatica", "phs001138", "Cited paper"):
        assert part in s[""]


@pytest.mark.parametrize(
    ("term", "expected_fragment"),
    [
        ("Cavatica", "Samples were processed with Cavatica."),
        ("portal.kidsfirstdrc.org", "browsed at portal.kidsfirstdrc.org"),
        ("*OD026675", "U2COD026675"),
        ("nonexistent, phs001138.v1.p1", "phs001138.v1.p1"),
        ('"Kids First Data Resource Center"', "We thank the Kids First"),
    ],
)
def test_find_sentence(term: str, expected_fragment: str) -> None:
    sentence = find_sentence(sections(JATS)[""], term)
    assert sentence is not None and expected_fragment in sentence


def test_find_sentence_misses_and_skips_cites() -> None:
    text = sections(JATS)[""]
    assert find_sentence(text, "Not In Paper") is None
    assert find_sentence(text, "37788089_med") is None
    assert len(find_sentence("x" * 2000 + " Cavatica.", "cavatica") or "") == 500


def test_evidence_for() -> None:
    queries = [
        (1, "*OD026675", ""),
        (2, "Kids First Data Resource Center", "Methods"),
        (3, "Kids First Data Resource Center", "Acknowledgement & Funding"),
        (4, "phs001138.v1.p1", ""),
        (5, "37788089_med", "Cites"),
    ]
    out = evidence_for(JATS, queries)
    assert [(q, s) for q, s, _ in out] == [(q, s) for q, _, s in queries]
    by_q = {q: sent for q, _, sent in out}
    assert by_q[1] and "U2COD026675" in by_q[1]
    assert by_q[2] is None  # term is in ack, not methods: API hit, no exact match
    assert by_q[3] and by_q[3].startswith("We thank")
    assert by_q[4] and "dbGaP" in by_q[4]
    assert by_q[5] is None


async def test_flow(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from prefect.testing.utilities import prefect_test_harness

    hits = [
        ("111", "PMC1", 1, "Cavatica", "Methods"),
        ("111", "PMC1", 1, "Cavatica", "Methods"),  # MED + PMC record, same query
        ("111", "PMC1", 2, "Not here", ""),
        ("222", "PMC2", 1, "Cavatica", "Methods"),  # no full text -> no rows
    ]
    calls: list[str] = []
    written: dict[str, object] = {}

    async def fake_load(run_id: str) -> list[flow_mod.Hit]:
        return hits

    async def fake_xml(pmcid: str, *, client: object = None) -> str | None:
        calls.append(pmcid)
        return JATS if pmcid == "PMC1" else None

    async def fake_upsert(run_id: str, rows: object) -> int:
        written["run_id"], written["rows"] = run_id, list(rows)  # type: ignore[arg-type]
        return len(written["rows"])  # type: ignore[arg-type]

    monkeypatch.setattr(flow_mod, "load_hits", fake_load)
    monkeypatch.setattr(flow_mod, "full_text_xml", fake_xml)
    monkeypatch.setattr(flow_mod, "upsert_evidence", fake_upsert)
    monkeypatch.setattr(flow_mod, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(flow_mod, "PAUSE_SECONDS", 0)

    with prefect_test_harness():
        counts = await flow_mod.pubsearch_evidence("run-1")
        assert counts == {
            "papers": 2,
            "fetched": 1,
            "cached": 0,
            "sentences_found": 1,
            "no_match": 1,
            "rows": 2,
        }
        assert (tmp_path / "PMC1.xml").read_text() == JATS
        assert not (tmp_path / "PMC2.xml").exists()
        assert written["run_id"] == "run-1"
        assert sorted(written["rows"]) == [  # type: ignore[arg-type]
            ("111", 1, "Methods", "Samples were processed with Cavatica."),
            ("111", 2, "", None),
        ]

        # Second run hits the disk cache; limit caps the number of papers.
        counts = await flow_mod.pubsearch_evidence("run-1", limit=1)
        assert counts["cached"] == 1 and counts["papers"] == 1
        assert calls == ["PMC1", "PMC2"]
