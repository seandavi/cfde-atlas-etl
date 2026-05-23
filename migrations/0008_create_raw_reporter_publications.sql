-- 0008 — Raw layer for RePORTER /v2/publications/search results.
--
-- One row per (pmid, core_project_number). A publication that acknowledges
-- multiple grants shows up multiple times — that is intentional and the
-- granularity downstream needs for grant-level rollups.

CREATE TABLE IF NOT EXISTS raw.reporter_publications (
    pmid                INTEGER     NOT NULL,
    core_project_number TEXT        NOT NULL,
    source              JSONB       NOT NULL,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (pmid, core_project_number)
);

CREATE INDEX IF NOT EXISTS raw_reporter_publications_core_project_idx
    ON raw.reporter_publications (core_project_number);

COMMENT ON TABLE raw.reporter_publications IS
    'RePORTER /v2/publications/search rows. PK is (pmid, core_project_number) '
    'because a paper acknowledging multiple grants yields multiple rows.';

COMMENT ON COLUMN raw.reporter_publications.pmid IS
    'PubMed ID. Join key into raw.icite for enrichment.';

COMMENT ON COLUMN raw.reporter_publications.core_project_number IS
    'NIH core project number this publication acknowledges. FK to analytics.core_projects.core_project_number.';

COMMENT ON COLUMN raw.reporter_publications.source IS
    'Full RePORTER publication record as returned by /v2/publications/search.';

COMMENT ON COLUMN raw.reporter_publications.fetched_at IS
    'When this row was last written by the ETL.';
