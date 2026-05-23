-- 0024 — Raw layer for the project-side details of downstream citing grants.
--
-- raw.reporter_citing_publications (#13) gave us (citing_pmid, downstream_core_project_number)
-- using RePORTER's publications endpoint. The publication record there does NOT carry the
-- grant-side details (PI, institution, mechanism, award amount, dates). This table fetches
-- those via RePORTER /v2/projects/search keyed on core_project_number.
--
-- Logically distinct from raw.reporter_projects (which is the CFDE cohort) so the
-- CFDE set stays a clean primary set.

CREATE TABLE IF NOT EXISTS raw.reporter_citing_projects (
    project_num         TEXT        NOT NULL PRIMARY KEY,
    core_project_number TEXT,
    source              JSONB       NOT NULL,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS raw_reporter_citing_projects_core_project_idx
    ON raw.reporter_citing_projects (core_project_number);

CREATE INDEX IF NOT EXISTS raw_reporter_citing_projects_activity_code_idx
    ON raw.reporter_citing_projects ((source ->> 'activity_code'));

COMMENT ON TABLE raw.reporter_citing_projects IS
    'NIH RePORTER project records for downstream grants that fund publications citing CFDE work. '
    'NOT a CFDE cohort. Use analytics.citing_grant_details and the citing-funding rollup views.';

COMMENT ON COLUMN raw.reporter_citing_projects.project_num IS
    'RePORTER project_num. PK.';

COMMENT ON COLUMN raw.reporter_citing_projects.core_project_number IS
    'RePORTER core_project_num of the downstream grant. Maps back to '
    'raw.reporter_citing_publications.core_project_number.';

COMMENT ON COLUMN raw.reporter_citing_projects.source IS
    'Full RePORTER project record (project_title, organization, principal_investigators, '
    'activity_code, agency_code, award_amount, project_start_date, project_end_date, ...).';
