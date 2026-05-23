"""Tests for the DRC source parser. No network."""

from __future__ import annotations

from cfde_atlas_etl.sources.drc import parse_tsv

DCC_FIXTURE = (
    b"link\tlastmodified\tdcc_id\tdrcapproved\tdccapproved\n"
    b"https://example.org/foo\t2024-03-08\tabcd\tTrue\tFalse\n"
    b"https://example.org/bar\t\t\tFalse\tFalse\n"
)

FILE_FIXTURE = (
    b"filetype\tfilename\tlink\tsize\tsha256checksum\n"
    b"C2M2\tdatapackage.zip\thttps://example.org/dp.zip\t384717\t\n"
    b"C2M2\tdatapackage.zip\thttps://example.org/dp2.zip\t9288164172\t\n"
)


def test_parse_tsv_normalizes_empty_to_none() -> None:
    rows = parse_tsv(DCC_FIXTURE)
    assert len(rows) == 2
    assert rows[0]["link"] == "https://example.org/foo"
    assert rows[0]["dcc_id"] == "abcd"
    # Empty strings become None
    assert rows[1]["dcc_id"] is None
    assert rows[1]["lastmodified"] is None


def test_parse_tsv_preserves_numeric_string_size() -> None:
    rows = parse_tsv(FILE_FIXTURE)
    assert rows[0]["size"] == "384717"
    assert rows[1]["size"] == "9288164172"  # > 2^31, must survive as string
