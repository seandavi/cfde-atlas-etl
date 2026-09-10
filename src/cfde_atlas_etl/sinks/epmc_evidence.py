"""Sink for raw.epmc_evidence (see migrations/0033)."""

from __future__ import annotations

from collections.abc import Iterable

from cfde_atlas_etl.sinks.postgres import _executemany

# sentence is NULL when the paper's full text was fetched but the query term did
# not survive exact matching in its section ("API hit, no exact match"). A paper
# with no full text at all gets no row, so the views can tell the two apart.
UPSERT_EVIDENCE_SQL = """
INSERT INTO raw.epmc_evidence (run_id, pmid, query_no, section, sentence, fetched_at)
VALUES (%(run_id)s, %(pmid)s, %(query_no)s, %(section)s, %(sentence)s, NOW())
ON CONFLICT (run_id, pmid, query_no, section) DO UPDATE SET
    sentence = EXCLUDED.sentence,
    fetched_at = NOW();
"""


async def upsert_evidence(run_id: str, rows: Iterable[tuple[str, int, str, str | None]]) -> int:
    """rows: (pmid, query_no, section, sentence_or_None)."""
    payloads: list[dict[str, object]] = [
        {"run_id": run_id, "pmid": pmid, "query_no": qno, "section": section, "sentence": sentence}
        for pmid, qno, section, sentence in rows
    ]
    return await _executemany(UPSERT_EVIDENCE_SQL, payloads)
