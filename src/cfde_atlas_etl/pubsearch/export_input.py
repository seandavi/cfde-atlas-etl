"""Write seed rows into the Eval team's PPST Script_Input template.

Opens the template xlsx (kept out of git; path via ``PPST_TEMPLATE_PATH``),
appends one row per SeedRow to the ``Script_Input`` sheet, extends the
``Table2`` Excel table and the two dropdown validations to cover the written
rows, and saves to a new file. Every other sheet is left untouched.

Usage::

    uv run python -m cfde_atlas_etl.pubsearch.export_input \\
        --rows rows.json --out CFDE_PPST_input_2026-09-10.xlsx --program CFDE
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from collections.abc import Sequence
from pathlib import Path

import openpyxl
from openpyxl.worksheet.datavalidation import DataValidation, DataValidationList

from cfde_atlas_etl.pubsearch.models import TEMPLATE_COLUMNS, SeedRow

SHEET = "Script_Input"
TABLE = "Table2"
# Formulas exactly as they appear in the template; both resolve to tables on Field_lookup.
FIELD_SEARCH_FORMULA = 'INDIRECT("Field_Search_Lookup[Field_Search]")'
MEANING_FORMULA = 'INDIRECT("Meaning")'
# Search.Field, OR.Search.Field, AND.Search.Field, NOT.Search.Field.
FIELD_SEARCH_COLUMNS = ("D", "F", "H", "J")


def write_script_input(rows: Sequence[SeedRow], template: Path, out: Path, *, program: str) -> Path:
    """Append ``rows`` to the template's Script_Input sheet and save as ``out``."""
    wb = openpyxl.load_workbook(template)
    ws = wb[SHEET]
    header = tuple(c.value for c in ws[1])
    if header != TEMPLATE_COLUMNS:
        raise ValueError(f"{SHEET} header {header!r} != TEMPLATE_COLUMNS")
    if not rows:
        raise ValueError("no rows to write")

    for r, row in enumerate(rows, start=2):
        for c, value in enumerate(row.as_template_row(), start=1):
            ws.cell(row=r, column=c, value=value or None)  # '' -> blank cell

    last = len(rows) + 1
    ref = f"A1:K{last}"
    table = ws.tables[TABLE]
    table.ref = ref
    if table.autoFilter is not None:
        table.autoFilter.ref = ref

    # The template's ranges are sloppy (H2:H45, I3:I18, J18:J46); rewrite them cleanly.
    ws.data_validations = DataValidationList()
    field_dv = DataValidation(type="list", formula1=FIELD_SEARCH_FORMULA, allow_blank=True)
    for col in FIELD_SEARCH_COLUMNS:
        field_dv.add(f"{col}2:{col}{last}")
    meaning_dv = DataValidation(type="list", formula1=MEANING_FORMULA, allow_blank=True)
    meaning_dv.add(f"A2:A{last}")
    ws.add_data_validation(field_dv)
    ws.add_data_validation(meaning_dv)

    wb.properties.title = f"{program} PPST Script_Input"
    wb.properties.subject = f"program={program} written={dt.date.today().isoformat()}"
    wb.save(out)
    return out


def _main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--rows", type=Path, required=True, help="JSON list of SeedRow objects")
    p.add_argument(
        "--template",
        type=Path,
        default=os.environ.get("PPST_TEMPLATE_PATH"),
        required="PPST_TEMPLATE_PATH" not in os.environ,
        help="PPST input template xlsx (default: $PPST_TEMPLATE_PATH)",
    )
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--program", required=True)
    a = p.parse_args()
    rows = [SeedRow(**d) for d in json.loads(a.rows.read_text())]
    print(write_script_input(rows, a.template, a.out, program=a.program))


if __name__ == "__main__":
    _main()
