-- 0019 — Analytics views for downstream grants supporting citing publications.
--
-- analytics.citing_grants is the joinable view; analytics.citing_grants_rollup
-- pre-aggregates by CFDE core project for chat-friendly answers.

CREATE OR REPLACE VIEW analytics.citing_grants AS
SELECT
    c.cfde_pmid,
    c.citing_pmid,
    rcp.core_project_number                              AS downstream_core_project_number,
    rcp.source ->> 'agency_code'                         AS downstream_agency_code,
    rcp.source ->> 'activity_code'                       AS downstream_activity_code,
    rcp.source -> 'organization' ->> 'org_name'          AS downstream_organization,
    rcp.fetched_at                                       AS data_refreshed_at
FROM raw.icite_citations c
JOIN raw.reporter_citing_publications rcp ON rcp.citing_pmid = c.citing_pmid;

COMMENT ON VIEW analytics.citing_grants IS
    'For each CFDE pmid that gets cited, the downstream NIH grants the citing '
    'paper acknowledges. One row per (cfde_pmid, citing_pmid, downstream_core_project_number). '
    'Use to answer "what NIH-funded work builds on CFDE outputs?"';

COMMENT ON COLUMN analytics.citing_grants.cfde_pmid IS
    'CFDE-funded pmid being cited. FK to analytics.publications.pmid.';

COMMENT ON COLUMN analytics.citing_grants.citing_pmid IS
    'Citing pmid. FK to analytics.citing_publications.citing_pmid.';

COMMENT ON COLUMN analytics.citing_grants.downstream_core_project_number IS
    'NIH core project number the citing paper acknowledges. NOT a CFDE core project — '
    'this is downstream-funded work.';

COMMENT ON COLUMN analytics.citing_grants.downstream_organization IS
    'Institution that holds the downstream grant.';


CREATE OR REPLACE VIEW analytics.citing_grants_rollup AS
SELECT
    p.core_project_number                                  AS cfde_core_project_number,
    COUNT(DISTINCT cg.citing_pmid)                         AS citing_publications,
    COUNT(DISTINCT cg.downstream_core_project_number)      AS downstream_grants,
    COUNT(DISTINCT cg.downstream_organization)             AS downstream_organizations,
    MAX(cg.data_refreshed_at)                              AS data_refreshed_at
FROM analytics.citing_grants cg
JOIN raw.reporter_publications p ON p.pmid = cg.cfde_pmid
GROUP BY p.core_project_number;

COMMENT ON VIEW analytics.citing_grants_rollup IS
    'Per CFDE core project, counts of citing publications, distinct downstream '
    'NIH core_project_numbers, and distinct downstream institutions. Chat-friendly '
    'aggregate for "top CFDE projects by downstream impact."';

COMMENT ON COLUMN analytics.citing_grants_rollup.cfde_core_project_number IS
    'CFDE core project number. FK to analytics.core_projects.core_project_number.';

COMMENT ON COLUMN analytics.citing_grants_rollup.citing_publications IS
    'Distinct pmids that cite at least one CFDE pub under this CFDE core project.';

COMMENT ON COLUMN analytics.citing_grants_rollup.downstream_grants IS
    'Distinct downstream NIH core_project_numbers acknowledged by citing papers.';
