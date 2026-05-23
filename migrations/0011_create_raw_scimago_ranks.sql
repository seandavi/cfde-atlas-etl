-- 0011 — Raw layer for Scimago Journal Rank dump.
--
-- Sourced from https://www.scimagojr.com/journalrank.php?out=xls (semicolon-CSV
-- despite the .xls). Scimago rate-limits/bans CI IPs; refresh sparingly.

CREATE TABLE IF NOT EXISTS raw.scimago_ranks (
    sourceid   INTEGER     NOT NULL PRIMARY KEY,
    issns      TEXT[]      NOT NULL DEFAULT '{}',
    source     JSONB       NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS raw_scimago_ranks_issns_gin_idx
    ON raw.scimago_ranks USING GIN (issns);

COMMENT ON TABLE raw.scimago_ranks IS
    'Scimago Journal Rank export. One row per Scimago Sourceid. Use the GIN '
    'index on issns to join from raw.entrez_journals.issn.';

COMMENT ON COLUMN raw.scimago_ranks.sourceid IS
    'Scimago internal source id. PK.';

COMMENT ON COLUMN raw.scimago_ranks.issns IS
    'ISSNs as a TEXT[] (hyphens removed). Multi-issn journals have multiple entries.';

COMMENT ON COLUMN raw.scimago_ranks.source IS
    'Full Scimago row: Title, Type, SJR, H index, Country, Region, Quartile, etc.';
