"""Postgres sinks for the raw layer.

ELT pattern: this writes source records as-is (jsonb) into raw.* tables.
Typed projections happen in the analytics.* views (see migrations/).
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import LiteralString

import psycopg

from cfde_atlas_etl.config import get_settings
from cfde_atlas_etl.models.drc import DrcCodeAsset, DrcDccAsset, DrcFileAsset
from cfde_atlas_etl.models.journal import EntrezJournal, ScimagoRank
from cfde_atlas_etl.models.opportunity import CommonFundOpportunity
from cfde_atlas_etl.models.project import ReporterProject
from cfde_atlas_etl.models.publication import IcitePublication, ReporterPublication

UPSERT_RAW_OPPORTUNITIES_SQL = """
INSERT INTO raw.opportunities (id, source, fetched_at)
VALUES (%(id)s, %(source)s, NOW())
ON CONFLICT (id) DO UPDATE SET
    source = EXCLUDED.source,
    fetched_at = NOW();
"""

UPSERT_RAW_REPORTER_PROJECTS_SQL = """
INSERT INTO raw.reporter_projects (project_num, core_project_number, source, fetched_at)
VALUES (%(project_num)s, %(core_project_number)s, %(source)s, NOW())
ON CONFLICT (project_num) DO UPDATE SET
    core_project_number = EXCLUDED.core_project_number,
    source = EXCLUDED.source,
    fetched_at = NOW();
"""

UPSERT_RAW_REPORTER_PUBLICATIONS_SQL = """
INSERT INTO raw.reporter_publications (pmid, core_project_number, source, fetched_at)
VALUES (%(pmid)s, %(core_project_number)s, %(source)s, NOW())
ON CONFLICT (pmid, core_project_number) DO UPDATE SET
    source = EXCLUDED.source,
    fetched_at = NOW();
"""

UPSERT_RAW_ICITE_SQL = """
INSERT INTO raw.icite (pmid, source, fetched_at)
VALUES (%(pmid)s, %(source)s, NOW())
ON CONFLICT (pmid) DO UPDATE SET
    source = EXCLUDED.source,
    fetched_at = NOW();
"""

UPSERT_RAW_SCIMAGO_RANKS_SQL = """
INSERT INTO raw.scimago_ranks (sourceid, issns, source, fetched_at)
VALUES (%(sourceid)s, %(issns)s, %(source)s, NOW())
ON CONFLICT (sourceid) DO UPDATE SET
    issns = EXCLUDED.issns,
    source = EXCLUDED.source,
    fetched_at = NOW();
"""

UPSERT_RAW_ENTREZ_JOURNALS_SQL = """
INSERT INTO raw.entrez_journals (abbrev, issn, source, fetched_at)
VALUES (%(abbrev)s, %(issn)s, %(source)s, NOW())
ON CONFLICT (abbrev) DO UPDATE SET
    issn = EXCLUDED.issn,
    source = EXCLUDED.source,
    fetched_at = NOW();
"""

UPSERT_RAW_DRC_DCC_SQL = """
INSERT INTO raw.drc_dcc (link, dcc_id, source, fetched_at)
VALUES (%(link)s, %(dcc_id)s, %(source)s, NOW())
ON CONFLICT (link) DO UPDATE SET
    dcc_id = EXCLUDED.dcc_id,
    source = EXCLUDED.source,
    fetched_at = NOW();
"""

UPSERT_RAW_DRC_FILE_SQL = """
INSERT INTO raw.drc_file (link, filetype, size_bytes, source, fetched_at)
VALUES (%(link)s, %(filetype)s, %(size_bytes)s, %(source)s, NOW())
ON CONFLICT (link) DO UPDATE SET
    filetype = EXCLUDED.filetype,
    size_bytes = EXCLUDED.size_bytes,
    source = EXCLUDED.source,
    fetched_at = NOW();
"""

UPSERT_RAW_DRC_CODE_SQL = """
INSERT INTO raw.drc_code (link, asset_type, source, fetched_at)
VALUES (%(link)s, %(asset_type)s, %(source)s, NOW())
ON CONFLICT (link) DO UPDATE SET
    asset_type = EXCLUDED.asset_type,
    source = EXCLUDED.source,
    fetched_at = NOW();
"""

UPSERT_RAW_ICITE_CITATIONS_SQL = """
INSERT INTO raw.icite_citations (cfde_pmid, citing_pmid, fetched_at)
VALUES (%(cfde_pmid)s, %(citing_pmid)s, NOW())
ON CONFLICT (cfde_pmid, citing_pmid) DO UPDATE SET
    fetched_at = NOW();
"""

UPSERT_RAW_ICITE_CITING_PUBS_SQL = """
INSERT INTO raw.icite_citing_pubs (pmid, source, fetched_at)
VALUES (%(pmid)s, %(source)s, NOW())
ON CONFLICT (pmid) DO UPDATE SET
    source = EXCLUDED.source,
    fetched_at = NOW();
"""

UPSERT_RAW_REPORTER_CITING_PUBLICATIONS_SQL = """
INSERT INTO raw.reporter_citing_publications (citing_pmid, core_project_number, source, fetched_at)
VALUES (%(citing_pmid)s, %(core_project_number)s, %(source)s, NOW())
ON CONFLICT (citing_pmid, core_project_number) DO UPDATE SET
    source = EXCLUDED.source,
    fetched_at = NOW();
"""


async def _executemany(sql: LiteralString, payloads: list[dict[str, object]]) -> int:
    if not payloads:
        return 0
    settings = get_settings()
    async with (
        await psycopg.AsyncConnection.connect(settings.database_url) as conn,
        conn.cursor() as cur,
    ):
        await cur.executemany(sql, payloads)
        await conn.commit()
    return len(payloads)


async def upsert_raw_opportunities(sources: Iterable[CommonFundOpportunity]) -> int:
    payloads: list[dict[str, object]] = [
        {"id": s.id, "source": json.dumps(s.model_dump(mode="json"))} for s in sources
    ]
    return await _executemany(UPSERT_RAW_OPPORTUNITIES_SQL, payloads)


async def upsert_raw_reporter_projects(sources: Iterable[ReporterProject]) -> int:
    payloads: list[dict[str, object]] = [
        {
            "project_num": s.project_num,
            "core_project_number": s.core_project_num,
            "source": json.dumps(s.model_dump(mode="json")),
        }
        for s in sources
    ]
    return await _executemany(UPSERT_RAW_REPORTER_PROJECTS_SQL, payloads)


async def upsert_raw_reporter_publications(sources: Iterable[ReporterPublication]) -> int:
    payloads: list[dict[str, object]] = []
    for s in sources:
        if s.coreproject is None:
            # No core_project_number means we can't key this row in the raw table.
            # Skip — RePORTER usually returns a coreproject for grant-acknowledging pubs.
            continue
        payloads.append(
            {
                "pmid": s.pmid,
                "core_project_number": s.coreproject,
                "source": json.dumps(s.model_dump(mode="json")),
            }
        )
    return await _executemany(UPSERT_RAW_REPORTER_PUBLICATIONS_SQL, payloads)


async def upsert_raw_icite(sources: Iterable[IcitePublication]) -> int:
    payloads: list[dict[str, object]] = [
        {"pmid": s.pmid, "source": json.dumps(s.model_dump(mode="json"))} for s in sources
    ]
    return await _executemany(UPSERT_RAW_ICITE_SQL, payloads)


async def upsert_raw_scimago_ranks(sources: Iterable[ScimagoRank]) -> int:
    payloads: list[dict[str, object]] = [
        {
            "sourceid": s.Sourceid,
            "issns": s.issns,
            "source": json.dumps(s.model_dump(mode="json")),
        }
        for s in sources
    ]
    return await _executemany(UPSERT_RAW_SCIMAGO_RANKS_SQL, payloads)


async def upsert_raw_entrez_journals(sources: Iterable[EntrezJournal]) -> int:
    payloads: list[dict[str, object]] = [
        {
            "abbrev": s.abbrev,
            "issn": s.issn,
            "source": json.dumps(s.model_dump(mode="json")),
        }
        for s in sources
    ]
    return await _executemany(UPSERT_RAW_ENTREZ_JOURNALS_SQL, payloads)


async def upsert_raw_drc_dcc(sources: Iterable[DrcDccAsset]) -> int:
    payloads: list[dict[str, object]] = [
        {
            "link": s.link,
            "dcc_id": s.dcc_id,
            "source": json.dumps(s.model_dump(mode="json")),
        }
        for s in sources
    ]
    return await _executemany(UPSERT_RAW_DRC_DCC_SQL, payloads)


async def upsert_raw_drc_file(sources: Iterable[DrcFileAsset]) -> int:
    payloads: list[dict[str, object]] = []
    for s in sources:
        size: int | None
        try:
            size = int(s.size) if s.size else None
        except (TypeError, ValueError):
            size = None
        payloads.append(
            {
                "link": s.link,
                "filetype": s.filetype,
                "size_bytes": size,
                "source": json.dumps(s.model_dump(mode="json")),
            }
        )
    return await _executemany(UPSERT_RAW_DRC_FILE_SQL, payloads)


async def upsert_raw_drc_code(sources: Iterable[DrcCodeAsset]) -> int:
    payloads: list[dict[str, object]] = [
        {
            "link": s.link,
            "asset_type": s.type,
            "source": json.dumps(s.model_dump(mode="json")),
        }
        for s in sources
    ]
    return await _executemany(UPSERT_RAW_DRC_CODE_SQL, payloads)


async def upsert_raw_icite_citations(edges: Iterable[tuple[int, int]]) -> int:
    payloads: list[dict[str, object]] = [
        {"cfde_pmid": cfde_pmid, "citing_pmid": citing_pmid} for cfde_pmid, citing_pmid in edges
    ]
    return await _executemany(UPSERT_RAW_ICITE_CITATIONS_SQL, payloads)


async def upsert_raw_icite_citing_pubs(sources: Iterable[IcitePublication]) -> int:
    payloads: list[dict[str, object]] = [
        {"pmid": s.pmid, "source": json.dumps(s.model_dump(mode="json"))} for s in sources
    ]
    return await _executemany(UPSERT_RAW_ICITE_CITING_PUBS_SQL, payloads)


async def upsert_raw_reporter_citing_publications(
    sources: Iterable[ReporterPublication],
) -> int:
    payloads: list[dict[str, object]] = []
    for s in sources:
        if s.coreproject is None:
            continue
        payloads.append(
            {
                "citing_pmid": s.pmid,
                "core_project_number": s.coreproject,
                "source": json.dumps(s.model_dump(mode="json")),
            }
        )
    return await _executemany(UPSERT_RAW_REPORTER_CITING_PUBLICATIONS_SQL, payloads)
