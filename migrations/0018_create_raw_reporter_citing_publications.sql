-- 0018 — Raw layer for RePORTER grants supporting publications that cite CFDE work.
--
-- Same shape as raw.reporter_publications but logically distinct: these
-- grants are downstream of CFDE, not CFDE itself.

CREATE TABLE IF NOT EXISTS raw.reporter_citing_publications (
    citing_pmid         INTEGER     NOT NULL,
    core_project_number TEXT        NOT NULL,
    source              JSONB       NOT NULL,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (citing_pmid, core_project_number)
);

CREATE INDEX IF NOT EXISTS raw_reporter_citing_publications_core_project_idx
    ON raw.reporter_citing_publications (core_project_number);

COMMENT ON TABLE raw.reporter_citing_publications IS
    'RePORTER /v2/publications/search rows for pmids that cite CFDE publications. '
    'PK is (citing_pmid, core_project_number) — a citing paper acknowledging '
    'multiple downstream grants yields multiple rows. These grants are NOT CFDE; '
    'this table is the downstream-funding view used by analytics.citing_grants.';

COMMENT ON COLUMN raw.reporter_citing_publications.citing_pmid IS
    'PubMed ID of a paper that cites a CFDE publication. FK to raw.icite_citations.citing_pmid.';

COMMENT ON COLUMN raw.reporter_citing_publications.core_project_number IS
    'NIH core project number that the citing paper acknowledges. NOT CFDE.';
