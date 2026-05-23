-- 0005 — Raw layer for NIH RePORTER projects.
--
-- One row per project_num (the most-granular grant ID). core_project_num
-- groups projects within the same award (e.g. parent + supplements).

CREATE TABLE IF NOT EXISTS raw.reporter_projects (
    project_num         TEXT        NOT NULL PRIMARY KEY,
    core_project_number TEXT,
    source              JSONB       NOT NULL,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS raw_reporter_projects_core_project_idx
    ON raw.reporter_projects (core_project_number);

CREATE INDEX IF NOT EXISTS raw_reporter_projects_opportunity_idx
    ON raw.reporter_projects ((source ->> 'opportunity_number'));

COMMENT ON TABLE raw.reporter_projects IS
    'NIH RePORTER projects fetched from /v2/projects/search. '
    'One row per project_num; multiple projects share a core_project_number.';

COMMENT ON COLUMN raw.reporter_projects.project_num IS
    'RePORTER project_num — the per-fiscal-year, per-mechanism grant identifier.';

COMMENT ON COLUMN raw.reporter_projects.core_project_number IS
    'RePORTER core_project_num. Stable across years/supplements. Primary navigation key.';

COMMENT ON COLUMN raw.reporter_projects.source IS
    'Full RePORTER project record as returned by /v2/projects/search.';

COMMENT ON COLUMN raw.reporter_projects.fetched_at IS
    'When this row was last written by the ETL.';
