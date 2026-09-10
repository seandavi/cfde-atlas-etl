"""Tests for the PPST Script_Input writer against a synthetic template.

The fixture rebuilds only the structure the writer touches or depends on:
the Script_Input header + Table2 + two dropdown validations, and the
Field_lookup tables the INDIRECT formulas point at.
"""

from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table

from cfde_atlas_etl.pubsearch.export_input import (
    FIELD_SEARCH_FORMULA,
    MEANING_FORMULA,
    write_script_input,
)
from cfde_atlas_etl.pubsearch.models import SEARCH_FIELDS, TEMPLATE_COLUMNS, SeedRow

OTHER_SHEETS = ("Term_Glossary", "Field_lookup", "Example", "User_Guide")


@pytest.fixture
def template(tmp_path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Script_Input"
    ws.append(TEMPLATE_COLUMNS)
    ws.add_table(Table(displayName="Table2", ref="A1:K1"))
    dv = DataValidation(type="list", formula1=FIELD_SEARCH_FORMULA, allow_blank=True)
    for rng in ("D2:D46", "F2:F46", "H2:H45", "I3:I18", "J18:J46"):
        dv.add(rng)
    ws.add_data_validation(dv)
    dv = DataValidation(type="list", formula1=MEANING_FORMULA, allow_blank=True)
    dv.add("A2:A46")
    ws.add_data_validation(dv)

    wb.create_sheet("Term_Glossary").append(["Term", "Definition"])
    fl = wb.create_sheet("Field_lookup")
    fl.append(["Field_Search"])
    for f in SEARCH_FIELDS[1:]:
        fl.append([f])
    fl.add_table(Table(displayName="Field_Search_Lookup", ref=f"A1:A{len(SEARCH_FIELDS)}"))
    fl["C1"] = "Meaning_Assignment"
    for i, v in enumerate(("Awardee", "User", "Broader.Influence"), start=2):
        fl[f"C{i}"] = v
    fl.add_table(Table(displayName="Meaning", ref="C1:C4"))
    wb.create_sheet("Example").append(list(TEMPLATE_COLUMNS))
    wb.create_sheet("User_Guide").append(["Step", "Text"])
    path = tmp_path / "template.xlsx"
    wb.save(path)
    return path


ROWS = [
    SeedRow("Awardee", "Grants", "OD030596", notes="analytics.core_projects"),
    SeedRow("User", "Domains", "cfde.cloud", "Methods", "cfde.cloud", "", notes="c2m2.dcc"),
    SeedRow("Broader.Influence", "Cites", "CITES:123_med", notes="analytics.publications"),
]


def _values(ws) -> list[tuple]:
    return [tuple(r) for r in ws.iter_rows(values_only=True)]


def test_rows_land_in_order_and_table_and_validations_extend(template: Path, tmp_path: Path):
    out = write_script_input(ROWS, template, tmp_path / "out.xlsx", program="CFDE")
    wb = openpyxl.load_workbook(out)
    ws = wb["Script_Input"]

    assert _values(ws)[0] == TEMPLATE_COLUMNS
    assert _values(ws)[1:] == [tuple(v or None for v in r.as_template_row()) for r in ROWS]
    assert ws.max_row == 4

    table = ws.tables["Table2"]
    assert table.ref == "A1:K4"
    assert table.autoFilter.ref == "A1:K4"

    dvs = {dv.formula1: dv for dv in ws.data_validations.dataValidation}
    assert set(dvs) == {FIELD_SEARCH_FORMULA, MEANING_FORMULA}
    assert str(dvs[FIELD_SEARCH_FORMULA].sqref) == "D2:D4 F2:F4 H2:H4 J2:J4"
    assert str(dvs[MEANING_FORMULA].sqref) == "A2:A4"
    assert all(dv.allow_blank for dv in dvs.values())

    assert "CFDE" in wb.properties.title
    assert "program=CFDE" in wb.properties.subject


def test_other_sheets_unchanged(template: Path, tmp_path: Path):
    before = openpyxl.load_workbook(template)
    out = write_script_input(ROWS, template, tmp_path / "out.xlsx", program="CFDE")
    after = openpyxl.load_workbook(out)
    assert after.sheetnames == before.sheetnames
    for name in OTHER_SHEETS:
        assert _values(after[name]) == _values(before[name])
    assert dict(after["Field_lookup"].tables.items()) == {
        "Field_Search_Lookup": f"A1:A{len(SEARCH_FIELDS)}",
        "Meaning": "C1:C4",
    }


def test_wrong_header_raises(template: Path, tmp_path: Path):
    wb = openpyxl.load_workbook(template)
    wb["Script_Input"]["B1"] = "Cluster"
    bad = tmp_path / "bad.xlsx"
    wb.save(bad)
    with pytest.raises(ValueError, match="header"):
        write_script_input(ROWS, bad, tmp_path / "out.xlsx", program="CFDE")


def test_zero_rows_raises(template: Path, tmp_path: Path):
    with pytest.raises(ValueError, match="no rows"):
        write_script_input([], template, tmp_path / "out.xlsx", program="CFDE")
