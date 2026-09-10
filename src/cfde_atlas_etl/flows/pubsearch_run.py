"""Prefect flow: seed table -> Europe PMC -> raw.epmc_runs / epmc_queries / epmc_hits.

One run per (program, timestamp, program yaml sha). See docs/pubsearch/SPEC.md.
Not part of load_all unless PUBSEARCH_PROGRAMS is set.
"""

from __future__ import annotations

import asyncio
import hashlib
import subprocess
import time
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

import httpx
from prefect import flow, get_run_logger, task

from cfde_atlas_etl.pubsearch.models import SeedRow
from cfde_atlas_etl.pubsearch.seeds import PROGRAMS_DIR, build_seeds, load_program
from cfde_atlas_etl.sinks.epmc import finish_run, insert_run, upsert_hits, upsert_queries
from cfde_atlas_etl.sources.epmc import EpmcHit, build_query, hit_count, search

MAX_IN_FLIGHT = 5
MIN_REQUEST_INTERVAL = 0.1  # seconds -> <= 10 requests/s overall

_sem = asyncio.Semaphore(MAX_IN_FLIGHT)
_throttle = asyncio.Lock()
_last_request = 0.0


async def _throttle_hook(_request: httpx.Request) -> None:
    """httpx request hook: space every outbound Europe PMC request >= MIN_REQUEST_INTERVAL."""
    global _last_request
    async with _throttle:
        wait = _last_request + MIN_REQUEST_INTERVAL - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        _last_request = time.monotonic()


def yaml_sha(program: str) -> str:
    """Git blob sha of pubsearch/programs/<program>.yaml (sha256 of the bytes if git is missing)."""
    path = PROGRAMS_DIR / f"{program}.yaml"
    try:
        return subprocess.run(
            ["git", "hash-object", str(path)], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return hashlib.sha256(path.read_bytes()).hexdigest()


def make_run_id(program: str, sha: str, now: datetime | None = None) -> str:
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%S")
    return f"{program}-{stamp}-{sha[:7]}"


def render_query(row: SeedRow, window: tuple[int, int] | None) -> str:
    return build_query(
        row.search_terms,
        row.search_field,
        and_terms=row.and_terms,
        and_section=row.and_search_field,
        or_terms=row.or_terms,
        or_section=row.or_search_field,
        not_terms=row.not_terms,
        not_section=row.not_search_field,
        date_window=window,
    )


def query_rows(
    rows: list[SeedRow], program: str, window: tuple[int, int] | None
) -> list[dict[str, Any]]:
    """raw.epmc_queries payloads, query_no 1-based in seed order, hit_count None until fetched."""
    return [
        {
            "query_no": i,
            "program": program,
            **asdict(row),
            "epmc_query": render_query(row, window),
            "hit_count": None,
        }
        for i, row in enumerate(rows, start=1)
    ]


@task(retries=3, retry_delay_seconds=15)
async def build_seed_rows(program: str) -> list[SeedRow]:
    return await build_seeds(program)


@task(retries=3, retry_delay_seconds=15)
async def run_query(run_id: str, row: dict[str, Any]) -> tuple[int, set[str]]:
    """Fetch hitCount + every hit for one query; write the query row and its hits."""
    async with (
        _sem,
        httpx.AsyncClient(timeout=60.0, event_hooks={"request": [_throttle_hook]}) as c,
    ):
        row["hit_count"] = await hit_count(row["epmc_query"], client=c)
        hits = [EpmcHit.from_result(r) async for r in search(row["epmc_query"], client=c)]
    await upsert_queries(run_id, [row])
    n = await upsert_hits(run_id, row["query_no"], hits)
    return n, {h.pmid for h in hits if h.pmid}


@flow(name="pubsearch-run")
async def pubsearch_run(
    program: str,
    *,
    date_window: tuple[int, int] | None = None,
    limit: int | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    logger = get_run_logger()
    t0 = time.monotonic()
    window = date_window or load_program(program).date_window
    sha = yaml_sha(program)
    run_id = make_run_id(program, sha)

    seeds = await build_seed_rows(program)
    rows = query_rows(seeds[:limit], program, window)
    logger.info("Run %s: %d/%d seed rows, window=%s", run_id, len(rows), len(seeds), window)

    await insert_run(
        {
            "run_id": run_id,
            "program": program,
            "program_yaml_sha": sha,
            "date_window_start": window[0] if window else None,
            "date_window_end": window[1] if window else None,
            "notes": notes,
        }
    )
    await upsert_queries(run_id, rows)  # rows exist (hit_count NULL) before any hits land

    results = await asyncio.gather(*(run_query(run_id, r) for r in rows))
    await finish_run(run_id)

    pmids: set[str] = set().union(*(p for _, p in results)) if results else set()
    out = {
        "run_id": run_id,
        "query_count": len(rows),
        "hit_rows": sum(n for n, _ in results),
        "distinct_pmids": len(pmids),
        "duration": round(time.monotonic() - t0, 1),
    }
    logger.info("Run %s done: %s", run_id, out)
    return out


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Run a program's seed queries against Europe PMC.")
    p.add_argument("--program", required=True)
    p.add_argument("--limit", type=int, help="only the first N seed rows (smoke tests)")
    p.add_argument("--date-window", nargs=2, type=int, metavar=("START", "END"))
    p.add_argument("--notes", help="free text for raw.epmc_runs.notes")
    a = p.parse_args()
    window = (a.date_window[0], a.date_window[1]) if a.date_window else None
    print(asyncio.run(pubsearch_run(a.program, date_window=window, limit=a.limit, notes=a.notes)))
