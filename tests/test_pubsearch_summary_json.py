"""Tests for pubsearch/summary_json.py: pure summarize(), file output, schema drift."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from cfde_atlas_etl.pubsearch.summary_json import SCHEMA_PATH, schema_json, summarize, write_summary

RUN = {
    "run_id": "abc123-20260910T120000Z",
    "program": "cfde",
    "program_yaml_sha": "abc123",
    "date_window_start": 2019,
    "date_window_end": 2026,
    "started_at": datetime(2026, 9, 10, 12, 0, tzinfo=UTC),
    "finished_at": datetime(2026, 9, 10, 12, 5, tzinfo=UTC),
    "query_count": 5,
    "hit_count": 6,
    "unique_pmids": 3,
    "preprint_hits": 1,
}
SUMMARY = [
    {
        "level": "tier",
        "label": "Awardee",
        "impact_category": None,
        "paper_count": 2,
        "paper_count_excl_preprints": 2,
        "pmid_count": 2,
    },
    {
        "level": "tier",
        "label": "User",
        "impact_category": None,
        "paper_count": 1,
        "paper_count_excl_preprints": 1,
        "pmid_count": 1,
    },
    {
        "level": "tier",
        "label": "Broader.Influence",
        "impact_category": None,
        "paper_count": 1,
        "paper_count_excl_preprints": 0,
        "pmid_count": 0,
    },
    {
        "level": "cluster",
        "label": "grants",
        "impact_category": "Awardee",
        "paper_count": 2,
        "paper_count_excl_preprints": 2,
        "pmid_count": 2,
    },
    {
        "level": "cluster",
        "label": "name",
        "impact_category": "Broader.Influence",
        "paper_count": 2,
        "paper_count_excl_preprints": 1,
        "pmid_count": 1,
    },
]
# 4 papers: 2 Awardee (one via override from User), 1 User, 1 preprint Broader.
MATRIX = [
    {
        "pmid": "1",
        "is_preprint": False,
        "pub_year": 2020,
        "final_assignment": "Awardee",
        "override_tier": None,
    },
    {
        "pmid": "2",
        "is_preprint": False,
        "pub_year": 2021,
        "final_assignment": "Awardee",
        "override_tier": "Awardee",
    },
    {
        "pmid": "3",
        "is_preprint": False,
        "pub_year": 2021,
        "final_assignment": "User",
        "override_tier": None,
    },
    {
        "pmid": None,
        "is_preprint": True,
        "pub_year": 2022,
        "final_assignment": "Broader.Influence",
        "override_tier": None,
    },
]
PUBS = [
    {"pmid": "1", "journal": "Nature", "relative_citation_ratio": Decimal("1.5")},
    {"pmid": "2", "journal": "Nature", "relative_citation_ratio": Decimal("3.0")},
    {"pmid": "3", "journal": "Cell", "relative_citation_ratio": Decimal("0.5")},
]
QUERIES = [
    {"query_cluster": "grants", "query_count": 3},
    {"query_cluster": "name", "query_count": 2},
]


def _summary():
    return summarize(RUN, SUMMARY, MATRIX, PUBS, QUERIES)


def test_summarize_blocks() -> None:
    s = _summary()
    assert s.schema_version == 1
    assert s.run.display_name == "Common Fund Data Ecosystem"
    assert s.run.date_window == (2019, 2026)
    assert s.run.unique_pmids == 3

    assert [(t.tier, t.papers, t.papers_excl_preprints, t.pmids) for t in s.tiers] == [
        ("Awardee", 2, 2, 2),
        ("User", 1, 1, 1),
        ("Broader.Influence", 1, 0, 0),
    ]
    assert [(c.cluster, c.impact_category, c.papers, c.query_count) for c in s.clusters] == [
        ("grants", "Awardee", 2, 3),
        ("name", "Broader.Influence", 2, 2),
    ]
    # preprint (2022) excluded
    assert [(y.year, y.awardee, y.user, y.broader_influence) for y in s.by_year] == [
        (2020, 1, 0, 0),
        (2021, 1, 1, 0),
    ]
    assert [(j.journal, j.papers) for j in s.top_journals] == [("Nature", 2), ("Cell", 1)]
    assert s.rcr is not None
    assert (s.rcr.n, s.rcr.median, s.rcr.q1, s.rcr.q3, s.rcr.max) == (3, 1.5, 1.0, 2.25, 3.0)
    assert s.overrides.count == 1
    assert s.overrides.by_tier == {"Awardee": 1}
    assert s.notes == []


def test_sparse_join_note_and_null_rcr() -> None:
    s = summarize(RUN, SUMMARY, MATRIX, PUBS[:1], QUERIES)
    assert s.rcr is not None and s.rcr.n == 1 and s.rcr.q1 == s.rcr.q3 == 1.5
    assert any("1 of 3" in n for n in s.notes)
    assert summarize(RUN, SUMMARY, MATRIX, [], QUERIES).rcr is None


def test_write_summary_matches_committed_schema(tmp_path: Path) -> None:
    out = write_summary(_summary(), tmp_path / "s.json")
    doc = json.loads(out.read_text())
    schema = json.loads(SCHEMA_PATH.read_text())
    assert set(doc) == set(schema["properties"])
    assert set(schema["required"]) <= set(doc)
    defs = schema["$defs"]
    for block, name in (("run", "RunBlock"), ("overrides", "OverridesBlock")):
        assert set(defs[name]["required"]) <= set(doc[block])
    assert set(doc["by_year"][0]) == set(defs["YearBlock"]["properties"])
    assert out.read_text() == json.dumps(doc, indent=2, sort_keys=True) + "\n"


def test_schema_file_is_current() -> None:
    assert SCHEMA_PATH.read_text() == schema_json(), (
        "run: uv run python -m cfde_atlas_etl.pubsearch.summary_json --write-schema"
    )
