"""Postgres sink for C2M2 datapackages.

Uses psycopg's binary-COPY for the per-table bulk inserts (10M+ row tables).
Idempotency lives in `raw.c2m2_bundles`: we DELETE existing rows for the
(dcc_id, submission_date) tuple before COPY-ing, so re-ingest is safe and
the row_counts map stays accurate.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Iterable
from typing import Any

import psycopg
from psycopg import sql

from cfde_atlas_etl.config import get_settings
from cfde_atlas_etl.sources.c2m2 import C2M2Table


async def fetch_bundle_status(
    dcc_id: str, submission_date: dt.date
) -> tuple[str, str | None] | None:
    """Return (status, bundle_sha256) for an existing bundle row, or None."""
    settings = get_settings()
    async with (
        await psycopg.AsyncConnection.connect(settings.database_url) as conn,
        conn.cursor() as cur,
    ):
        await cur.execute(
            "SELECT status, bundle_sha256 FROM raw.c2m2_bundles "
            "WHERE dcc_id = %s AND submission_date = %s",
            (dcc_id, submission_date),
        )
        row = await cur.fetchone()
    return (row[0], row[1]) if row else None


async def mark_bundle_in_progress(
    *,
    dcc_id: str,
    dcc_abbreviation: str | None,
    submission_date: dt.date,
    bundle_url: str,
    bundle_sha256: str,
    bundle_size_bytes: int,
) -> None:
    settings = get_settings()
    async with (
        await psycopg.AsyncConnection.connect(settings.database_url) as conn,
        conn.cursor() as cur,
    ):
        await cur.execute(
            """
            INSERT INTO raw.c2m2_bundles
                (dcc_id, dcc_abbreviation, submission_date, bundle_url,
                 bundle_sha256, bundle_size_bytes, processed_at, row_counts, status, error)
            VALUES (%s, %s, %s, %s, %s, %s, NOW(), '{}'::jsonb, 'in_progress', NULL)
            ON CONFLICT (dcc_id, submission_date) DO UPDATE SET
                dcc_abbreviation = EXCLUDED.dcc_abbreviation,
                bundle_url = EXCLUDED.bundle_url,
                bundle_sha256 = EXCLUDED.bundle_sha256,
                bundle_size_bytes = EXCLUDED.bundle_size_bytes,
                processed_at = NOW(),
                row_counts = '{}'::jsonb,
                status = 'in_progress',
                error = NULL
            """,
            (
                dcc_id,
                dcc_abbreviation,
                submission_date,
                bundle_url,
                bundle_sha256,
                bundle_size_bytes,
            ),
        )
        await conn.commit()


async def mark_bundle_ok(
    *,
    dcc_id: str,
    submission_date: dt.date,
    row_counts: dict[str, int],
) -> None:
    settings = get_settings()
    async with (
        await psycopg.AsyncConnection.connect(settings.database_url) as conn,
        conn.cursor() as cur,
    ):
        await cur.execute(
            """
            UPDATE raw.c2m2_bundles
            SET status = 'ok', processed_at = NOW(), row_counts = %s, error = NULL
            WHERE dcc_id = %s AND submission_date = %s
            """,
            (json.dumps(row_counts), dcc_id, submission_date),
        )
        await conn.commit()


async def mark_bundle_failed(
    *,
    dcc_id: str,
    submission_date: dt.date,
    error: str,
) -> None:
    settings = get_settings()
    async with (
        await psycopg.AsyncConnection.connect(settings.database_url) as conn,
        conn.cursor() as cur,
    ):
        await cur.execute(
            """
            UPDATE raw.c2m2_bundles
            SET status = 'failed', processed_at = NOW(), error = %s
            WHERE dcc_id = %s AND submission_date = %s
            """,
            (error[:8000], dcc_id, submission_date),
        )
        await conn.commit()


async def reset_bundle_rows(
    *,
    table: C2M2Table,
    dcc_id: str,
    submission_date: dt.date,
) -> None:
    """Delete rows previously loaded for this (dcc_id, submission_date) tuple.

    Ontology + dcc tables are global (shared across DCC submissions) so we only
    purge the per-DCC association/entity tables. Ontology tables are upserted
    by id below instead.
    """
    if table.kind == "ontology" or table.tsv_name == "dcc":
        return
    settings = get_settings()
    async with (
        await psycopg.AsyncConnection.connect(settings.database_url) as conn,
        conn.cursor() as cur,
    ):
        if "dcc_id" in table.columns or table.tsv_name not in {"dcc", "id_namespace"}:
            schema, name = table.table.split(".", 1)
            stmt = sql.SQL("DELETE FROM {tbl} WHERE dcc_id = %s AND submission_date = %s").format(
                tbl=sql.Identifier(schema, name),
            )
            await cur.execute(stmt, (dcc_id, submission_date))
        await conn.commit()


async def copy_rows_into(
    *,
    table: C2M2Table,
    rows: list[tuple[Any, ...]],
    dcc_id: str,
    submission_date: dt.date,
) -> int:
    """Insert rows into the target table via a temp staging table + ON CONFLICT DO NOTHING.

    Direct COPY-into-target trips PK constraints when:
      (a) different DCCs reuse the same natural-key strings (e.g. project namespaces)
      (b) within a single TSV the same natural key appears twice
    Solution: COPY into an unlogged temp table, then INSERT … SELECT … ON CONFLICT DO NOTHING
    so duplicates silently drop. Caller pre-filters NULL-PK rows + in-batch duplicates.

    Ontology tables route through `_upsert_ontology` instead (DO UPDATE keeps the
    richest description across DCCs).
    """
    if table.kind == "ontology":
        return await _upsert_ontology(table, rows, dcc_id, submission_date)

    if not rows:
        return 0

    settings = get_settings()
    schema, name = table.table.split(".", 1)
    target_cols = (*table.columns, "dcc_id", "submission_date")
    cols_sql = sql.SQL(", ").join(sql.Identifier(c) for c in target_cols)
    target_ident = sql.Identifier(schema, name)
    staging_ident = sql.Identifier(f"stg_{name}")

    create_stage = sql.SQL(
        "CREATE TEMP TABLE {stage} (LIKE {tbl} INCLUDING DEFAULTS) ON COMMIT DROP"
    ).format(stage=staging_ident, tbl=target_ident)
    copy_stage = sql.SQL("COPY {stage} ({cols}) FROM STDIN").format(
        stage=staging_ident, cols=cols_sql
    )
    insert_from_stage = sql.SQL(
        "INSERT INTO {tbl} ({cols}) SELECT {cols} FROM {stage} ON CONFLICT DO NOTHING"
    ).format(tbl=target_ident, cols=cols_sql, stage=staging_ident)

    async with await psycopg.AsyncConnection.connect(settings.database_url) as conn:
        async with conn.cursor() as cur:
            await cur.execute(create_stage)
            async with cur.copy(copy_stage) as cp:
                for row in rows:
                    await cp.write_row((*row, dcc_id, submission_date))
            await cur.execute(insert_from_stage)
            inserted = cur.rowcount if cur.rowcount is not None and cur.rowcount >= 0 else len(rows)
        await conn.commit()
    return inserted


async def _upsert_ontology(
    table: C2M2Table,
    rows: Iterable[tuple[Any, ...]],
    dcc_id: str,
    submission_date: dt.date,
) -> int:
    """Ontology tables share rows across DCCs; ON CONFLICT (id) DO UPDATE."""
    payloads: list[dict[str, Any]] = []
    for row in rows:
        d: dict[str, Any] = {table.columns[i]: row[i] for i in range(len(table.columns))}
        d["dcc_id"] = dcc_id
        d["submission_date"] = submission_date
        payloads.append(d)
    if not payloads:
        return 0

    col_list = (*table.columns, "dcc_id", "submission_date")
    placeholders = sql.SQL(", ").join(sql.Placeholder(c) for c in col_list)
    insert_cols = sql.SQL(", ").join(sql.Identifier(c) for c in col_list)
    schema, name = table.table.split(".", 1)
    table_ident = sql.Identifier(schema, name)

    update_assignments = [
        sql.SQL("{col} = COALESCE(EXCLUDED.{col}, {tbl}.{col})").format(
            col=sql.Identifier(c), tbl=table_ident
        )
        for c in table.columns
        if c != "id"
    ]
    if update_assignments:
        update_clause = sql.SQL(", ").join(update_assignments)
        stmt = sql.SQL(
            "INSERT INTO {tbl} ({cols}) VALUES ({ph}) "
            "ON CONFLICT (id) DO UPDATE SET {upd}, fetched_at = NOW()"
        ).format(tbl=table_ident, cols=insert_cols, ph=placeholders, upd=update_clause)
    else:
        stmt = sql.SQL(
            "INSERT INTO {tbl} ({cols}) VALUES ({ph}) ON CONFLICT (id) DO NOTHING"
        ).format(tbl=table_ident, cols=insert_cols, ph=placeholders)

    settings = get_settings()
    async with (
        await psycopg.AsyncConnection.connect(settings.database_url) as conn,
        conn.cursor() as cur,
    ):
        await cur.executemany(stmt, payloads)
        await conn.commit()
    return len(payloads)


_DCC_COLS = (
    "dcc_id",
    "dcc_name",
    "dcc_abbreviation",
    "dcc_description",
    "contact_email",
    "contact_name",
    "dcc_url",
    "project_id_namespace",
    "project_local_id",
    "submission_date",
)


async def upsert_dcc_row(
    *,
    dcc_id: str,
    payload: tuple[Any, ...],
    submission_date: dt.date,
) -> None:
    _ = dcc_id  # kept for caller-side symmetry; dcc_id also lives in payload[0]
    """The dcc.tsv row is the source of truth for DCC identity. Upsert by dcc_id."""
    settings = get_settings()
    values = (*payload, submission_date)
    placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in _DCC_COLS)
    insert_cols = sql.SQL(", ").join(sql.Identifier(c) for c in _DCC_COLS)
    update_clause = sql.SQL(", ").join(
        sql.SQL("{col} = EXCLUDED.{col}").format(col=sql.Identifier(c))
        for c in _DCC_COLS
        if c != "dcc_id"
    )
    stmt = sql.SQL(
        "INSERT INTO c2m2.dcc ({cols}) VALUES ({ph}) "
        "ON CONFLICT (dcc_id) DO UPDATE SET {upd}, fetched_at = NOW()"
    ).format(cols=insert_cols, ph=placeholders, upd=update_clause)
    async with (
        await psycopg.AsyncConnection.connect(settings.database_url) as conn,
        conn.cursor() as cur,
    ):
        await cur.execute(stmt, values)
        await conn.commit()
