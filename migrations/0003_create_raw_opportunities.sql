-- 0003 — Create raw layer for funding opportunities.
--
-- Scraped from commonfund.nih.gov/dataecosystem/FundingOpportunities and
-- merged with raw/manual-opportunities.yaml.

CREATE TABLE IF NOT EXISTS raw.opportunities (
    id          TEXT        NOT NULL PRIMARY KEY,
    source      JSONB       NOT NULL,
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS raw_opportunities_prefix_idx
    ON raw.opportunities ((source ->> 'prefix'));

COMMENT ON TABLE raw.opportunities IS
    'Common Fund funding opportunity numbers (RFA-RM-*, NOT-RM-*, OTA-*). '
    'Driven by scrape of commonfund.nih.gov plus manual curation. '
    'Use analytics.opportunities for queries.';

COMMENT ON COLUMN raw.opportunities.id IS
    'Opportunity number string, e.g. RFA-RM-24-006.';

COMMENT ON COLUMN raw.opportunities.source IS
    'Source JSON: id, prefix, activity_code, source_url, plus any extras the scraper adds.';

COMMENT ON COLUMN raw.opportunities.fetched_at IS
    'When this row was last written by the ETL.';
