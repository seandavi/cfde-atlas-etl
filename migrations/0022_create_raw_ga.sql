-- 0022 — Raw layer for Google Analytics.
--
-- raw.ga_properties: the curated property -> core_project_number crosswalk
-- (loaded from raw/manual-ga-properties.yaml). Driving the flow off this list
-- handles the upstream-dependency: we only fetch from DCC properties that
-- have granted our service account viewer access.
--
-- raw.ga_reports: one row per (property, report_kind, period_start, period_end)
-- with the raw runReport response as jsonb. Per-report parsers live in views.

CREATE TABLE IF NOT EXISTS raw.ga_properties (
    property_id         TEXT        NOT NULL PRIMARY KEY,
    display_name        TEXT,
    hostname            TEXT,
    core_project_number TEXT,
    dcc                 TEXT,
    granted_at          DATE,
    source              JSONB       NOT NULL,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS raw_ga_properties_core_project_idx
    ON raw.ga_properties (core_project_number);

COMMENT ON TABLE raw.ga_properties IS
    'GA4 properties this ETL has access to, with the CFDE core_project_number crosswalk. '
    'Loaded from raw/manual-ga-properties.yaml because GA access is granted per-DCC by '
    'teams we cannot direct. property_id is the GA4 numeric property id.';

COMMENT ON COLUMN raw.ga_properties.property_id IS 'GA4 numeric property id. PK.';
COMMENT ON COLUMN raw.ga_properties.hostname IS 'Primary hostname for the property; helps disambiguate pagePath data.';
COMMENT ON COLUMN raw.ga_properties.core_project_number IS
    'NIH core project number this property is funded under. FK to analytics.core_projects.core_project_number.';
COMMENT ON COLUMN raw.ga_properties.granted_at IS
    'When the DCC granted our service account Viewer access. Helps reason about earliest reliable date.';


CREATE TABLE IF NOT EXISTS raw.ga_reports (
    property_id   TEXT        NOT NULL,
    report_kind   TEXT        NOT NULL,
    period_start  DATE        NOT NULL,
    period_end    DATE        NOT NULL,
    source        JSONB       NOT NULL,
    fetched_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (property_id, report_kind, period_start, period_end)
);

CREATE INDEX IF NOT EXISTS raw_ga_reports_kind_idx ON raw.ga_reports (report_kind);

COMMENT ON TABLE raw.ga_reports IS
    'GA4 Data API runReport responses landed as-is. One row per '
    '(property_id, report_kind, period_start, period_end). report_kind values: '
    'over_time, top_pages, top_countries, top_regions, top_cities, top_continents, '
    'top_languages, top_devices, top_oses, traffic_sources, top_referrers, '
    'top_search_terms, events_by_name.';

COMMENT ON COLUMN raw.ga_reports.report_kind IS
    'String label identifying which report variant this row holds (see table comment for the enum).';
