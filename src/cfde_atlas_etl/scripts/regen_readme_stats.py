"""Rewrite the auto-generated stats block in `README.md`.

Reads analytics.data_inventory, groups by `section`, formats a markdown table
per section, and rewrites the content between markers:

    <!-- BEGIN STATS -->
    ...generated...
    <!-- END STATS -->

Idempotent — same input -> same output. Safe to run repeatedly.

Run standalone:
    uv run python -m cfde_atlas_etl.scripts.regen_readme_stats
"""

from __future__ import annotations

import asyncio
import datetime as dt
import os
import re
from collections import defaultdict
from pathlib import Path

import psycopg
from dotenv import load_dotenv

BEGIN = "<!-- BEGIN STATS -->"
END = "<!-- END STATS -->"

SECTION_ORDER: tuple[tuple[str, str], ...] = (
    ("opportunities-projects-pubs", "Opportunities, Projects, Publications"),
    ("forward-citations", "Forward Citations & Downstream Impact"),
    ("drc", "DRC Asset Manifests"),
    ("c2m2", "C2M2 (DCC Contents)"),
    ("github", "GitHub Activity"),
    ("ga", "Google Analytics"),
    ("infra", "Infrastructure"),
    ("raw", "Raw Layer"),
)


def _fmt_int(n: int | None) -> str:
    return f"{n:,}" if isinstance(n, int) else "—"


def _fmt_ts(ts: dt.datetime | None) -> str:
    if ts is None:
        return "—"
    return ts.strftime("%Y-%m-%d %H:%M UTC")


def render(inventory: list[dict[str, object]]) -> str:
    grouped: dict[str | None, list[dict[str, object]]] = defaultdict(list)
    for row in inventory:
        section = row.get("section")
        section_key = section if isinstance(section, str) or section is None else str(section)
        grouped[section_key].append(row)

    now = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = [
        f"*Auto-generated from `analytics.data_inventory` at {now}. "
        "Edit `config.yaml` + re-run `flows.load_all` to update.*",
        "",
    ]

    for key, header in SECTION_ORDER:
        rows = sorted(
            grouped.get(key) or [],
            key=lambda r: (-(int(r.get("row_count") or 0)), str(r.get("qname"))),
        )
        if not rows:
            continue
        lines.append(f"### {header}")
        lines.append("")
        lines.append("| Object | Rows | Data Refreshed | Description |")
        lines.append("|---|---:|---|---|")
        for r in rows:
            desc_raw = r.get("description")
            description = (
                (desc_raw if isinstance(desc_raw, str) else "")
                .replace("\n", " ")
                .replace("|", "\\|")
            )
            if len(description) > 160:
                description = description[:157] + "…"
            lines.append(
                f"| `{r.get('qname')}` "
                f"| {_fmt_int(r.get('row_count'))} "  # type: ignore[arg-type]
                f"| {_fmt_ts(r.get('data_refreshed_at'))} "  # type: ignore[arg-type]
                f"| {description or '—'} |"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def replace_block(readme_text: str, generated: str) -> str:
    pattern = re.compile(
        re.escape(BEGIN) + r".*?" + re.escape(END),
        flags=re.DOTALL,
    )
    block = f"{BEGIN}\n{generated}{END}"
    if pattern.search(readme_text):
        return pattern.sub(block, readme_text)
    # Markers absent — append at end with a heading.
    return readme_text.rstrip() + f"\n\n## Dataset Stats\n\n{block}\n"


async def load_inventory() -> list[dict[str, object]]:
    load_dotenv()
    db = os.environ.get("DATABASE_URL")
    if not db:
        raise RuntimeError("DATABASE_URL must be set")
    async with (
        await psycopg.AsyncConnection.connect(db) as conn,
        conn.cursor() as cur,
    ):
        await cur.execute(
            "SELECT qname, section, description, row_count, data_refreshed_at "
            "FROM analytics.data_inventory ORDER BY qname"
        )
        rows = await cur.fetchall()
    return [
        {
            "qname": r[0],
            "section": r[1],
            "description": r[2],
            "row_count": r[3],
            "data_refreshed_at": r[4],
        }
        for r in rows
    ]


async def main(readme_path: Path | None = None) -> int:
    inventory = await load_inventory()
    if readme_path is None:
        readme_path = Path("README.md")
    text = readme_path.read_text() if readme_path.exists() else ""
    new_text = replace_block(text, render(inventory))
    readme_path.write_text(new_text)
    return len(inventory)


if __name__ == "__main__":
    asyncio.run(main())
