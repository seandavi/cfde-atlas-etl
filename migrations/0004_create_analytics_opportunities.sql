-- 0004 — Analytics view for funding opportunities.
--
-- Drives `analytics.opportunities` description in cfde-atlas describe_table.
-- Column comments are the LLM-facing contract.

CREATE OR REPLACE VIEW analytics.opportunities AS
SELECT
    id                                  AS opportunity_number,
    source ->> 'prefix'                 AS prefix,
    source ->> 'activity_code'          AS activity_code,
    source ->> 'source_url'             AS source_url,
    fetched_at                          AS data_refreshed_at
FROM raw.opportunities;

COMMENT ON VIEW analytics.opportunities IS
    'NIH Common Fund Data Ecosystem funding opportunity numbers. '
    'One row per opportunity. Used as a join key in analytics.projects.opportunity_number.';

COMMENT ON COLUMN analytics.opportunities.opportunity_number IS
    'Funding opportunity announcement (FOA) number such as RFA-RM-24-006, '
    'NOT-RM-23-014, or OTA-23-004. The primary key.';

COMMENT ON COLUMN analytics.opportunities.prefix IS
    'One of: RFA (Request for Applications), NOT (Notice), OTA (Other Transaction Authority).';

COMMENT ON COLUMN analytics.opportunities.activity_code IS
    'NIH activity code parsed from the FOA page (e.g. U54, U24, R03). '
    'Empty for PDF FOAs where the code is not machine-extractable.';

COMMENT ON COLUMN analytics.opportunities.source_url IS
    'URL of the FOA document the row was parsed from.';

COMMENT ON COLUMN analytics.opportunities.data_refreshed_at IS
    'Timestamp of the most recent ETL load for this row.';
