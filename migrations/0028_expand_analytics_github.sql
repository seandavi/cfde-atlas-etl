-- 0028 — Expand analytics.github_repos + add analytics.github_readmes / github_citations.
--
-- Drives chat queries like:
--   "Which CFDE repos have a CITATION.cff with a linked publication?"
--   "Which repos haven't pushed in over a year?"
--   "Show me Python repos under U54OD036472 with full sustainability docs."

DROP VIEW IF EXISTS analytics.github_repos;

CREATE OR REPLACE VIEW analytics.github_repos AS
WITH issue_counts AS (
    SELECT repo_id,
           COUNT(*) FILTER (WHERE NOT is_pull_request AND state = 'open')   AS open_issues,
           COUNT(*) FILTER (WHERE NOT is_pull_request AND state = 'closed') AS closed_issues,
           COUNT(*) FILTER (WHERE is_pull_request AND state = 'open')       AS open_pull_requests,
           COUNT(*) FILTER (WHERE is_pull_request AND state = 'closed')     AS closed_pull_requests
    FROM raw.github_issues
    GROUP BY repo_id
),
star_counts AS (SELECT repo_id, COUNT(*) AS stars FROM raw.github_stars GROUP BY repo_id),
fork_counts AS (
    SELECT parent_repo_id AS repo_id, COUNT(*) AS forks FROM raw.github_forks GROUP BY parent_repo_id
),
commit_counts AS (
    SELECT repo_id, COUNT(*) AS commits, MAX(committed_at) AS last_commit_at
    FROM raw.github_commits GROUP BY repo_id
),
language_top AS (
    SELECT DISTINCT ON (repo_id) repo_id, language AS primary_language
    FROM raw.github_languages ORDER BY repo_id, bytes DESC
),
core_project_links AS (
    SELECT repo_id, ARRAY_AGG(DISTINCT core_project_number ORDER BY core_project_number) AS core_project_numbers
    FROM raw.github_repo_core_projects GROUP BY repo_id
)
SELECT
    r.repo_id,
    r.full_name,
    r.source -> 'owner' ->> 'login'                          AS owner_login,
    r.source ->> 'name'                                      AS name,
    r.source ->> 'description'                               AS description,
    r.source ->> 'homepage'                                  AS homepage,
    r.source ->> 'default_branch'                            AS default_branch,
    NULLIF(r.source ->> 'created_at', '')::TIMESTAMPTZ       AS created_at,
    NULLIF(r.source ->> 'pushed_at',  '')::TIMESTAMPTZ       AS last_push_at,
    (
        EXTRACT(EPOCH FROM (NOW() - NULLIF(r.source ->> 'pushed_at', '')::TIMESTAMPTZ)) / 86400
    )::INTEGER                                               AS days_since_last_push,
    COALESCE(sc.stars, 0)                                    AS stars,
    COALESCE(fc.forks, 0)                                    AS forks,
    NULLIF(r.source ->> 'subscribers_count', '')::INTEGER    AS watchers,
    COALESCE(cc.commits, 0)                                  AS commits,
    cc.last_commit_at,
    COALESCE(ic.open_issues, 0)                              AS open_issues,
    COALESCE(ic.closed_issues, 0)                            AS closed_issues,
    COALESCE(ic.open_pull_requests, 0)                       AS open_pull_requests,
    COALESCE(ic.closed_pull_requests, 0)                     AS closed_pull_requests,
    lt.primary_language,
    r.source -> 'license' ->> 'name'                         AS license_name,
    r.source -> 'license' ->> 'spdx_id'                      AS license_spdx,
    ARRAY(SELECT jsonb_array_elements_text(COALESCE(r.source -> 'topics', '[]'::JSONB)))
                                                             AS topics,
    NULLIF(r.source ->> 'size', '')::INTEGER                 AS size_kb,
    (r.source ->> 'archived')::BOOLEAN                       AS archived,
    (r.source ->> 'is_template')::BOOLEAN                    AS is_template,
    (r.features ->> 'has_readme')::BOOLEAN                   AS has_readme,
    (r.features ->> 'has_security')::BOOLEAN                 AS has_security,
    (r.features ->> 'has_contributing')::BOOLEAN             AS has_contributing,
    (r.features ->> 'has_coc')::BOOLEAN                      AS has_code_of_conduct,
    (r.features ->> 'has_citation')::BOOLEAN                 AS has_citation,
    (r.features ->> 'has_funding')::BOOLEAN                  AS has_funding,
    COALESCE((r.features ->> 'workflow_files')::INTEGER, 0)  AS workflow_files,
    cpl.core_project_numbers,
    r.fetched_at                                             AS data_refreshed_at
FROM raw.github_repos r
LEFT JOIN issue_counts ic    ON ic.repo_id = r.repo_id
LEFT JOIN star_counts sc     ON sc.repo_id = r.repo_id
LEFT JOIN fork_counts fc     ON fc.repo_id = r.repo_id
LEFT JOIN commit_counts cc   ON cc.repo_id = r.repo_id
LEFT JOIN language_top lt    ON lt.repo_id = r.repo_id
LEFT JOIN core_project_links cpl ON cpl.repo_id = r.repo_id;

COMMENT ON VIEW analytics.github_repos IS
    'Per-GitHub-repo summary. One row per repo_id. core_project_numbers is a TEXT[] — '
    'filter with WHERE ''U54OD036472'' = ANY (core_project_numbers). '
    'Sustainability flags (has_readme/security/contributing/coc/citation/funding) come '
    'from GitHub /community/profile; NULL means "not yet checked". '
    'days_since_last_push and license_spdx are derived from the base repo response.';

COMMENT ON COLUMN analytics.github_repos.repo_id IS 'GitHub repo id. PK.';
COMMENT ON COLUMN analytics.github_repos.full_name IS '"owner/name" identifier.';
COMMENT ON COLUMN analytics.github_repos.homepage IS 'Project website URL declared in the GitHub repo settings; may be NULL.';
COMMENT ON COLUMN analytics.github_repos.last_push_at IS 'Timestamp of the most recent push to any branch.';
COMMENT ON COLUMN analytics.github_repos.days_since_last_push IS
    'Days between NOW() and last_push_at. > 365 indicates a stale / unmaintained repo.';
COMMENT ON COLUMN analytics.github_repos.stars IS 'Star count derived from raw.github_stars rows.';
COMMENT ON COLUMN analytics.github_repos.forks IS 'Fork count derived from raw.github_forks rows.';
COMMENT ON COLUMN analytics.github_repos.commits IS 'Tracked commit count (raw.github_commits).';
COMMENT ON COLUMN analytics.github_repos.last_commit_at IS 'Most recent committed_at timestamp.';
COMMENT ON COLUMN analytics.github_repos.primary_language IS
    'Language with the most bytes in raw.github_languages. NULL when no languages reported.';
COMMENT ON COLUMN analytics.github_repos.license_name IS
    'Human-readable license name from GitHub (e.g. "MIT License").';
COMMENT ON COLUMN analytics.github_repos.license_spdx IS
    'SPDX short identifier (e.g. "MIT", "Apache-2.0", "NOASSERTION"). NULL when GitHub could not detect a license.';
COMMENT ON COLUMN analytics.github_repos.topics IS
    'Lowercase GitHub topic tags as a TEXT[]. Use WHERE ''cfde'' = ANY (topics) to filter.';
COMMENT ON COLUMN analytics.github_repos.size_kb IS 'Repo size in KB per GitHub. Includes the .git directory.';
COMMENT ON COLUMN analytics.github_repos.archived IS 'TRUE if the repo is archived (read-only on GitHub).';
COMMENT ON COLUMN analytics.github_repos.is_template IS 'TRUE if the repo is a template, intended to be cloned as a starting point.';
COMMENT ON COLUMN analytics.github_repos.has_readme IS
    'TRUE if /community/profile reported a README file. NULL = not yet checked.';
COMMENT ON COLUMN analytics.github_repos.has_security IS
    'TRUE if SECURITY.md is present. Sustainability signal for security disclosure policy. NULL = not yet checked.';
COMMENT ON COLUMN analytics.github_repos.has_contributing IS
    'TRUE if CONTRIBUTING.md is present. Sustainability signal for contributor onboarding. NULL = not yet checked.';
COMMENT ON COLUMN analytics.github_repos.has_code_of_conduct IS
    'TRUE if CODE_OF_CONDUCT.md is present. Sustainability signal for community norms. NULL = not yet checked.';
COMMENT ON COLUMN analytics.github_repos.has_citation IS
    'TRUE if CITATION.cff is present. Join analytics.github_citations for parsed contents.';
COMMENT ON COLUMN analytics.github_repos.has_funding IS
    'TRUE if .github/FUNDING.yml is present.';
COMMENT ON COLUMN analytics.github_repos.workflow_files IS
    'Count of files in .github/workflows/. Proxy for CI maturity.';
COMMENT ON COLUMN analytics.github_repos.core_project_numbers IS
    'Array of CFDE core_project_numbers this repo was discovered under. '
    'Filter: WHERE ''U54OD036472'' = ANY (core_project_numbers).';


CREATE OR REPLACE VIEW analytics.github_readmes AS
SELECT
    repo_id,
    path             AS readme_path,
    sha              AS readme_sha,
    LENGTH(content)  AS content_length,
    truncated,
    content,
    fetched_at       AS data_refreshed_at
FROM raw.github_readmes;

COMMENT ON VIEW analytics.github_readmes IS
    'Decoded README text per GitHub repo (one row per repo_id). '
    'Join to analytics.github_repos on repo_id. content is UTF-8 plain text, truncated to 256 KB.';

COMMENT ON COLUMN analytics.github_readmes.repo_id IS 'GitHub repo id. PK. FK to analytics.github_repos.repo_id.';
COMMENT ON COLUMN analytics.github_readmes.readme_path IS 'README file path within the repo.';
COMMENT ON COLUMN analytics.github_readmes.content_length IS 'Character count of the stored content (post-truncation).';
COMMENT ON COLUMN analytics.github_readmes.truncated IS 'TRUE if original README was longer than 256 KB and only a prefix was stored.';
COMMENT ON COLUMN analytics.github_readmes.content IS 'Plain text README content; suitable for full-text search or LLM summarization.';


CREATE OR REPLACE VIEW analytics.github_citations AS
SELECT
    c.repo_id,
    r.full_name,
    c.doi,
    c.pmid,
    c.source ->> 'title'                                  AS software_title,
    c.source ->> 'version'                                AS software_version,
    NULLIF(c.source ->> 'date-released', '')::DATE        AS date_released,
    c.source -> 'preferred-citation' ->> 'title'          AS preferred_citation_title,
    c.source -> 'preferred-citation' ->> 'journal'        AS preferred_citation_journal,
    NULLIF(c.source -> 'preferred-citation' ->> 'year', '')::INTEGER
                                                          AS preferred_citation_year,
    c.fetched_at                                          AS data_refreshed_at
FROM raw.github_citations c
LEFT JOIN raw.github_repos r ON r.repo_id = c.repo_id;

COMMENT ON VIEW analytics.github_citations IS
    'CITATION.cff contents for repos that publish one. doi/pmid are the direct '
    'crosswalk to analytics.publications: WHERE doi IS NOT NULL → join on doi; '
    'WHERE pmid IS NOT NULL → join on pmid. Surfaces software ↔ paper relationship.';

COMMENT ON COLUMN analytics.github_citations.repo_id IS 'GitHub repo id. PK. FK to analytics.github_repos.repo_id.';
COMMENT ON COLUMN analytics.github_citations.doi IS
    'DOI of the canonical paper for this software, if declared in CITATION.cff. '
    'Join to analytics.publications.doi.';
COMMENT ON COLUMN analytics.github_citations.pmid IS
    'PubMed ID of the canonical paper for this software, if declared in CITATION.cff. '
    'Join to analytics.publications.pmid.';
COMMENT ON COLUMN analytics.github_citations.software_title IS 'CITATION.cff "title" field — the software project name.';
COMMENT ON COLUMN analytics.github_citations.software_version IS 'CITATION.cff "version" field.';
COMMENT ON COLUMN analytics.github_citations.preferred_citation_title IS
    'Title of the paper users should cite (CITATION.cff preferred-citation.title).';
