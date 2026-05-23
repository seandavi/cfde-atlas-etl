-- 0014 — Raw layer for CFDE DRC asset manifests.
--
-- Three independent S3 TSVs: dcc assets (linkout templates etc.), file assets
-- (downloadable files), code assets (APIs / scripts). All keyed on `link` (URL)
-- since none expose a stable surrogate id we can rely on.

CREATE TABLE IF NOT EXISTS raw.drc_dcc (
    link       TEXT        NOT NULL PRIMARY KEY,
    dcc_id     TEXT,
    source     JSONB       NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS raw_drc_dcc_dcc_id_idx ON raw.drc_dcc (dcc_id);

COMMENT ON TABLE raw.drc_dcc IS
    'CFDE DRC current_dcc_assets manifest. Linkout templates and per-DCC '
    'assets. dcc_id is the DRC-side DCC UUID; mapping to NIH core_project_number '
    'requires a separate crosswalk (not yet populated, see #11).';

COMMENT ON COLUMN raw.drc_dcc.link IS
    'Asset URL or linkout template. PK.';

COMMENT ON COLUMN raw.drc_dcc.dcc_id IS
    'DRC DCC UUID. Maps to a CFDE DCC (GTEx, LINCS, etc.) via a crosswalk that '
    'eventually links to analytics.core_projects. The crosswalk is not in this table.';


CREATE TABLE IF NOT EXISTS raw.drc_file (
    link       TEXT        NOT NULL PRIMARY KEY,
    filetype   TEXT,
    size_bytes BIGINT,
    source     JSONB       NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS raw_drc_file_filetype_idx ON raw.drc_file (filetype);

COMMENT ON TABLE raw.drc_file IS
    'CFDE DRC current_file_assets manifest. Downloadable files (e.g. C2M2 packages). '
    'Keyed on download URL.';

COMMENT ON COLUMN raw.drc_file.link IS
    'Download URL. PK.';

COMMENT ON COLUMN raw.drc_file.filetype IS
    'Asset filetype label (e.g. C2M2, datapackage).';

COMMENT ON COLUMN raw.drc_file.size_bytes IS
    'File size in bytes, parsed from the manifest size column.';


CREATE TABLE IF NOT EXISTS raw.drc_code (
    link       TEXT        NOT NULL PRIMARY KEY,
    asset_type TEXT,
    source     JSONB       NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS raw_drc_code_type_idx ON raw.drc_code (asset_type);

COMMENT ON TABLE raw.drc_code IS
    'CFDE DRC current_code_assets manifest. Code references (APIs, smartAPI specs, '
    'JSON-LD endpoints, ETL scripts). Keyed on code URL.';

COMMENT ON COLUMN raw.drc_code.link IS
    'Code or API URL. PK.';

COMMENT ON COLUMN raw.drc_code.asset_type IS
    'Asset type (API, ETL, etc.). Mirrors the type column in the manifest.';
