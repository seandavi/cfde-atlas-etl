"""Postgres sink for the raw layer.

ELT pattern: this writes source records as-is (jsonb) into raw.* tables.
Typed projections happen in the analytics.* views (see migrations/).

Upsert key: (pmid, core_project_number). Refresh stamp: fetched_at = NOW()
on every upserted row.
"""

from __future__ import annotations

import json
from collections.abc import Iterable

import psycopg

from cfde_atlas_etl.config import get_settings
from cfde_atlas_etl.models.publications import IccEvalPublication

UPSERT_RAW_PUBLICATIONS_SQL = """
INSERT INTO raw.publications (pmid, core_project_number, source, fetched_at)
VALUES (%(pmid)s, %(core_project_number)s, %(source)s, NOW())
ON CONFLICT (pmid, core_project_number) DO UPDATE SET
    source = EXCLUDED.source,
    fetched_at = NOW();
"""


async def upsert_raw_publications(sources: Iterable[IccEvalPublication]) -> int:
    """Upsert raw publications. Returns row count attempted."""
    settings = get_settings()
    payloads = [
        {
            "pmid": s.id,
            "core_project_number": s.coreProject,
            # model_dump_json gives a JSON string; psycopg will store as jsonb
            # via the column type, but explicit json.dumps keeps the round-trip clean
            "source": json.dumps(s.model_dump(mode="json")),
        }
        for s in sources
    ]
    if not payloads:
        return 0

    async with await psycopg.AsyncConnection.connect(settings.database_url) as conn:
        async with conn.cursor() as cur:
            await cur.executemany(UPSERT_RAW_PUBLICATIONS_SQL, payloads)
        await conn.commit()

    return len(payloads)
