"""Per-program summary JSON for the cfde-atlas report page. See docs/pubsearch/SPEC.md.

Reads analytics.pubsearch_runs / pubsearch_summary / pubsearch_matrix plus
analytics.publications (journal, RCR by pmid) for one run and writes a
``PubsearchSummary`` document (schema: docs/pubsearch/summary.schema.json).

Usage::

    uv run python -m cfde_atlas_etl.pubsearch.summary_json --run-id X --out cfde.json
    uv run python -m cfde_atlas_etl.pubsearch.summary_json --write-schema   # regen schema
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from cfde_atlas_etl.config import get_settings
from cfde_atlas_etl.models.pubsearch_summary import (
    ClusterBlock,
    JournalBlock,
    OverridesBlock,
    PubsearchSummary,
    RcrBlock,
    RunBlock,
    TierBlock,
    YearBlock,
)
from cfde_atlas_etl.pubsearch.seeds import load_program

Row = Mapping[str, Any]
TIERS = ("Awardee", "User", "Broader.Influence")
TOP_JOURNALS = 15
SCHEMA_PATH = Path(__file__).resolve().parents[3] / "docs" / "pubsearch" / "summary.schema.json"


def schema_json() -> str:
    return json.dumps(PubsearchSummary.model_json_schema(), indent=2) + "\n"


def summarize(
    run_row: Row,
    summary_rows: Iterable[Row],
    matrix_rows: Iterable[Row],
    pub_rows: Iterable[Row],
    query_rows: Iterable[Row] = (),
) -> PubsearchSummary:
    """Pure: dict rows from the views -> PubsearchSummary.

    ``query_rows`` = ``{query_cluster, query_count}`` per cluster (raw.epmc_queries);
    the summary view does not carry it.
    """
    matrix_rows = list(matrix_rows)
    pub_rows = list(pub_rows)
    notes: list[str] = []

    try:
        display_name = load_program(run_row["program"]).display_name
    except FileNotFoundError:
        display_name = run_row["program"]
    run = RunBlock(
        run_id=run_row["run_id"],
        program=run_row["program"],
        display_name=display_name,
        program_yaml_sha=run_row.get("program_yaml_sha"),
        date_window=(run_row.get("date_window_start"), run_row.get("date_window_end")),
        started_at=run_row["started_at"],
        finished_at=run_row.get("finished_at"),
        query_count=run_row["query_count"],
        hit_count=run_row["hit_count"],
        unique_pmids=run_row["unique_pmids"],
        preprint_hits=run_row["preprint_hits"],
    )

    tier_rows = {r["label"]: r for r in summary_rows if r["level"] == "tier"}
    tiers = [
        TierBlock(
            tier=t,
            papers=r["paper_count"],
            papers_excl_preprints=r["paper_count_excl_preprints"],
            pmids=r["pmid_count"],
        )
        for t in TIERS
        if (r := tier_rows.get(t))
    ]

    queries_per_cluster = {r["query_cluster"]: r["query_count"] for r in query_rows}
    clusters = [
        ClusterBlock(
            cluster=r["label"],
            impact_category=r.get("impact_category"),
            papers=r["paper_count"],
            papers_excl_preprints=r["paper_count_excl_preprints"],
            pmids=r["pmid_count"],
            query_count=queries_per_cluster.get(r["label"], 0),
        )
        for r in sorted(
            (r for r in summary_rows if r["level"] == "cluster"), key=lambda r: r["label"]
        )
    ]

    per_year: dict[int, Counter[str]] = defaultdict(Counter)
    no_year = 0
    for m in matrix_rows:
        if m["is_preprint"]:
            continue
        if m["pub_year"] is None:
            no_year += 1
            continue
        per_year[m["pub_year"]][m["final_assignment"]] += 1
    by_year = [YearBlock(year=y, **per_year[y]) for y in sorted(per_year)]
    if no_year:
        notes.append(
            f"{no_year} non-preprint paper(s) have no pub_year and are omitted from by_year."
        )

    journal_counts = Counter(p["journal"] for p in pub_rows if p.get("journal"))
    top_journals = [
        JournalBlock(journal=j, papers=n)
        for j, n in sorted(journal_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP_JOURNALS]
    ]
    with_pmid = sum(1 for m in matrix_rows if m["pmid"])
    if with_pmid and len(pub_rows) < with_pmid:
        notes.append(
            f"top_journals and rcr cover {len(pub_rows)} of {with_pmid} papers with a PMID: "
            "only papers already in analytics.publications (typically Awardee papers) join."
        )

    rcr_values = sorted(
        float(p["relative_citation_ratio"])
        for p in pub_rows
        if p.get("relative_citation_ratio") is not None
    )
    rcr = None
    if rcr_values:
        # statistics.quantiles needs >= 2 points; a single value is its own quartiles.
        q1, _, q3 = (
            statistics.quantiles(rcr_values, n=4, method="inclusive")
            if len(rcr_values) > 1
            else (rcr_values[0],) * 3
        )
        rcr = RcrBlock(
            n=len(rcr_values),
            median=statistics.median(rcr_values),
            q1=q1,
            q3=q3,
            max=rcr_values[-1],
        )

    override_tiers = Counter(m["override_tier"] for m in matrix_rows if m.get("override_tier"))
    overrides = OverridesBlock(
        count=sum(override_tiers.values()), by_tier=dict(sorted(override_tiers.items()))
    )

    return PubsearchSummary(
        run=run,
        tiers=tiers,
        clusters=clusters,
        by_year=by_year,
        top_journals=top_journals,
        rcr=rcr,
        overrides=overrides,
        notes=notes,
    )


async def build_summary(run_id: str) -> PubsearchSummary:
    async with (
        await psycopg.AsyncConnection.connect(get_settings().database_url) as conn,
        conn.cursor(row_factory=dict_row) as cur,
    ):
        await cur.execute("SELECT * FROM analytics.pubsearch_runs WHERE run_id = %s", (run_id,))
        run_row = await cur.fetchone()
        if run_row is None:
            raise ValueError(f"no pubsearch run {run_id!r}")
        await cur.execute("SELECT * FROM analytics.pubsearch_summary WHERE run_id = %s", (run_id,))
        summary_rows = await cur.fetchall()
        await cur.execute(
            "SELECT pmid, is_preprint, pub_year, final_assignment, override_tier "
            "FROM analytics.pubsearch_matrix WHERE run_id = %s",
            (run_id,),
        )
        matrix_rows = await cur.fetchall()
        await cur.execute(
            "SELECT DISTINCT ON (p.pmid) p.pmid::text AS pmid, p.journal, p.relative_citation_ratio "
            "FROM analytics.pubsearch_matrix m "
            "JOIN analytics.publications p ON p.pmid::text = m.pmid "
            "WHERE m.run_id = %s ORDER BY p.pmid",
            (run_id,),
        )
        pub_rows = await cur.fetchall()
        await cur.execute(
            "SELECT query_cluster, COUNT(*)::int AS query_count FROM raw.epmc_queries "
            "WHERE run_id = %s GROUP BY query_cluster",
            (run_id,),
        )
        query_rows = await cur.fetchall()
    return summarize(run_row, summary_rows, matrix_rows, pub_rows, query_rows)


def write_summary(summary: PubsearchSummary, out: Path) -> Path:
    out.write_text(
        json.dumps(summary.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True) + "\n"
    )
    return out


def _main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--run-id")
    p.add_argument("--out", type=Path)
    p.add_argument("--write-schema", action="store_true", help=f"regenerate {SCHEMA_PATH}")
    a = p.parse_args()
    if a.write_schema:
        SCHEMA_PATH.write_text(schema_json())
        print(SCHEMA_PATH)
    if a.run_id:
        if not a.out:
            p.error("--out is required with --run-id")
        print(write_summary(asyncio.run(build_summary(a.run_id)), a.out))
    elif not a.write_schema:
        p.error("--run-id or --write-schema required")


if __name__ == "__main__":
    _main()
