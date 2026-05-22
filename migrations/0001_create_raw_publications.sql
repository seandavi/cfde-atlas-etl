-- 0001 — Create raw layer for publications.
--
-- ELT pattern: source data lands here as-is in jsonb. Typed projections
-- live in the analytics layer (see 0002).

CREATE SCHEMA IF NOT EXISTS raw;

CREATE TABLE IF NOT EXISTS raw.publications (
    pmid                INTEGER     NOT NULL,
    core_project_number TEXT        NOT NULL,
    source              JSONB       NOT NULL,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (pmid, core_project_number)
);

CREATE INDEX IF NOT EXISTS raw_publications_core_project_idx
    ON raw.publications (core_project_number);

CREATE INDEX IF NOT EXISTS raw_publications_year_idx
    ON raw.publications (((source ->> 'year')::INTEGER));

COMMENT ON TABLE raw.publications IS
    'Raw publications from icc-eval-core /data/output/publications.json. '
    'One row per (pmid, core_project_number). Use analytics.publications for queries.';

COMMENT ON COLUMN raw.publications.source IS
    'Source JSON object as provided by icc-eval-core. Field names follow upstream camelCase.';

COMMENT ON COLUMN raw.publications.fetched_at IS
    'When this row was last written by the ETL. Drives cfde-atlas "data refreshed at" footer.';
