-- 0016 — Raw layer for forward citations of CFDE-funded publications.
--
-- raw.icite_citations is the edge table: one row per (cfde_pmid, citing_pmid).
-- raw.icite_citing_pubs holds the iCite metadata for citing pmids — same shape
-- as raw.icite but kept separate so the CFDE-funded set stays cleanly
-- distinguished from "papers that cite CFDE."

CREATE TABLE IF NOT EXISTS raw.icite_citations (
    cfde_pmid   INTEGER     NOT NULL,
    citing_pmid INTEGER     NOT NULL,
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (cfde_pmid, citing_pmid)
);

CREATE INDEX IF NOT EXISTS raw_icite_citations_citing_idx
    ON raw.icite_citations (citing_pmid);

COMMENT ON TABLE raw.icite_citations IS
    'Forward-citation edges: one row per (CFDE pmid, pmid that cites it). '
    'Derived from raw.icite.source -> cited_by[]. '
    'Drives the "downstream impact" queries used by analytics.citing_publications and '
    'analytics.citing_grants (#13).';

COMMENT ON COLUMN raw.icite_citations.cfde_pmid IS
    'PubMed ID of a CFDE-acknowledging publication. FK to analytics.publications.pmid.';

COMMENT ON COLUMN raw.icite_citations.citing_pmid IS
    'PubMed ID of the paper citing the CFDE pmid. FK to raw.icite_citing_pubs.pmid.';


CREATE TABLE IF NOT EXISTS raw.icite_citing_pubs (
    pmid       INTEGER     NOT NULL PRIMARY KEY,
    source     JSONB       NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS raw_icite_citing_pubs_year_idx
    ON raw.icite_citing_pubs (((source ->> 'year')::INTEGER));

COMMENT ON TABLE raw.icite_citing_pubs IS
    'iCite metadata for pmids that cite CFDE-funded papers (downstream impact). '
    'Same /api/pubs schema as raw.icite — kept in a separate table so the CFDE set '
    'stays a clean primary cohort.';

COMMENT ON COLUMN raw.icite_citing_pubs.pmid IS
    'PubMed ID of a citing paper. PK.';
