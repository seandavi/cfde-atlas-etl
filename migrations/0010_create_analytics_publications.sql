-- 0010 — Analytics view for publications.
--
-- LEFT JOIN raw.icite onto raw.reporter_publications by pmid. A publication
-- may be absent from iCite (rare); we still surface the RePORTER fields in
-- that case.
--
-- This view is the LLM-facing contract for cfde-atlas's describe_table.
-- Change THIS view, not the raw tables, when adjusting what chat queries see.

CREATE OR REPLACE VIEW analytics.publications AS
SELECT
    rp.pmid,
    rp.core_project_number,
    COALESCE(i.source ->> 'title',     rp.source ->> 'pub_title')   AS title,
    COALESCE(i.source ->> 'journal',   rp.source ->> 'journal_title') AS journal,
    NULLIF(COALESCE(i.source ->> 'year', rp.source ->> 'pub_year'), '')::INTEGER AS year,
    COALESCE(NULLIF(i.source ->> 'citation_count', '')::INTEGER, 0)  AS citation_count,
    (i.source -> 'authors' -> 0 ->> 'fullName')                      AS first_author,
    COALESCE(i.source ->> 'doi',       rp.source ->> 'doi')          AS doi,
    NULLIF(i.source ->> 'relative_citation_ratio', '')::NUMERIC      AS relative_citation_ratio,
    NULLIF(i.source ->> 'citations_per_year',     '')::NUMERIC       AS citations_per_year,
    NULLIF(i.source ->> 'last_modified', '')::DATE                   AS last_modified,
    rp.fetched_at                                                    AS data_refreshed_at
FROM raw.reporter_publications rp
LEFT JOIN raw.icite i USING (pmid);

COMMENT ON VIEW analytics.publications IS
    'Grant-acknowledging publications, one row per (pmid, core_project_number). '
    'A paper acknowledging multiple grants yields one row per grant. '
    'Join key to grants is core_project_number.';

COMMENT ON COLUMN analytics.publications.pmid IS
    'PubMed identifier. Integer. Stable across the lifetime of a paper.';

COMMENT ON COLUMN analytics.publications.core_project_number IS
    'NIH core project number, e.g. U54OD036472. The primary navigation key across all tables. '
    'FK to analytics.core_projects.core_project_number.';

COMMENT ON COLUMN analytics.publications.title IS
    'Article title. Sourced from iCite when present, with RePORTER pub_title as fallback.';

COMMENT ON COLUMN analytics.publications.journal IS
    'Journal name (abbreviation). Resolves to a full title in analytics.journals via the abbrev join.';

COMMENT ON COLUMN analytics.publications.citation_count IS
    'Cumulative citations as of last ETL refresh (see data_refreshed_at). From iCite.';

COMMENT ON COLUMN analytics.publications.first_author IS
    'First author full name (iCite authors[0].fullName).';

COMMENT ON COLUMN analytics.publications.relative_citation_ratio IS
    'iCite Relative Citation Ratio. Field-normalized citation impact. 1.0 = average for the field. '
    'See https://icite.od.nih.gov for definition.';

COMMENT ON COLUMN analytics.publications.citations_per_year IS
    'Citations divided by years since publication. Useful for comparing recent vs older work.';

COMMENT ON COLUMN analytics.publications.last_modified IS
    'iCite last_modified date — when iCite last refreshed this record upstream.';

COMMENT ON COLUMN analytics.publications.data_refreshed_at IS
    'Timestamp of the most recent ETL load for this row (RePORTER side).';
