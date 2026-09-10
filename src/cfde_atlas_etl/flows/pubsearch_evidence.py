"""Prefect flow: full-text evidence pass for a pubsearch run -> raw.epmc_evidence.

For every hit in the run with a PMCID, fetch the JATS full text once (cached on
disk under raw/epmc_fulltext/, gitignored) and, per query that found the paper,
store the sentence where the query term occurs in the section the query targeted.
See docs/pubsearch/SPEC.md and pubsearch/evidence.py.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import psycopg
from prefect import flow, get_run_logger

from cfde_atlas_etl.config import get_settings
from cfde_atlas_etl.pubsearch.evidence import evidence_for
from cfde_atlas_etl.sinks.epmc_evidence import upsert_evidence
from cfde_atlas_etl.sources.epmc import full_text_xml

CACHE_DIR = Path("raw/epmc_fulltext")
CONCURRENCY = 4
PAUSE_SECONDS = 0.25

# (pmid, pmcid, query_no, search_terms, search_field)
Hit = tuple[str, str, int, str, str]


async def load_hits(run_id: str) -> list[Hit]:
    settings = get_settings()
    async with (
        await psycopg.AsyncConnection.connect(settings.database_url) as conn,
        conn.cursor() as cur,
    ):
        await cur.execute(
            "SELECT h.pmid, h.pmcid, h.query_no, q.search_terms, q.search_field "
            "FROM raw.epmc_hits h JOIN raw.epmc_queries q USING (run_id, query_no) "
            "WHERE h.run_id = %s AND h.pmcid IS NOT NULL AND h.pmid IS NOT NULL "
            "ORDER BY h.pmcid, h.query_no",
            (run_id,),
        )
        return [tuple(r) for r in await cur.fetchall()]  # type: ignore[misc]


async def fetch_xml(
    pmcid: str, client: httpx.AsyncClient, sem: asyncio.Semaphore
) -> tuple[str | None, bool]:
    """(xml_or_None, from_cache)."""
    path = CACHE_DIR / f"{pmcid}.xml"
    if path.exists():
        return path.read_text(), True
    async with sem:
        xml = await full_text_xml(pmcid, client=client)
        await asyncio.sleep(PAUSE_SECONDS)
    if xml is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(xml)
    return xml, False


@flow(name="pubsearch-evidence")
async def pubsearch_evidence(run_id: str, *, limit: int | None = None) -> dict[str, int]:
    logger = get_run_logger()
    hits = await load_hits(run_id)

    # pmcid -> (pmid, {(query_no, terms, field)}); the same paper can be a MED and
    # a PMC record for the same query, so dedupe.
    papers: dict[str, tuple[str, set[tuple[int, str, str]]]] = {}
    for pmid, pmcid, qno, terms, field in hits:
        papers.setdefault(pmcid, (pmid, set()))[1].add((qno, terms, field))
    pmcids = list(papers)[:limit]
    logger.info("Run %s: %d hits, %d papers with a PMCID", run_id, len(hits), len(pmcids))

    counts = dict.fromkeys(("papers", "fetched", "cached", "sentences_found", "no_match"), 0)
    counts["papers"] = len(pmcids)
    rows: list[tuple[str, int, str, str | None]] = []
    sem = asyncio.Semaphore(CONCURRENCY)

    async def one(pmcid: str) -> None:
        xml, cached = await fetch_xml(pmcid, client, sem)
        if xml is None:
            logger.warning("%s: no full text at Europe PMC", pmcid)
            return
        counts["cached" if cached else "fetched"] += 1
        pmid, queries = papers[pmcid]
        for qno, section, sentence in evidence_for(xml, sorted(queries)):
            counts["sentences_found" if sentence else "no_match"] += 1
            rows.append((pmid, qno, section, sentence))

    async with httpx.AsyncClient(timeout=60.0) as client:
        await asyncio.gather(*(one(p) for p in pmcids))

    counts["rows"] = await upsert_evidence(run_id, rows)
    logger.info("Evidence pass done: %s", counts)
    return counts


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--run-id", required=True)
    p.add_argument("--limit", type=int, default=None)
    a = p.parse_args()
    print(asyncio.run(pubsearch_evidence(a.run_id, limit=a.limit)))
