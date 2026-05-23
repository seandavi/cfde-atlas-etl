-- 0015 — Analytics views for DRC assets.
--
-- One typed view per asset kind, plus a union "drc_assets" view with an
-- `asset_kind` discriminator. No core_project_number FK yet — see #11.

CREATE OR REPLACE VIEW analytics.drc_dcc_assets AS
SELECT
    link                                        AS asset_url,
    dcc_id,
    source ->> 'creator'                        AS creator,
    NULLIF(source ->> 'lastmodified', '')::TIMESTAMPTZ AS last_modified_at,
    (source ->> 'drcapproved')::BOOLEAN         AS drc_approved,
    (source ->> 'dccapproved')::BOOLEAN         AS dcc_approved,
    (source ->> 'deleted')::BOOLEAN             AS deleted,
    NULLIF(source ->> 'created', '')::TIMESTAMPTZ AS created_at,
    fetched_at                                  AS data_refreshed_at
FROM raw.drc_dcc;

COMMENT ON VIEW analytics.drc_dcc_assets IS
    'CFDE DRC dcc-level assets: linkout templates and DCC-specific resources. '
    'dcc_id is a DRC-side UUID; map to NIH core_project_number via a crosswalk '
    '(not yet populated — see issue #11).';

COMMENT ON COLUMN analytics.drc_dcc_assets.asset_url IS
    'Asset URL or linkout template. PK.';

COMMENT ON COLUMN analytics.drc_dcc_assets.dcc_id IS
    'DRC DCC UUID. Eventually maps to NIH core_project_number (crosswalk pending).';

COMMENT ON COLUMN analytics.drc_dcc_assets.drc_approved IS
    'TRUE if the DRC team has approved this asset.';

COMMENT ON COLUMN analytics.drc_dcc_assets.dcc_approved IS
    'TRUE if the originating DCC has approved this asset.';


CREATE OR REPLACE VIEW analytics.drc_files AS
SELECT
    link               AS file_url,
    source ->> 'filetype'  AS filetype,
    source ->> 'filename'  AS filename,
    size_bytes,
    source ->> 'sha256checksum' AS sha256,
    fetched_at         AS data_refreshed_at
FROM raw.drc_file;

COMMENT ON VIEW analytics.drc_files IS
    'CFDE DRC downloadable file assets (e.g. C2M2 datapackages). One row per URL.';

COMMENT ON COLUMN analytics.drc_files.file_url IS 'Download URL. PK.';
COMMENT ON COLUMN analytics.drc_files.filetype IS 'Asset filetype label (e.g. C2M2).';
COMMENT ON COLUMN analytics.drc_files.filename IS 'Source-side filename.';
COMMENT ON COLUMN analytics.drc_files.size_bytes IS 'File size in bytes.';
COMMENT ON COLUMN analytics.drc_files.sha256 IS 'SHA256 checksum hex; empty when DRC has not computed one.';


CREATE OR REPLACE VIEW analytics.drc_code AS
SELECT
    link                       AS code_url,
    asset_type,
    source ->> 'name'          AS name,
    source ->> 'description'   AS description,
    (source ->> 'openAPISpec')::BOOLEAN  AS has_openapi_spec,
    (source ->> 'smartAPISpec')::BOOLEAN AS has_smartapi_spec,
    source ->> 'smartAPIURL'   AS smartapi_url,
    source ->> 'entityPageExample' AS entity_page_example,
    fetched_at                 AS data_refreshed_at
FROM raw.drc_code;

COMMENT ON VIEW analytics.drc_code IS
    'CFDE DRC code/API assets: APIs, smartAPI specs, JSON-LD endpoints, ETL scripts.';

COMMENT ON COLUMN analytics.drc_code.code_url IS 'Code or API URL. PK.';
COMMENT ON COLUMN analytics.drc_code.asset_type IS 'Asset type (API, ETL, etc.).';
COMMENT ON COLUMN analytics.drc_code.has_smartapi_spec IS 'TRUE if a smartAPI spec exists.';


CREATE OR REPLACE VIEW analytics.drc_assets AS
    SELECT 'dcc'::TEXT AS asset_kind, asset_url AS link, NULL::TEXT AS asset_type,
           dcc_id, NULL::BIGINT AS size_bytes, data_refreshed_at
    FROM analytics.drc_dcc_assets
    UNION ALL
    SELECT 'file'::TEXT, file_url, filetype, NULL::TEXT, size_bytes, data_refreshed_at
    FROM analytics.drc_files
    UNION ALL
    SELECT 'code'::TEXT, code_url, asset_type, NULL::TEXT, NULL::BIGINT, data_refreshed_at
    FROM analytics.drc_code;

COMMENT ON VIEW analytics.drc_assets IS
    'Union of analytics.drc_dcc_assets / drc_files / drc_code with an asset_kind '
    'discriminator. Use the per-kind views for typed columns; use this for "show me '
    'every DRC asset" queries.';

COMMENT ON COLUMN analytics.drc_assets.asset_kind IS 'One of: dcc, file, code.';
