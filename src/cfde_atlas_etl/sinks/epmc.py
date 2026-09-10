"""Postgres sink for raw.epmc_runs / raw.epmc_queries / raw.epmc_hits (migration 0033).

Written by flows.pubsearch_run. Column lists mirror the migration exactly.
"""

from __future__ import annotations

from typing import Any

from cfde_atlas_etl.sinks.postgres import _executemany
from cfde_atlas_etl.sources.epmc import EpmcHit

INSERT_RUN_SQL = """
INSERT INTO raw.epmc_runs
    (run_id, program, program_yaml_sha, date_window_start, date_window_end, started_at, notes)
VALUES
    (%(run_id)s, %(program)s, %(program_yaml_sha)s, %(date_window_start)s, %(date_window_end)s,
     NOW(), %(notes)s)
ON CONFLICT (run_id) DO UPDATE SET
    program = EXCLUDED.program,
    program_yaml_sha = EXCLUDED.program_yaml_sha,
    date_window_start = EXCLUDED.date_window_start,
    date_window_end = EXCLUDED.date_window_end,
    started_at = NOW(),
    finished_at = NULL,
    notes = EXCLUDED.notes;
"""

UPSERT_QUERY_SQL = """
INSERT INTO raw.epmc_queries
    (run_id, query_no, program, impact_category, query_cluster, search_terms, search_field,
     or_terms, or_search_field, and_terms, and_search_field, not_terms, not_search_field,
     notes, epmc_query, hit_count, fetched_at)
VALUES
    (%(run_id)s, %(query_no)s, %(program)s, %(impact_category)s, %(query_cluster)s,
     %(search_terms)s, %(search_field)s, %(or_terms)s, %(or_search_field)s, %(and_terms)s,
     %(and_search_field)s, %(not_terms)s, %(not_search_field)s, %(notes)s, %(epmc_query)s,
     %(hit_count)s, NOW())
ON CONFLICT (run_id, query_no) DO UPDATE SET
    program = EXCLUDED.program,
    impact_category = EXCLUDED.impact_category,
    query_cluster = EXCLUDED.query_cluster,
    search_terms = EXCLUDED.search_terms,
    search_field = EXCLUDED.search_field,
    or_terms = EXCLUDED.or_terms,
    or_search_field = EXCLUDED.or_search_field,
    and_terms = EXCLUDED.and_terms,
    and_search_field = EXCLUDED.and_search_field,
    not_terms = EXCLUDED.not_terms,
    not_search_field = EXCLUDED.not_search_field,
    notes = EXCLUDED.notes,
    epmc_query = EXCLUDED.epmc_query,
    hit_count = EXCLUDED.hit_count,
    fetched_at = NOW();
"""

UPSERT_HIT_SQL = """
INSERT INTO raw.epmc_hits
    (run_id, query_no, epmc_id, source, pmid, pmcid, pub_year, is_open_access, title, fetched_at)
VALUES
    (%(run_id)s, %(query_no)s, %(epmc_id)s, %(source)s, %(pmid)s, %(pmcid)s, %(pub_year)s,
     %(is_open_access)s, %(title)s, NOW())
ON CONFLICT (run_id, query_no, source, epmc_id) DO UPDATE SET
    pmid = EXCLUDED.pmid,
    pmcid = EXCLUDED.pmcid,
    pub_year = EXCLUDED.pub_year,
    is_open_access = EXCLUDED.is_open_access,
    title = EXCLUDED.title,
    fetched_at = NOW();
"""

FINISH_RUN_SQL = """
UPDATE raw.epmc_runs SET finished_at = NOW() WHERE run_id = %(run_id)s;
"""


async def insert_run(run: dict[str, Any]) -> int:
    """`run` keys: run_id, program, program_yaml_sha, date_window_start, date_window_end, notes."""
    return await _executemany(INSERT_RUN_SQL, [run])


async def upsert_queries(run_id: str, rows: list[dict[str, Any]]) -> int:
    """`rows`: query_no, the SeedRow fields, epmc_query, hit_count (None until fetched)."""
    return await _executemany(UPSERT_QUERY_SQL, [{"run_id": run_id, **r} for r in rows])


async def upsert_hits(run_id: str, query_no: int, hits: list[EpmcHit]) -> int:
    payloads: list[dict[str, object]] = [
        {
            "run_id": run_id,
            "query_no": query_no,
            "epmc_id": h.id,
            "source": h.source,
            "pmid": h.pmid,
            "pmcid": h.pmcid,
            "pub_year": h.pub_year,
            "is_open_access": h.is_open_access,
            "title": h.title,
        }
        for h in hits
    ]
    return await _executemany(UPSERT_HIT_SQL, payloads)


async def finish_run(run_id: str) -> int:
    return await _executemany(FINISH_RUN_SQL, [{"run_id": run_id}])
