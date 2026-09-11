"""Tests for pubsearch seed builders (pure transforms, no live DB)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cfde_atlas_etl.pubsearch.models import SEARCH_FIELDS, SeedRow
from cfde_atlas_etl.pubsearch.seeds import (
    accession,
    accession_rows,
    bare_host,
    cites_rows,
    curated_rows,
    domain_rows,
    drc_url_rows,
    grant_rows,
    grant_serial,
    grant_title_rows,
    load_program,
    order_rows,
    quote_term,
    title_phrases,
    url_host_path,
)


def test_grant_serial() -> None:
    assert grant_serial("R03OD030596", "R03") == "*OD030596"
    assert grant_serial("OT2OD026675", "OT2") == "*OD026675"


def test_bare_host() -> None:
    assert bare_host("https://kidsfirstdrc.org") == "kidsfirstdrc.org"
    assert bare_host("https://www.glygen.org/") == "glygen.org"
    assert bare_host("HTTPS://CM4AI.ORG") == "cm4ai.org"
    assert bare_host("http://dcic.4dnucleome.org/") == "dcic.4dnucleome.org"


def test_url_host_path() -> None:
    assert (
        url_host_path("https://ldh.genome.network/cfde/ldh/Gene/id/{GENE_NAME}")
        == "ldh.genome.network/cfde/ldh/Gene/id"
    )
    assert url_host_path("https://ldh.genome.network/cfde/ldh/Gene/id/") == (
        "ldh.genome.network/cfde/ldh/Gene/id"
    )
    assert url_host_path("https://drugcentral.org/?q={drug.label}") == "drugcentral.org"
    assert url_host_path("https://www.gtexportal.org/home/gene/{gene.ensembl}") == (
        "gtexportal.org/home/gene"
    )


def test_accession() -> None:
    assert accession("phs001138.v2.p1") == "phs001138"
    assert accession("phs001138") == "phs001138"


def test_quote_term() -> None:
    assert quote_term("CFDE") == "CFDE"
    assert quote_term("Common Fund") == '"Common Fund"'
    assert quote_term("cfde.cloud") == '"cfde.cloud"'
    assert quote_term('"already"') == '"already"'


def test_order_and_dedupe() -> None:
    rows = [
        *cites_rows([(1,)]),
        *accession_rows([("phs1.v1",), ("phs1.v2",)]),  # same term after stripping -> 1 row
        *grant_rows([("U54DA1", "U54"), ("R03OD1", "R03"), ("U54DA2", "U54")]),
    ]
    ordered = order_rows(rows)
    assert [r.impact_category for r in ordered] == ["Awardee"] * 3 + ["User", "Broader.Influence"]
    assert [r.query_cluster for r in ordered[:3]] == ["R03", "U54", "U54"]
    assert len(ordered) == 5


def test_builders_fields_and_notes() -> None:
    rows = [
        *grant_rows([("R03OD030596", "R03")]),
        *cites_rows([(12345,)]),
        *accession_rows([("phs001138.v2.p1",)]),
        *domain_rows([("KFDRC", "https://kidsfirstdrc.org")]),
        *drc_url_rows(
            [
                ("x", "https://ldh.genome.network/cfde/ldh/Gene/id/{GENE_NAME}"),
                ("y", "https://other.org/"),
            ],
            ["cfde"],
        ),
    ]
    assert all(r.notes for r in rows)
    assert rows[0] == SeedRow("Awardee", "R03", "*OD030596", "", notes="analytics.core_projects")
    assert rows[1].search_terms == "12345_med" and rows[1].search_field == "Cites"
    assert rows[1].query_cluster == "Cites_Awardee_Paper"
    assert rows[2].search_terms == "phs001138" and rows[2].query_cluster == "dBGap_accession_number"
    assert [r.search_field for r in rows[3:6]] == ["Methods", "Acknowledgement & Funding", ""]
    assert {r.search_terms for r in rows[3:6]} == {"kidsfirstdrc.org"}
    assert [(r.search_terms, r.search_field) for r in rows[6:]] == [
        ("ldh.genome.network/cfde/ldh/Gene/id", "Methods"),
        ("ldh.genome.network/cfde/ldh/Gene/id", ""),
    ]


def test_load_program_tmp_yaml(tmp_path: Path) -> None:
    (tmp_path / "demo.yaml").write_text(
        "program: demo\ndisplay_name: Demo\nseed_kinds: [curated]\n"
        "curated:\n"
        "  - {impact_category: User, query_cluster: Program_Name, search_terms: Demo Program,"
        " search_field: Methods, quote: true}\n"
        "  - {impact_category: User, query_cluster: Program_Name, search_terms: Demo Program,"
        " search_field: ''}\n"
    )
    cfg = load_program("demo", tmp_path)
    rows = curated_rows(cfg)
    assert [r.search_terms for r in rows] == ['"Demo Program"', "Demo Program"]
    assert all(r.notes == "curated:programs/demo.yaml" for r in rows)
    with pytest.raises(FileNotFoundError):
        load_program("nope", tmp_path)


def test_load_program_rejects_bad_field(tmp_path: Path) -> None:
    (tmp_path / "bad.yaml").write_text(
        "program: bad\ndisplay_name: Bad\nseed_kinds: [curated]\n"
        "curated:\n"
        "  - {impact_category: User, query_cluster: X, search_terms: y, search_field: Body}\n"
    )
    with pytest.raises(ValueError):
        curated_rows(load_program("bad", tmp_path))


def test_cfde_yaml_validates() -> None:
    cfg = load_program("cfde")
    assert cfg.program == "cfde"
    rows = curated_rows(cfg)
    assert rows and all(r.search_field in SEARCH_FIELDS for r in rows)
    assert all(r.notes == "curated:programs/cfde.yaml" for r in rows)


def test_title_phrases() -> None:
    assert title_phrases("The Common Fund Knowledge Center (CFKC): providing validated x") == [
        "Common Fund Knowledge Center",
        "CFKC",
    ]
    assert title_phrases("The CFDE Cloud Workspace") == ["CFDE Cloud Workspace"]
    assert title_phrases("Biomedical Data Commons Workbench (BDCW)") == [
        "Biomedical Data Commons Workbench",
        "BDCW",
    ]
    assert (
        title_phrases(
            "U24-Uncovering the Shared Genetic Origins of Childhood Cancer and Birth Defects"
        )
        == []
    )
    assert title_phrases("Kids First Data Resource Center (KFDRC): Harnessing Data") == [
        "Kids First Data Resource Center",
        "KFDRC",
    ]


def test_grant_title_rows_acronym_gets_qualifier() -> None:
    rows = grant_title_rows(
        [("OT2OD036440", "The Common Fund Knowledge Center (CFKC): x")], ["OT2"]
    )
    assert [r.search_terms for r in rows] == ["Common Fund Knowledge Center"] * 2 + ["CFKC"] * 2
    assert {r.search_field for r in rows} == {"Methods", "Acknowledgement & Funding"}
    assert [r.and_terms for r in rows] == ["", "", "Common Fund", "Common Fund"]
    assert all(r.impact_category == "User" and "OT2OD036440" in r.notes for r in rows)


def test_grant_title_rows_exclude() -> None:
    rows = grant_title_rows(
        [("U54OD036472", "CONNECT: Collaborative Network"), ("OT2OD036440", "The CFDE Workbench")],
        ["U54", "OT2"],
        exclude=["connect"],
    )
    assert {r.search_terms for r in rows} == {"CFDE Workbench"}
