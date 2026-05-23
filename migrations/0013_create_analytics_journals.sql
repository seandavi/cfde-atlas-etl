-- 0013 — Analytics view for journals.
--
-- Joins entrez_journals.issn to scimago_ranks.issns (TEXT[] containment).
-- abbrev is the FK target from analytics.publications.journal.

CREATE OR REPLACE VIEW analytics.journals AS
SELECT
    ej.abbrev,
    COALESCE(NULLIF(ej.source ->> 'name', ''), ej.abbrev)         AS journal_name,
    sr.source ->> 'Title'                                         AS scimago_title,
    ej.issn,
    NULLIF(REPLACE(sr.source ->> 'SJR', ',', '.'), '')::NUMERIC   AS sjr_score,
    sr.source ->> 'SJR Best Quartile'                             AS sjr_quartile,
    sr.source ->> 'Country'                                       AS country,
    sr.source ->> 'Region'                                        AS region,
    GREATEST(ej.fetched_at, sr.fetched_at)                        AS data_refreshed_at
FROM raw.entrez_journals ej
LEFT JOIN raw.scimago_ranks sr
    ON ej.issn <> '' AND ej.issn = ANY (sr.issns);

COMMENT ON VIEW analytics.journals IS
    'Journal metadata keyed on NLM abbreviation. Use to resolve '
    'analytics.publications.journal to a full name and Scimago Journal Rank.';

COMMENT ON COLUMN analytics.journals.abbrev IS
    'NLM Title Abbreviation. PK. Join key from analytics.publications.journal.';

COMMENT ON COLUMN analytics.journals.journal_name IS
    'Full journal name (PubMed esummary fulljournalname), falling back to the abbreviation.';

COMMENT ON COLUMN analytics.journals.scimago_title IS
    'Title as Scimago publishes it (may differ from PubMed). NULL if no Scimago match.';

COMMENT ON COLUMN analytics.journals.issn IS
    'Electronic ISSN (hyphens stripped). Empty when esummary did not return one.';

COMMENT ON COLUMN analytics.journals.sjr_score IS
    'Scimago Journal Rank score. Higher = more prestigious. NULL when no Scimago match.';

COMMENT ON COLUMN analytics.journals.sjr_quartile IS
    'Scimago best quartile (Q1..Q4). Q1 is top 25 percent in the journal''s primary category.';

COMMENT ON COLUMN analytics.journals.data_refreshed_at IS
    'Most recent fetched_at across the entrez and scimago sides of the join.';
