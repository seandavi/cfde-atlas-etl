-- 0023 — Analytics views for Google Analytics reports.
--
-- Views are kind-specific (each parses out dimension columns) plus a
-- property-coverage view useful for chat ("do we have data for X DCC?").
--
-- The reports are stored unparsed in raw.ga_reports.source. Each view
-- unrolls source -> rows[] -> dimensionValues + metricValues by index, with
-- column comments tied to each report's known schema.

CREATE OR REPLACE VIEW analytics.ga_property_coverage AS
SELECT
    p.property_id,
    p.display_name,
    p.hostname,
    p.core_project_number,
    p.dcc,
    p.granted_at,
    COUNT(r.*)::INTEGER                   AS report_count,
    MAX(r.fetched_at)                     AS last_loaded_at
FROM raw.ga_properties p
LEFT JOIN raw.ga_reports r ON r.property_id = p.property_id
GROUP BY p.property_id, p.display_name, p.hostname, p.core_project_number, p.dcc, p.granted_at;

COMMENT ON VIEW analytics.ga_property_coverage IS
    'GA properties this ETL is authorized for, plus how many reports we have stored. '
    'Use to answer "do we have GA data for DCC X?" — zero report_count means access '
    'was granted but no run has landed yet.';

COMMENT ON COLUMN analytics.ga_property_coverage.report_count IS
    'Number of (report_kind, period) tuples currently in raw.ga_reports for this property.';


CREATE OR REPLACE VIEW analytics.ga_pageviews AS
SELECT
    p.property_id,
    p.core_project_number,
    -- GA returns dates as YYYYMMDD strings; reshape to ISO.
    (REGEXP_REPLACE(row_data -> 'dimensionValues' -> 0 ->> 'value', '(\d{4})(\d{2})(\d{2})', '\1-\2-\3'))::DATE
                                                                AS event_date,
    (row_data -> 'metricValues' -> 0 ->> 'value')::INTEGER      AS page_views,
    (row_data -> 'metricValues' -> 1 ->> 'value')::INTEGER      AS total_users,
    (row_data -> 'metricValues' -> 2 ->> 'value')::INTEGER      AS sessions,
    (row_data -> 'metricValues' -> 3 ->> 'value')::NUMERIC      AS avg_session_seconds,
    r.fetched_at                                                AS data_refreshed_at
FROM raw.ga_reports r
JOIN raw.ga_properties p USING (property_id)
CROSS JOIN LATERAL jsonb_array_elements(COALESCE(r.source -> 'rows', '[]'::JSONB)) AS row_data
WHERE r.report_kind = 'over_time';

COMMENT ON VIEW analytics.ga_pageviews IS
    'Per-(property, date) GA pageviews timeseries. Sourced from over_time runReport '
    '(dimensions=[date], metrics=[screenPageViews, totalUsers, sessions, averageSessionDuration]). '
    'Use core_project_number to roll up by CFDE project.';

COMMENT ON COLUMN analytics.ga_pageviews.event_date IS
    'Calendar date the metrics are for (UTC-adjusted by GA).';

COMMENT ON COLUMN analytics.ga_pageviews.page_views IS 'screenPageViews on that date.';
COMMENT ON COLUMN analytics.ga_pageviews.total_users IS 'Distinct GA users on that date.';
COMMENT ON COLUMN analytics.ga_pageviews.sessions IS 'GA sessions on that date.';
COMMENT ON COLUMN analytics.ga_pageviews.avg_session_seconds IS
    'Mean session duration in seconds (GA averageSessionDuration).';


CREATE OR REPLACE VIEW analytics.ga_top_pages AS
SELECT
    p.property_id,
    p.core_project_number,
    row_data -> 'dimensionValues' -> 0 ->> 'value'              AS page_path,
    row_data -> 'dimensionValues' -> 1 ->> 'value'              AS page_title,
    (row_data -> 'metricValues' -> 0 ->> 'value')::INTEGER      AS page_views,
    (row_data -> 'metricValues' -> 1 ->> 'value')::INTEGER      AS total_users,
    (row_data -> 'metricValues' -> 2 ->> 'value')::NUMERIC      AS avg_session_seconds,
    r.fetched_at                                                AS data_refreshed_at
FROM raw.ga_reports r
JOIN raw.ga_properties p USING (property_id)
CROSS JOIN LATERAL jsonb_array_elements(COALESCE(r.source -> 'rows', '[]'::JSONB)) AS row_data
WHERE r.report_kind = 'top_pages';

COMMENT ON VIEW analytics.ga_top_pages IS
    'Per-page pageview rollup. From top_pages runReport (dimensions=[pagePath, pageTitle], '
    'metrics=[screenPageViews, totalUsers, averageSessionDuration]). page_path is relative '
    'to property hostname; join raw.ga_properties.hostname for absolute URLs.';

COMMENT ON COLUMN analytics.ga_top_pages.page_path IS
    'Pathname relative to the GA property hostname. Combine with raw.ga_properties.hostname for the absolute URL.';


CREATE OR REPLACE VIEW analytics.ga_geo AS
SELECT
    p.property_id,
    p.core_project_number,
    CASE r.report_kind
        WHEN 'top_continents' THEN 'continent'
        WHEN 'top_countries'  THEN 'country'
        WHEN 'top_regions'    THEN 'region'
        WHEN 'top_cities'     THEN 'city'
    END                                                      AS geo_level,
    row_data -> 'dimensionValues' -> 0 ->> 'value'           AS geo_name,
    (row_data -> 'metricValues' -> 0 ->> 'value')::INTEGER   AS total_users,
    r.fetched_at                                             AS data_refreshed_at
FROM raw.ga_reports r
JOIN raw.ga_properties p USING (property_id)
CROSS JOIN LATERAL jsonb_array_elements(COALESCE(r.source -> 'rows', '[]'::JSONB)) AS row_data
WHERE r.report_kind IN ('top_continents','top_countries','top_regions','top_cities');

COMMENT ON VIEW analytics.ga_geo IS
    'Geographic rollups: continent/country/region/city distinct totalUsers per property. '
    'geo_level discriminates which dimension the row is for.';


CREATE OR REPLACE VIEW analytics.ga_traffic_sources AS
SELECT
    p.property_id,
    p.core_project_number,
    row_data -> 'dimensionValues' -> 0 ->> 'value' AS default_channel_group,
    row_data -> 'dimensionValues' -> 1 ->> 'value' AS source,
    row_data -> 'dimensionValues' -> 2 ->> 'value' AS medium,
    (row_data -> 'metricValues' -> 0 ->> 'value')::INTEGER AS sessions,
    (row_data -> 'metricValues' -> 1 ->> 'value')::INTEGER AS total_users,
    r.fetched_at AS data_refreshed_at
FROM raw.ga_reports r
JOIN raw.ga_properties p USING (property_id)
CROSS JOIN LATERAL jsonb_array_elements(COALESCE(r.source -> 'rows', '[]'::JSONB)) AS row_data
WHERE r.report_kind = 'traffic_sources';

COMMENT ON VIEW analytics.ga_traffic_sources IS
    'Sessions and users grouped by GA default channel group / source / medium. '
    'Use to answer "where is traffic to DCC X coming from?"';
