-- 0025 — Analytics views for downstream citing-grant details + funding rollups.
--
-- Builds on raw.reporter_citing_projects (#35). Surfaces PI, institution, mechanism,
-- and award amount alongside the existing (cfde_pmid, citing_pmid, downstream_core_project_number)
-- triples; provides per-CFDE-core-project and per-institution and per-mechanism
-- funding rollups for chat-friendly impact questions.

CREATE OR REPLACE VIEW analytics.citing_grant_details AS
SELECT
    core_project_number                                            AS downstream_core_project_number,
    project_num                                                    AS downstream_project_num,
    source ->> 'project_title'                                     AS project_title,
    source ->> 'agency_code'                                       AS agency_code,
    source ->> 'activity_code'                                     AS activity_code,
    source -> 'organization' ->> 'org_name'                        AS organization_name,
    source -> 'organization' ->> 'org_state'                       AS organization_state,
    NULLIF(source ->> 'award_amount', '')::NUMERIC                 AS award_amount,
    NULLIF(source ->> 'project_start_date', '')::DATE              AS project_start_date,
    NULLIF(source ->> 'project_end_date',   '')::DATE              AS project_end_date,
    (source ->> 'is_active')::BOOLEAN                              AS is_active,
    (
        SELECT STRING_AGG(
            COALESCE(pi ->> 'full_name', NULLIF(CONCAT_WS(' ', pi ->> 'first_name', pi ->> 'last_name'), '')),
            '; ' ORDER BY pi ->> 'last_name'
        )
        FROM jsonb_array_elements(COALESCE(source -> 'principal_investigators', '[]'::JSONB)) AS pi
    )                                                              AS principal_investigators,
    fetched_at                                                     AS data_refreshed_at
FROM raw.reporter_citing_projects;

COMMENT ON VIEW analytics.citing_grant_details IS
    'Per-(downstream project_num) detail for grants that fund publications citing CFDE work. '
    'Use to surface PI, institution, mechanism, and award amount alongside the (cfde_pmid, citing_pmid, '
    'downstream_core_project_number) edges in analytics.citing_grants. NOT a CFDE-funded set.';

COMMENT ON COLUMN analytics.citing_grant_details.downstream_core_project_number IS
    'NIH core project number for a downstream grant acknowledged by a paper citing CFDE work. '
    'Join key to analytics.citing_grants.downstream_core_project_number.';

COMMENT ON COLUMN analytics.citing_grant_details.award_amount IS
    'USD award amount for this project_num (one fiscal year + supplements aggregate '
    'within core_project_number).';

COMMENT ON COLUMN analytics.citing_grant_details.principal_investigators IS
    'Semicolon-separated PI list for the downstream grant.';

COMMENT ON COLUMN analytics.citing_grant_details.organization_state IS
    'US state of the grantee institution where RePORTER provides it.';


-- Extended view that joins citing_grants edges to the new grant-side details.
CREATE OR REPLACE VIEW analytics.citing_grants_full AS
SELECT
    cg.cfde_pmid,
    cg.citing_pmid,
    cg.downstream_core_project_number,
    cgd.project_title                                              AS downstream_project_title,
    cgd.principal_investigators                                    AS downstream_principal_investigators,
    cgd.organization_name                                          AS downstream_organization,
    cgd.organization_state                                         AS downstream_organization_state,
    cgd.activity_code                                              AS downstream_activity_code,
    cgd.agency_code                                                AS downstream_agency_code,
    cgd.award_amount                                               AS downstream_award_amount,
    cgd.project_start_date                                         AS downstream_project_start_date,
    cgd.project_end_date                                           AS downstream_project_end_date,
    GREATEST(cg.data_refreshed_at, COALESCE(cgd.data_refreshed_at, cg.data_refreshed_at))
                                                                   AS data_refreshed_at
FROM analytics.citing_grants cg
LEFT JOIN analytics.citing_grant_details cgd
    ON cgd.downstream_core_project_number = cg.downstream_core_project_number;

COMMENT ON VIEW analytics.citing_grants_full IS
    'Forward citations expanded to include downstream grant-side details (PI, institution, '
    'mechanism, award amount). One row per (cfde_pmid, citing_pmid, downstream_core_project_number).';


CREATE OR REPLACE VIEW analytics.citing_funding_by_cfde_core AS
SELECT
    rp.core_project_number                                         AS cfde_core_project_number,
    COUNT(DISTINCT cgf.downstream_core_project_number)             AS downstream_grants,
    COUNT(DISTINCT cgf.downstream_organization)                    AS downstream_organizations,
    COUNT(DISTINCT cgf.downstream_principal_investigators)         AS downstream_pi_strings,
    SUM(COALESCE(cgf.downstream_award_amount, 0))                  AS downstream_award_amount_total,
    MAX(cgf.data_refreshed_at)                                     AS data_refreshed_at
FROM analytics.citing_grants_full cgf
JOIN raw.reporter_publications rp ON rp.pmid = cgf.cfde_pmid
GROUP BY rp.core_project_number;

COMMENT ON VIEW analytics.citing_funding_by_cfde_core IS
    'Per CFDE core_project_number: counts of distinct downstream grants, institutions, PI strings, '
    'and a SUM of downstream award_amount (note: this sums per-fiscal-year project_nums and will '
    'overcount within a core; treat as an order-of-magnitude indicator, not a precise dollar total).';

COMMENT ON COLUMN analytics.citing_funding_by_cfde_core.downstream_award_amount_total IS
    'Sum of award_amount across downstream project_nums acknowledged by papers citing this CFDE '
    'core project. Order-of-magnitude indicator only — RePORTER project_nums repeat per fiscal year.';


CREATE OR REPLACE VIEW analytics.citing_funding_by_institution AS
SELECT
    cgd.organization_name,
    cgd.organization_state,
    COUNT(DISTINCT cgd.downstream_core_project_number)             AS distinct_downstream_grants,
    SUM(COALESCE(cgd.award_amount, 0))                             AS total_award_amount,
    MAX(cgd.data_refreshed_at)                                     AS data_refreshed_at
FROM analytics.citing_grant_details cgd
WHERE cgd.organization_name IS NOT NULL
GROUP BY cgd.organization_name, cgd.organization_state;

COMMENT ON VIEW analytics.citing_funding_by_institution IS
    'Per downstream institution: count of citing grants + total award amount. Use to rank '
    'institutions whose work cites CFDE-funded outputs.';


CREATE OR REPLACE VIEW analytics.citing_funding_by_mechanism AS
SELECT
    cgd.activity_code,
    COUNT(DISTINCT cgd.downstream_core_project_number)             AS distinct_downstream_grants,
    SUM(COALESCE(cgd.award_amount, 0))                             AS total_award_amount,
    MAX(cgd.data_refreshed_at)                                     AS data_refreshed_at
FROM analytics.citing_grant_details cgd
WHERE cgd.activity_code IS NOT NULL
GROUP BY cgd.activity_code;

COMMENT ON VIEW analytics.citing_funding_by_mechanism IS
    'Per NIH activity code (U54, R01, ...) among downstream citing grants. Use to see whether '
    'CFDE outputs feed primarily small-grant work, large U-mechanism centers, or other.';
