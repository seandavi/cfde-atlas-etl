-- 0006 — Analytics views for projects and core projects.
--
-- This is the contract cfde-atlas reads. Column names + types + COMMENTs
-- drive the output of cfde-atlas's describe_table tool.

CREATE OR REPLACE VIEW analytics.projects AS
SELECT
    project_num,
    core_project_number,
    source ->> 'project_title'                          AS project_title,
    NULLIF(source ->> 'appl_id', '')::INTEGER           AS application_id,
    NULLIF(source ->> 'award_amount', '')::NUMERIC      AS award_amount,
    source ->> 'activity_code'                          AS activity_code,
    source ->> 'agency_code'                            AS agency_code,
    source ->> 'opportunity_number'                     AS opportunity_number,
    NULLIF(source ->> 'project_start_date', '')::DATE   AS project_start_date,
    NULLIF(source ->> 'project_end_date', '')::DATE     AS project_end_date,
    (source ->> 'is_active')::BOOLEAN                   AS is_active,
    source -> 'organization' ->> 'org_name'             AS organization_name,
    fetched_at                                          AS data_refreshed_at
FROM raw.reporter_projects;

COMMENT ON VIEW analytics.projects IS
    'One row per NIH RePORTER project_num. Multiple project_nums roll up into one '
    'core_project_number (see analytics.core_projects). Join key for publications, '
    'github_repos, and ga_pageviews is core_project_number.';

COMMENT ON COLUMN analytics.projects.project_num IS
    'RePORTER project_num. The per-fiscal-year, per-mechanism grant identifier. Primary key.';

COMMENT ON COLUMN analytics.projects.core_project_number IS
    'NIH core project number, e.g. U54OD036472. Stable across years/supplements. '
    'The primary navigation key joining publications, grants, repos, and pageviews.';

COMMENT ON COLUMN analytics.projects.application_id IS
    'RePORTER appl_id. Unique per submitted application; useful for deduping submissions.';

COMMENT ON COLUMN analytics.projects.award_amount IS
    'Total award amount in USD for this project_num''s fiscal year.';

COMMENT ON COLUMN analytics.projects.activity_code IS
    'NIH activity code (U54, U24, R03, ...). See NIH Activity Code Search for definitions.';

COMMENT ON COLUMN analytics.projects.opportunity_number IS
    'FOA the project was awarded under. FK to analytics.opportunities.opportunity_number.';

COMMENT ON COLUMN analytics.projects.is_active IS
    'TRUE if project_end_date is in the future at fetch time.';

COMMENT ON COLUMN analytics.projects.data_refreshed_at IS
    'Timestamp of the most recent ETL load for this row.';


CREATE OR REPLACE VIEW analytics.core_projects AS
SELECT
    core_project_number,
    -- Pick a representative title (any project under this core_project_number)
    (ARRAY_AGG(source ->> 'project_title') FILTER (WHERE source ->> 'project_title' IS NOT NULL))[1]
        AS core_project_title,
    (ARRAY_AGG(source ->> 'activity_code') FILTER (WHERE source ->> 'activity_code' IS NOT NULL))[1]
        AS activity_code,
    COUNT(*)::INTEGER                                                AS project_count,
    ARRAY_AGG(DISTINCT project_num ORDER BY project_num)             AS project_nums,
    SUM(COALESCE(NULLIF(source ->> 'award_amount', '')::NUMERIC, 0)) AS total_award_amount,
    MAX(fetched_at)                                                  AS data_refreshed_at
FROM raw.reporter_projects
WHERE core_project_number IS NOT NULL
GROUP BY core_project_number;

COMMENT ON VIEW analytics.core_projects IS
    'One row per NIH core_project_number, rolled up from analytics.projects. '
    'Total award amount sums all project_nums (fiscal years + supplements) under the core.';

COMMENT ON COLUMN analytics.core_projects.core_project_number IS
    'NIH core project number, e.g. U54OD036472. Primary key.';

COMMENT ON COLUMN analytics.core_projects.core_project_title IS
    'Representative project title (first non-null title across this core_project_number).';

COMMENT ON COLUMN analytics.core_projects.activity_code IS
    'NIH activity code (U54, U24, ...) for the core project.';

COMMENT ON COLUMN analytics.core_projects.project_count IS
    'Number of project_nums (fiscal years + supplements) rolled up into this core.';

COMMENT ON COLUMN analytics.core_projects.total_award_amount IS
    'Sum of award_amount across all project_nums under this core_project_number, in USD.';

COMMENT ON COLUMN analytics.core_projects.data_refreshed_at IS
    'Timestamp of the most recent ETL load (max across rolled-up projects).';
