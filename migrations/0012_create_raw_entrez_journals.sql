-- 0012 — Raw layer for NCBI Entrez journal lookups.
--
-- Keyed on journal abbreviation (NLM TA field). Each row maps abbrev ->
-- (fulljournalname, electronic ISSN) via PubMed esummary.

CREATE TABLE IF NOT EXISTS raw.entrez_journals (
    abbrev     TEXT        NOT NULL PRIMARY KEY,
    issn       TEXT        NOT NULL DEFAULT '',
    source     JSONB       NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS raw_entrez_journals_issn_idx
    ON raw.entrez_journals (issn)
    WHERE issn <> '';

COMMENT ON TABLE raw.entrez_journals IS
    'NCBI Entrez esummary results for journal abbreviations. Used to resolve '
    'analytics.publications.journal abbreviations to full names + ISSNs.';

COMMENT ON COLUMN raw.entrez_journals.abbrev IS
    'NLM Title Abbreviation. PK. Join key from analytics.publications.journal.';

COMMENT ON COLUMN raw.entrez_journals.issn IS
    'Electronic ISSN with hyphens stripped. Empty string when esummary did not return one.';

COMMENT ON COLUMN raw.entrez_journals.source IS
    'Source JSON: abbrev, name (fulljournalname), issn.';
