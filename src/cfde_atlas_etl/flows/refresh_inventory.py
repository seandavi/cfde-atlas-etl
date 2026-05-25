"""Refresh analytics.data_inventory.

Enumerates every relation under selected schemas, runs `COUNT(*)` and
`MAX(data_refreshed_at)` (where present), and replaces the inventory table.

Called as the last step of `flows.load_all`. Can also be run standalone:

    uv run python -m cfde_atlas_etl.flows.refresh_inventory
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import psycopg
from prefect import flow, get_run_logger, task

from cfde_atlas_etl.config import get_settings

INVENTORIED_SCHEMAS = ("analytics", "raw", "c2m2")

# Topical grouping for chat / README / about-page presentation.
# (regex against fully-qualified name -> section label, first match wins)
SECTION_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^analytics\.opportunities$"), "opportunities-projects-pubs"),
    (re.compile(r"^analytics\.(core_)?projects$"), "opportunities-projects-pubs"),
    (re.compile(r"^analytics\.publications$"), "opportunities-projects-pubs"),
    (re.compile(r"^analytics\.journals$"), "opportunities-projects-pubs"),
    (re.compile(r"^analytics\.citing_publications$"), "forward-citations"),
    (re.compile(r"^analytics\.citing_grants"), "forward-citations"),
    (re.compile(r"^analytics\.citing_grant_details$"), "forward-citations"),
    (re.compile(r"^analytics\.citing_funding_by_"), "forward-citations"),
    (re.compile(r"^analytics\.drc"), "drc"),
    (re.compile(r"^analytics\.c2m2_"), "c2m2"),
    (re.compile(r"^analytics\.github"), "github"),
    (re.compile(r"^analytics\.ga"), "ga"),
    (re.compile(r"^analytics\.data_inventory$"), "infra"),
    (re.compile(r"^c2m2\."), "c2m2"),
    (re.compile(r"^raw\."), "raw"),
)


def section_for(qname: str) -> str | None:
    for pat, section in SECTION_RULES:
        if pat.match(qname):
            return section
    return None


@task
async def enumerate_relations() -> list[dict[str, Any]]:
    """Return every table / view / matview in the inventoried schemas."""
    settings = get_settings()
    async with (
        await psycopg.AsyncConnection.connect(settings.database_url) as conn,
        conn.cursor() as cur,
    ):
        await cur.execute(
            """
            SELECT n.nspname, c.relname, c.relkind, c.oid
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = ANY (%s)
              AND c.relkind IN ('r','v','m')
            ORDER BY n.nspname, c.relname
            """,
            (list(INVENTORIED_SCHEMAS),),
        )
        rows = await cur.fetchall()
        out: list[dict[str, Any]] = []
        for schema, name, relkind, oid in rows:
            kind = {"r": "table", "v": "view", "m": "matview"}.get(relkind, relkind)
            await cur.execute("SELECT obj_description(%s::oid)", (oid,))
            desc_row = await cur.fetchone()
            description = desc_row[0] if desc_row else None
            await cur.execute(
                """
                SELECT a.attname
                FROM pg_attribute a
                WHERE a.attrelid = %s
                  AND a.attname = 'data_refreshed_at'
                  AND NOT a.attisdropped
                """,
                (oid,),
            )
            has_refresh = await cur.fetchone() is not None
            out.append(
                {
                    "schema": schema,
                    "name": name,
                    "kind": kind,
                    "description": description,
                    "has_refresh_col": has_refresh,
                }
            )
    return out


@task
async def collect_stats(relations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """For each relation, run COUNT(*) and (when present) MAX(data_refreshed_at)."""
    settings = get_settings()
    logger = get_run_logger()
    out: list[dict[str, Any]] = []
    async with (
        await psycopg.AsyncConnection.connect(settings.database_url) as conn,
        conn.cursor() as cur,
    ):
        for rel in relations:
            qname = f"{rel['schema']}.{rel['name']}"
            try:
                from psycopg import sql

                count_stmt = sql.SQL("SELECT COUNT(*) FROM {}").format(
                    sql.Identifier(rel["schema"], rel["name"])
                )
                await cur.execute(count_stmt)
                count_row = await cur.fetchone()
                row_count = count_row[0] if count_row else None
                data_refreshed_at = None
                if rel["has_refresh_col"]:
                    refresh_stmt = sql.SQL("SELECT MAX(data_refreshed_at) FROM {}").format(
                        sql.Identifier(rel["schema"], rel["name"])
                    )
                    await cur.execute(refresh_stmt)
                    refresh_row = await cur.fetchone()
                    data_refreshed_at = refresh_row[0] if refresh_row else None
            except Exception as exc:
                logger.warning("inventory failed for %s: %s", qname, exc)
                row_count = None
                data_refreshed_at = None
            out.append(
                {
                    "qname": qname,
                    "schema": rel["schema"],
                    "name": rel["name"],
                    "kind": rel["kind"],
                    "section": section_for(qname),
                    "description": rel["description"],
                    "row_count": row_count,
                    "data_refreshed_at": data_refreshed_at,
                }
            )
    return out


@task
async def replace_inventory(stats: list[dict[str, Any]]) -> int:
    settings = get_settings()
    async with await psycopg.AsyncConnection.connect(settings.database_url) as conn:
        async with conn.cursor() as cur:
            await cur.execute("TRUNCATE analytics.data_inventory")
            await cur.executemany(
                """
                INSERT INTO analytics.data_inventory
                    (qname, schema_name, relation_name, kind, section, description,
                     row_count, data_refreshed_at, last_inventoried_at)
                VALUES (%(qname)s, %(schema)s, %(name)s, %(kind)s, %(section)s,
                        %(description)s, %(row_count)s, %(data_refreshed_at)s, NOW())
                """,
                stats,
            )
        await conn.commit()
    return len(stats)


@flow(name="refresh-data-inventory")
async def refresh_inventory() -> int:
    logger = get_run_logger()
    rels = await enumerate_relations()
    logger.info("Inventorying %d relations", len(rels))
    stats = await collect_stats(rels)
    written = await replace_inventory(stats)
    logger.info("Wrote %d rows into analytics.data_inventory", written)
    return written


def _json_default(obj: object) -> object:
    """JSON encoder fallback for psycopg's datetime-like values when dumping for debug."""
    return str(obj)


def stats_to_json(stats: list[dict[str, object]]) -> str:
    return json.dumps(stats, default=_json_default, indent=2)


if __name__ == "__main__":
    asyncio.run(refresh_inventory())
