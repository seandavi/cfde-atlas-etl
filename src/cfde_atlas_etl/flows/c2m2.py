"""Prefect flow: ingest C2M2 datapackages.

For each CFDE DCC, find the most recent C2M2 zip in `raw.drc_file`, download
it, unzip it, and COPY each TSV into its `c2m2.*` Postgres table.

Idempotency: a ledger row in `raw.c2m2_bundles` tracks (dcc_id, submission_date,
bundle_sha256, status). Subsequent runs skip bundles already at status='ok'
with a matching sha. Per-bundle failure (download / unzip / COPY) flips the
row to 'failed' + error message; other DCCs continue.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import os
import re
from collections import defaultdict
from typing import Any

import httpx
import psycopg
from prefect import flow, get_run_logger, task
from prefect.cache_policies import NO_CACHE

from cfde_atlas_etl.config import get_settings
from cfde_atlas_etl.sinks.c2m2 import (
    copy_rows_into,
    fetch_bundle_status,
    mark_bundle_failed,
    mark_bundle_in_progress,
    mark_bundle_ok,
    reset_bundle_rows,
    upsert_dcc_row,
)
from cfde_atlas_etl.sources.c2m2 import (
    C2M2_TABLES,
    C2M2_TABLES_BY_TSV,
    download_bundle,
    iter_bundle_rows,
    open_bundle,
    parse_submission_date_from_url,
)

DCC_PATH_RE = re.compile(r"cfde-drc\.s3\.amazonaws\.com/([^/]+)/C2M2/")

# 9+ GB zips and full unzip in memory — keep concurrency low.
BUNDLE_CONCURRENCY = int(os.environ.get("CFDE_C2M2_BUNDLE_CONCURRENCY", "2"))


@task
async def discover_latest_bundles() -> list[dict[str, Any]]:
    """For each DCC seen in raw.drc_file C2M2 zips, return the most-recent submission URL."""
    settings = get_settings()
    async with (
        await psycopg.AsyncConnection.connect(settings.database_url) as conn,
        conn.cursor() as cur,
    ):
        await cur.execute(
            """
            SELECT link, size_bytes
            FROM raw.drc_file
            WHERE source ->> 'filetype' = 'C2M2'
              AND link LIKE 'https://cfde-drc.s3.amazonaws.com/%/C2M2/%'
              AND link LIKE '%.zip'
            """
        )
        rows = await cur.fetchall()

    grouped: dict[str, list[tuple[str, str, int | None]]] = defaultdict(list)
    for link, size_bytes in rows:
        path_match = DCC_PATH_RE.search(link)
        date = parse_submission_date_from_url(link)
        if not path_match or not date:
            continue
        grouped[path_match.group(1)].append((date, link, size_bytes))

    latest: list[dict[str, Any]] = []
    for dcc_dir, entries in grouped.items():
        entries.sort(reverse=True)
        date, link, size_bytes = entries[0]
        latest.append(
            {
                "dcc_dir": dcc_dir,
                "submission_date": dt.date.fromisoformat(date),
                "url": link,
                "size_bytes": size_bytes,
            }
        )
    latest.sort(key=lambda x: x["size_bytes"] or 0)
    return latest


@task(retries=2, retry_delay_seconds=60, cache_policy=NO_CACHE)
async def ingest_bundle(bundle: dict[str, Any], client: httpx.AsyncClient) -> dict[str, Any]:
    logger = get_run_logger()
    url: str = bundle["url"]
    submission_date: dt.date = bundle["submission_date"]
    dcc_dir: str = bundle["dcc_dir"]

    logger.info("Downloading C2M2 bundle: %s (%s bytes)", url, bundle.get("size_bytes"))
    content, sha = await download_bundle(url, client=client)

    # Open and locate the dcc.tsv row first so we know the authoritative dcc_id.
    with open_bundle(content) as zf:
        dcc_table = C2M2_TABLES_BY_TSV["dcc"]
        dcc_rows = list(iter_bundle_rows(zf, dcc_table))
        if not dcc_rows:
            raise RuntimeError(f"{url} has no dcc.tsv content")
        dcc_payload = dcc_rows[0]
        dcc_id: str = dcc_payload[0] or f"unknown:{dcc_dir.lower()}"
        dcc_abbreviation = dcc_payload[2] or dcc_dir

        existing = await fetch_bundle_status(dcc_id, submission_date)
        if existing and existing[0] == "ok" and existing[1] == sha:
            logger.info(
                "Skipping %s (%s) — bundle already ingested with matching sha",
                dcc_id,
                submission_date,
            )
            return {"dcc_id": dcc_id, "submission_date": submission_date, "skipped": True}

        await mark_bundle_in_progress(
            dcc_id=dcc_id,
            dcc_abbreviation=dcc_abbreviation,
            submission_date=submission_date,
            bundle_url=url,
            bundle_sha256=sha,
            bundle_size_bytes=len(content),
        )

        # Write the dcc row first so other tables' dcc_id references resolve cleanly.
        await upsert_dcc_row(dcc_id=dcc_id, payload=dcc_payload, submission_date=submission_date)

        row_counts: dict[str, int] = {"dcc": 1}
        try:
            for table in C2M2_TABLES:
                if table.tsv_name == "dcc":
                    continue
                await reset_bundle_rows(table=table, dcc_id=dcc_id, submission_date=submission_date)
                rows = list(iter_bundle_rows(zf, table))
                if not rows:
                    continue
                inserted = await copy_rows_into(
                    table=table,
                    rows=rows,
                    dcc_id=dcc_id,
                    submission_date=submission_date,
                )
                row_counts[table.tsv_name] = inserted
        except Exception as exc:
            await mark_bundle_failed(
                dcc_id=dcc_id, submission_date=submission_date, error=repr(exc)
            )
            raise

    await mark_bundle_ok(dcc_id=dcc_id, submission_date=submission_date, row_counts=row_counts)
    logger.info(
        "OK %s (%s) — counts: %s",
        dcc_id,
        submission_date,
        {k: v for k, v in row_counts.items() if v},
    )
    return {
        "dcc_id": dcc_id,
        "submission_date": submission_date,
        "row_counts": row_counts,
        "skipped": False,
    }


@flow(name="load-c2m2")
async def load_c2m2() -> dict[str, Any]:
    logger = get_run_logger()

    bundles = await discover_latest_bundles()
    logger.info("Discovered %d C2M2 bundles (latest per DCC)", len(bundles))
    if not bundles:
        return {"bundles": 0, "ok": 0, "failed": 0, "skipped": 0}

    sem = asyncio.Semaphore(BUNDLE_CONCURRENCY)
    results: list[dict[str, Any] | Exception] = []

    async with httpx.AsyncClient(timeout=httpx.Timeout(900.0, connect=60.0)) as client:

        async def one(b: dict[str, Any]) -> dict[str, Any] | Exception:
            async with sem:
                try:
                    return await ingest_bundle(b, client)
                except Exception as exc:
                    logger.warning("ingest_bundle failed for %s: %s", b["url"], exc)
                    return exc

        results = await asyncio.gather(*(one(b) for b in bundles))

    ok = sum(1 for r in results if isinstance(r, dict) and not r.get("skipped"))
    skipped = sum(1 for r in results if isinstance(r, dict) and r.get("skipped"))
    failed = sum(1 for r in results if isinstance(r, Exception))
    logger.info("C2M2 ingest summary: ok=%d skipped=%d failed=%d", ok, skipped, failed)
    return {"bundles": len(bundles), "ok": ok, "skipped": skipped, "failed": failed}


if __name__ == "__main__":
    asyncio.run(load_c2m2())
