-- 0002 — Analytics view for publications.
--
-- This is the contract cfde-atlas reads. Column names, types, and comments
-- here drive the output of cfde-atlas's `describe_table` tool — so the
-- comments are written for the LLM, not for humans.
--
-- To change the shape cfde-atlas sees, change THIS view, not the raw table.

CREATE SCHEMA IF NOT EXISTS analytics;

CREATE OR REPLACE VIEW analytics.publications AS
SELECT
    pmid,
    core_project_number,
    source ->> 'title'                                    AS title,
    source ->> 'journal'                                  AS journal,
    (source ->> 'year')::INTEGER                          AS year,
    COALESCE((source ->> 'citations')::INTEGER, 0)        AS citation_count,
    (source -> 'authors' ->> 0)                           AS first_author,
    source ->> 'doi'                                      AS doi,
    NULLIF(source ->> 'relativeCitationRatio', '')::NUMERIC  AS relative_citation_ratio,
    NULLIF(source ->> 'citationsPerYear', '')::NUMERIC       AS citations_per_year,
    fetched_at                                            AS data_refreshed_at
FROM raw.publications;

COMMENT ON VIEW analytics.publications IS
    'Grant-acknowledging publications, one row per (pmid, core_project_number). '
    'A publication can acknowledge multiple grants and will have one row per grant. '
    'Join key is core_project_number (FK to analytics.grants.core_project_number).';

COMMENT ON COLUMN analytics.publications.pmid IS
    'PubMed identifier. Integer.';

COMMENT ON COLUMN analytics.publications.core_project_number IS
    'NIH core project number, e.g. U54OD036472. The primary navigation key across all tables.';

COMMENT ON COLUMN analytics.publications.citation_count IS
    'Citations as of last ETL refresh (see data_refreshed_at).';

COMMENT ON COLUMN analytics.publications.relative_citation_ratio IS
    'iCite Relative Citation Ratio. Field-normalized citation impact. 1.0 = average for the field.';

COMMENT ON COLUMN analytics.publications.citations_per_year IS
    'Citations divided by years since publication. Useful for comparing recent vs older work.';

COMMENT ON COLUMN analytics.publications.data_refreshed_at IS
    'Timestamp of the most recent ETL load for this row.';
