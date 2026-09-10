"""Write a pubsearch run as a PPST-shaped OUTPUT workbook.

Reproduces the Eval team's PPST output sheets (Summary, Data_Tabular,
Data_Matrixed_Query, Data_Matrixed_Cluster) with their sheet order and header
names, from ``analytics.pubsearch_*`` and ``raw.epmc_*``, so a run of ours can
be diffed against a PPST run directly. Our extra columns (Evidence, Run_ID,
Source, Is_Preprint, Override_Tier) are appended at the END of each sheet;
extra Summary rows (Run_ID, Program_YAML_SHA, Preprints_Included) follow the
Analyst row.

Deviation from PPST: the Eval team leaves ``Broader_Influence`` and
``Final_Assignment`` blank for broader papers and only fills Awardee/User. We
fill all three tier columns with 'x' wherever the tier's queries found the
paper, and always fill Final_Assignment (overrides applied). Preprints have no
pmid, so the ``pmid`` column carries ``paper_key`` (``PPR:<id>``) for them.

Usage::

    uv run python -m cfde_atlas_etl.pubsearch.export_output --run-id X --out run.xlsx
"""

from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any, LiteralString, cast

import openpyxl
import psycopg
from psycopg.rows import dict_row

from cfde_atlas_etl.config import get_settings

TIERS = ("Awardee", "User", "Broader.Influence")
TIER_COLUMNS = ("Awardee", "User", "Broader_Influence", "Final_Assignment")
MATRIX_EXTRA = ("Source", "Is_Preprint", "Override_Tier", "Evidence", "Run_ID")
QUERY_SUMMARY_HEADER = (
    "Query_Number",
    "Query_Label",
    "Query_Cluster",
    "Impact_Category",
    "Total_Results",
    "Total_PMIDs",
    "Original_Query",
    "Search_terms",
    "Search_Field",
    "OR_terms",
    "OR_Search_Field",
    "AND_terms",
    "AND_Search_Field",
    "NOT_terms",
    "NOT_Search_Field",
    "Notes",
)
TABULAR_HEADER = (
    "id",
    "source",
    "pmid",
    "pmcid",
    "title",
    "pubYear",
    "isOpenAccess",
    "Query_Number",
    "Query_Cluster",
    "Meaning",
    "Original_Query",
    "Evidence",
    "Run_ID",
)

Row = dict[str, Any]


def _x(flag: object) -> str | None:
    return "x" if flag else None


def _tier_cells(m: Row) -> list[Any]:
    return [
        _x(m["awardee"]),
        _x(m["user_tier"]),
        _x(m["broader_influence"]),
        m["final_assignment"],
        m["source"],
        bool(m["is_preprint"]),
        m.get("override_tier"),
        m.get("evidence"),
        m["run_id"],
    ]


def _paper_key(h: Row) -> str:
    return h["pmid"] or f"{h['source']}:{h['epmc_id']}"


def _pmids(rows: Iterable[Row]) -> set[str]:
    return {r["pmid"] for r in rows if r.get("pmid")}


def build_workbook(
    run: Row, queries: list[Row], matrix_rows: list[Row], tabular_rows: list[Row]
) -> openpyxl.Workbook:
    """Build the PPST output workbook from already-fetched rows.

    ``run``: a row of ``analytics.pubsearch_runs``; ``queries``: rows of
    ``raw.epmc_queries``; ``matrix_rows``: rows of ``analytics.pubsearch_matrix``;
    ``tabular_rows``: rows of ``raw.epmc_hits``. All for one run_id.
    """
    queries = sorted(queries, key=lambda q: q["query_no"])
    by_no = {q["query_no"]: q for q in queries}
    clusters = list(dict.fromkeys(q["query_cluster"] for q in queries))
    cluster_nos: dict[str, list[int]] = defaultdict(list)
    for q in queries:
        cluster_nos[q["query_cluster"]].append(q["query_no"])
    matrix_by_key = {m["paper_key"]: m for m in matrix_rows}
    hits_by_no: dict[int, list[Row]] = defaultdict(list)
    for h in tabular_rows:
        hits_by_no[h["query_no"]].append(h)

    wb = openpyxl.Workbook()
    wb.remove(wb.worksheets[0])

    # --- Summary: key/value block, not a table -------------------------------
    ws = wb.create_sheet("Summary")
    start, end = run.get("date_window_start"), run.get("date_window_end")
    ws.append(["Date & Time:", str(run.get("started_at") or "")])
    ws.append(["Program/Project:", run["program"]])
    ws.append(["Period Covered:", f"{start or ''}-{end or ''}"])
    ws.append(["Analyst Name:", f"cfde-atlas pubsearch {run['run_id']}"])
    ws.append(["Run_ID:", run["run_id"]])
    ws.append(["Program_YAML_SHA:", run.get("program_yaml_sha")])
    ws.append(["Preprints_Included:", True])
    ws.append([])
    ws.append(["Impact_Category_Summary"])
    ws.append(["Impact_Category", "Query_clusters", "Total_PMIDs"])
    for tier in TIERS:
        tier_clusters = dict.fromkeys(
            q["query_cluster"] for q in queries if q["impact_category"] == tier
        )
        n = len(_pmids(m for m in matrix_rows if m["final_assignment"] == tier))
        ws.append([tier, ", ".join(tier_clusters), n])
    ws.append([])
    ws.append(["Cluster_Summary"])
    ws.append(["Query_Cluster", "Impact_Category", "Query_Numbers", "Total_PMIDs"])
    for c in clusters:
        nos = cluster_nos[c]
        n = len(_pmids(m for m in matrix_rows if set(m["query_nos"]) & set(nos)))
        ws.append([c, by_no[nos[0]]["impact_category"], ", ".join(map(str, nos)), n])
    ws.append([])
    ws.append(["Query_Summary"])
    ws.append(list(QUERY_SUMMARY_HEADER))
    for q in queries:
        ws.append(
            [
                q["query_no"],
                q["query_cluster"],
                q["query_cluster"],
                q["impact_category"],
                q.get("hit_count"),
                len(_pmids(hits_by_no[q["query_no"]])),
                q["epmc_query"],
                q["search_terms"],
                q.get("search_field"),
                q.get("or_terms"),
                q.get("or_search_field"),
                q.get("and_terms"),
                q.get("and_search_field"),
                q.get("not_terms"),
                q.get("not_search_field"),
                q.get("notes"),
            ]
        )

    # --- Data_Tabular: one row per (paper, query) hit -------------------------
    ws = wb.create_sheet("Data_Tabular")
    ws.append(list(TABULAR_HEADER))
    for h in sorted(tabular_rows, key=lambda h: (h["query_no"], _paper_key(h))):
        m = matrix_by_key.get(_paper_key(h))
        if m is None:  # Exclude override: dropped from the matrix, drop here too
            continue
        q = by_no[h["query_no"]]
        ws.append(
            [
                h["epmc_id"],
                h["source"],
                h.get("pmid"),
                h.get("pmcid"),
                h.get("title"),
                h.get("pub_year"),
                h.get("is_open_access"),
                q["query_no"],
                q["query_cluster"],
                q["impact_category"],
                q["epmc_query"],
                m.get("evidence"),
                h["run_id"],
            ]
        )

    # --- Data_Matrixed_Query / Data_Matrixed_Cluster ---------------------------
    matrix_rows = sorted(matrix_rows, key=lambda m: m["paper_key"])
    ws = wb.create_sheet("Data_Matrixed_Query")
    ws.append(["pmid", "pubYear", *map(str, by_no), *TIER_COLUMNS, *MATRIX_EXTRA])
    for m in matrix_rows:
        found = set(m["query_nos"])
        ws.append(
            [m["paper_key"], m["pub_year"], *(_x(n in found) for n in by_no), *_tier_cells(m)]
        )

    ws = wb.create_sheet("Data_Matrixed_Cluster")
    ws.append(["pmid", "pubYear", *clusters, *TIER_COLUMNS, *MATRIX_EXTRA])
    for m in matrix_rows:
        found = set(m["clusters"])
        ws.append(
            [m["paper_key"], m["pub_year"], *(_x(c in found) for c in clusters), *_tier_cells(m)]
        )

    return wb


async def export_output(run_id: str, out: Path) -> Path:
    """Fetch one run from the DB and write its PPST output workbook to ``out``."""
    async with (
        await psycopg.AsyncConnection.connect(
            get_settings().database_url, row_factory=dict_row
        ) as conn,
        conn.cursor() as cur,
    ):

        async def rows(table: LiteralString) -> list[Row]:
            await cur.execute(f"SELECT * FROM {table} WHERE run_id = %s", (run_id,))
            return cast(list[Row], await cur.fetchall())

        run = await rows("analytics.pubsearch_runs")
        if not run:
            raise ValueError(f"no such run: {run_id}")
        wb = build_workbook(
            run[0],
            await rows("raw.epmc_queries"),
            await rows("analytics.pubsearch_matrix"),
            await rows("raw.epmc_hits"),
        )
    wb.save(out)
    return out


def _main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--run-id", required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    print(asyncio.run(export_output(a.run_id, a.out)))


if __name__ == "__main__":
    _main()
