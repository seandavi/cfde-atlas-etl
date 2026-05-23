-- 0021 — Analytics views for GitHub activity.
--
-- Three views:
--   - analytics.github_repos: per-repo summary with rollups + link to CFDE core projects
--   - analytics.github_activity_weekly: per-(repo, week) commit/issue/PR/star counts
--   - analytics.github_contributors: per-(repo, contributor) with contribution count
--
-- All LLM-facing comments emphasize units, value ranges, and join hints.

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
star_counts AS (
    SELECT repo_id, COUNT(*) AS stars FROM raw.github_stars GROUP BY repo_id
),
fork_counts AS (
    SELECT parent_repo_id AS repo_id, COUNT(*) AS forks
    FROM raw.github_forks GROUP BY parent_repo_id
),
commit_counts AS (
    SELECT repo_id,
           COUNT(*) AS commits,
           MAX(committed_at) AS last_commit_at
    FROM raw.github_commits
    GROUP BY repo_id
),
language_top AS (
    SELECT DISTINCT ON (repo_id) repo_id, language AS primary_language
    FROM raw.github_languages
    ORDER BY repo_id, bytes DESC
),
core_project_links AS (
    SELECT repo_id, ARRAY_AGG(DISTINCT core_project_number ORDER BY core_project_number) AS core_project_numbers
    FROM raw.github_repo_core_projects
    GROUP BY repo_id
)
SELECT
    r.repo_id,
    r.full_name,
    r.source -> 'owner' ->> 'login'                    AS owner_login,
    r.source ->> 'name'                                AS name,
    r.source ->> 'description'                         AS description,
    r.source ->> 'default_branch'                      AS default_branch,
    NULLIF(r.source ->> 'created_at', '')::TIMESTAMPTZ AS created_at,
    NULLIF(r.source ->> 'pushed_at',  '')::TIMESTAMPTZ AS last_push_at,
    COALESCE(sc.stars, 0)                              AS stars,
    COALESCE(fc.forks, 0)                              AS forks,
    NULLIF(r.source ->> 'subscribers_count', '')::INTEGER AS watchers,
    COALESCE(cc.commits, 0)                            AS commits,
    cc.last_commit_at,
    COALESCE(ic.open_issues, 0)                        AS open_issues,
    COALESCE(ic.closed_issues, 0)                      AS closed_issues,
    COALESCE(ic.open_pull_requests, 0)                 AS open_pull_requests,
    COALESCE(ic.closed_pull_requests, 0)               AS closed_pull_requests,
    lt.primary_language,
    r.source -> 'license' ->> 'name'                   AS license,
    cpl.core_project_numbers,
    r.fetched_at                                       AS data_refreshed_at
FROM raw.github_repos r
LEFT JOIN issue_counts ic    ON ic.repo_id = r.repo_id
LEFT JOIN star_counts sc     ON sc.repo_id = r.repo_id
LEFT JOIN fork_counts fc     ON fc.repo_id = r.repo_id
LEFT JOIN commit_counts cc   ON cc.repo_id = r.repo_id
LEFT JOIN language_top lt    ON lt.repo_id = r.repo_id
LEFT JOIN core_project_links cpl ON cpl.repo_id = r.repo_id;

COMMENT ON VIEW analytics.github_repos IS
    'Per-GitHub-repo summary with star/fork/commit/issue/PR rollups and link to CFDE '
    'core projects via core_project_numbers (TEXT[]). UNNEST to filter by a specific '
    'core project: WHERE ''U54OD036472'' = ANY (core_project_numbers).';

COMMENT ON COLUMN analytics.github_repos.repo_id IS 'GitHub repo id. PK.';
COMMENT ON COLUMN analytics.github_repos.full_name IS '"owner/name" identifier.';
COMMENT ON COLUMN analytics.github_repos.stars IS 'Star count from raw.github_stars.';
COMMENT ON COLUMN analytics.github_repos.forks IS 'Fork count from raw.github_forks.';
COMMENT ON COLUMN analytics.github_repos.commits IS 'Tracked commit count (raw.github_commits).';
COMMENT ON COLUMN analytics.github_repos.last_commit_at IS 'Most recent committed_at timestamp.';
COMMENT ON COLUMN analytics.github_repos.primary_language IS 'Language with most bytes in raw.github_languages.';
COMMENT ON COLUMN analytics.github_repos.core_project_numbers IS
    'Array of CFDE core_project_numbers this repo was discovered under (via topic/search).';


CREATE OR REPLACE VIEW analytics.github_activity_weekly AS
SELECT repo_id, DATE_TRUNC('week', committed_at) AS week, 'commit'::TEXT AS kind, COUNT(*)::INTEGER AS count
    FROM raw.github_commits WHERE committed_at IS NOT NULL GROUP BY repo_id, DATE_TRUNC('week', committed_at)
UNION ALL
SELECT repo_id, DATE_TRUNC('week', created_at) AS week,
       CASE WHEN is_pull_request THEN 'pull_request' ELSE 'issue' END,
       COUNT(*)::INTEGER
    FROM raw.github_issues WHERE created_at IS NOT NULL GROUP BY repo_id, DATE_TRUNC('week', created_at), is_pull_request
UNION ALL
SELECT repo_id, DATE_TRUNC('week', starred_at) AS week, 'star'::TEXT, COUNT(*)::INTEGER
    FROM raw.github_stars GROUP BY repo_id, DATE_TRUNC('week', starred_at);

COMMENT ON VIEW analytics.github_activity_weekly IS
    'Per-(repo, week, kind) activity counts. kind in {commit, issue, pull_request, star}. '
    'Drives "trend over time" chat queries. Join on repo_id to analytics.github_repos.';


CREATE OR REPLACE VIEW analytics.github_contributors AS
SELECT repo_id, login, contributions, fetched_at AS data_refreshed_at
FROM raw.github_contributors;

COMMENT ON VIEW analytics.github_contributors IS
    'Per-(repo, contributor) contribution counts. Aggregate across repos to find '
    'top contributors. login may be a bot account.';
