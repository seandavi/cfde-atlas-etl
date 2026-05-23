-- 0017 — Analytics view for citing publications.
--
-- Joins the (cfde_pmid, citing_pmid) edges to citing-pub metadata from
-- raw.icite_citing_pubs. Use this to answer "what papers cite CFDE work?"
-- and roll up by cfde_pmid for per-paper impact.

CREATE OR REPLACE VIEW analytics.citing_publications AS
SELECT
    c.cfde_pmid,
    c.citing_pmid,
    p.source ->> 'title'                                            AS citing_title,
    p.source ->> 'journal'                                          AS citing_journal,
    NULLIF(p.source ->> 'year', '')::INTEGER                        AS citing_year,
    p.source ->> 'doi'                                              AS citing_doi,
    NULLIF(p.source ->> 'relative_citation_ratio', '')::NUMERIC     AS citing_rcr,
    NULLIF(p.source ->> 'citation_count', '')::INTEGER              AS citing_citation_count,
    GREATEST(c.fetched_at, COALESCE(p.fetched_at, c.fetched_at))    AS data_refreshed_at
FROM raw.icite_citations c
LEFT JOIN raw.icite_citing_pubs p ON p.pmid = c.citing_pmid;

COMMENT ON VIEW analytics.citing_publications IS
    'Forward citations of CFDE-funded papers. One row per (cfde_pmid, citing_pmid). '
    'Join to analytics.publications on cfde_pmid for the CFDE paper, or to '
    'analytics.citing_grants (#13) for downstream funding attribution.';

COMMENT ON COLUMN analytics.citing_publications.cfde_pmid IS
    'PubMed ID of a CFDE-acknowledging paper being cited. FK to analytics.publications.pmid.';

COMMENT ON COLUMN analytics.citing_publications.citing_pmid IS
    'PubMed ID of the citing paper. FK to analytics.citing_grants.citing_pmid (#13).';

COMMENT ON COLUMN analytics.citing_publications.citing_rcr IS
    'iCite Relative Citation Ratio of the citing paper. Useful to weight downstream impact.';

COMMENT ON COLUMN analytics.citing_publications.data_refreshed_at IS
    'Max of the edge fetch time and the citing-pub iCite fetch time.';
