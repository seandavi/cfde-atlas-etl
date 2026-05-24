"""Tests for the C2M2 source helpers using a real fixture zip."""

from __future__ import annotations

from pathlib import Path

from cfde_atlas_etl.sources.c2m2 import (
    C2M2_TABLES_BY_TSV,
    iter_bundle_rows,
    open_bundle,
    parse_submission_date_from_url,
)

FIXTURE = Path(__file__).parent / "fixtures" / "c2m2_gtex_sample.zip"


def test_parse_submission_date_from_url_extracts_yyyy_mm_dd() -> None:
    url = "https://cfde-drc.s3.amazonaws.com/GTEx/C2M2/2025-01-15/submission.zip"
    assert parse_submission_date_from_url(url) == "2025-01-15"


def test_parse_submission_date_returns_none_when_absent() -> None:
    assert parse_submission_date_from_url("https://example.org/foo.zip") is None


def test_open_bundle_lists_c2m2_tsvs() -> None:
    with open_bundle(FIXTURE.read_bytes()) as zf:
        names = [n for n in zf.namelist() if n.endswith(".tsv")]
    assert len(names) >= 30


def test_iter_bundle_rows_reads_dcc_tsv() -> None:
    with open_bundle(FIXTURE.read_bytes()) as zf:
        rows = list(iter_bundle_rows(zf, C2M2_TABLES_BY_TSV["dcc"]))
    assert len(rows) == 1
    dcc_id, _name, dcc_abbreviation, *_ = rows[0]
    assert dcc_id == "cfde_registry_dcc:gtex"
    assert dcc_abbreviation == "GTEx"


def test_iter_bundle_rows_normalizes_blanks_to_none() -> None:
    with open_bundle(FIXTURE.read_bytes()) as zf:
        rows = list(iter_bundle_rows(zf, C2M2_TABLES_BY_TSV["subject"]))
    # First GTEx subject: ethnicity is blank in the source TSV, should be None.
    first = rows[0]
    # subject columns: id_namespace, local_id, project_id_namespace, project_local_id,
    #                  persistent_id, creation_time, granularity, sex, ethnicity, age_at_enrollment
    assert first[8] is None  # ethnicity
    # And persistent_id is also blank -> None
    assert first[4] is None


def test_iter_bundle_rows_skips_missing_tsv() -> None:
    # The fixture omits a few optional tsvs; iter_bundle_rows should yield nothing
    # rather than raising. Pick one that's not in the fixture (analysis_type rows = 0).
    with open_bundle(FIXTURE.read_bytes()) as zf:
        rows = list(iter_bundle_rows(zf, C2M2_TABLES_BY_TSV["analysis_type"]))
    assert rows == []


def test_dcc_table_has_tsv_column_aliasing() -> None:
    table = C2M2_TABLES_BY_TSV["dcc"]
    # PG column dcc_id is read from TSV column "id".
    assert table.columns[0] == "dcc_id"
    assert table.tsv_columns is not None
    assert table.tsv_columns[0] == "id"
    assert table.header_for("dcc_id") == "id"
    # Non-aliased column passes through.
    assert table.header_for("dcc_name") == "dcc_name"
