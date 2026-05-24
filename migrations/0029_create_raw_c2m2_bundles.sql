-- 0029 — C2M2 ingest tracker.
--
-- The c2m2 ingest flow downloads + unzips + COPYs the latest C2M2 datapackage per
-- DCC. This table is the per-(dcc, submission_date) ledger that makes the flow
-- idempotent: subsequent runs skip bundles already at status='ok' with matching sha.

CREATE TABLE IF NOT EXISTS raw.c2m2_bundles (
    dcc_id            TEXT        NOT NULL,
    dcc_abbreviation  TEXT,
    submission_date   DATE        NOT NULL,
    bundle_url        TEXT        NOT NULL,
    bundle_sha256     TEXT,
    bundle_size_bytes BIGINT,
    processed_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    row_counts        JSONB       NOT NULL DEFAULT '{}'::JSONB,
    status            TEXT        NOT NULL DEFAULT 'ok',
    error             TEXT,
    PRIMARY KEY (dcc_id, submission_date)
);

CREATE INDEX IF NOT EXISTS raw_c2m2_bundles_url_idx ON raw.c2m2_bundles (bundle_url);

COMMENT ON TABLE raw.c2m2_bundles IS
    'Ingest ledger for C2M2 datapackages. One row per (dcc_id, submission_date). '
    'The flow inserts status=in_progress before unzipping; flips to ok or failed on '
    'completion. row_counts is a JSON map of c2m2 table name -> rows inserted from '
    'this bundle. To force re-ingest, DELETE the row.';

COMMENT ON COLUMN raw.c2m2_bundles.dcc_id IS
    'C2M2 dcc.id (e.g. "cfde_registry_dcc:gtex"). Source of truth for DCC identity.';
COMMENT ON COLUMN raw.c2m2_bundles.submission_date IS
    'Datapackage submission date parsed from the bundle URL path (e.g. /GTEx/C2M2/2025-01-15/).';
COMMENT ON COLUMN raw.c2m2_bundles.bundle_url IS
    'Source URL of the .zip; matches raw.drc_file.link.';
COMMENT ON COLUMN raw.c2m2_bundles.bundle_sha256 IS
    'SHA256 of the zip. Used to detect content drift even when submission_date is unchanged.';
COMMENT ON COLUMN raw.c2m2_bundles.status IS
    'One of: ok, failed, in_progress.';
COMMENT ON COLUMN raw.c2m2_bundles.row_counts IS
    'JSON map of per-c2m2-table rowcounts ingested from this bundle. Helps reason about '
    'whether a re-ingest is needed if a downstream table looks empty.';
