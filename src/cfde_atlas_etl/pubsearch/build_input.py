"""Build the PPST Script_Input workbook for a program: seeds -> template -> xlsx.

Usage::

    uv run python -m cfde_atlas_etl.pubsearch.build_input --program cfde \\
        --template path/to/PPST_template.xlsx --out cfde_PPST_input_2026-09-10.xlsx

The template is the Eval team's blank input workbook (not in git; default from
``PPST_TEMPLATE_PATH``). Prints a per-(category, cluster) row count on success.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import os
from collections import Counter
from pathlib import Path

from cfde_atlas_etl.pubsearch.export_input import write_script_input
from cfde_atlas_etl.pubsearch.seeds import build_seeds


async def build_input(program: str, template: Path, out: Path) -> Path:
    rows = await build_seeds(program)
    write_script_input(rows, template, out, program=program)
    counts = Counter((r.impact_category, r.query_cluster) for r in rows)
    for (cat, cluster), n in sorted(counts.items()):
        print(f"{n:5d}  {cat:<18} {cluster}")
    print(f"{len(rows):5d}  total -> {out}")
    return out


def _main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--program", required=True)
    p.add_argument(
        "--template",
        type=Path,
        default=os.environ.get("PPST_TEMPLATE_PATH"),
        required="PPST_TEMPLATE_PATH" not in os.environ,
    )
    p.add_argument("--out", type=Path, default=None)
    a = p.parse_args()
    out = a.out or Path(f"{a.program}_PPST_input_{dt.date.today().isoformat()}.xlsx")
    asyncio.run(build_input(a.program, a.template, out))


if __name__ == "__main__":
    _main()
