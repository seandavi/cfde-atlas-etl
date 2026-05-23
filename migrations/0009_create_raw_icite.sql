-- 0009 — Raw layer for NIH iCite publication metadata.
--
-- iCite is keyed on pmid alone. Citation counts, RCR, journal info, authors,
-- and the cited_by list (used by the citing-publications flow, #12) come from here.

CREATE TABLE IF NOT EXISTS raw.icite (
    pmid       INTEGER     NOT NULL PRIMARY KEY,
    source     JSONB       NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS raw_icite_year_idx
    ON raw.icite (((source ->> 'year')::INTEGER));

COMMENT ON TABLE raw.icite IS
    'NIH iCite /api/pubs records, one per pmid. Source for citation counts, RCR, '
    'authors, journal, and cited_by (forward citations used in #12).';

COMMENT ON COLUMN raw.icite.pmid IS
    'PubMed ID. PK. Join key to raw.reporter_publications.';

COMMENT ON COLUMN raw.icite.source IS
    'Full iCite record (fl=all). Contains title, journal, authors, citation_count, '
    'relative_citation_ratio, citations_per_year, cited_by, references.';

COMMENT ON COLUMN raw.icite.fetched_at IS
    'When this row was last written by the ETL.';
