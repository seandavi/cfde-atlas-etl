-- 0026 — Sustainability + community-profile flags on raw.github_repos.
--
-- The base /repos/{o}/{n} response carries license, topics, size, archived,
-- is_template, default_branch, homepage. Those project cleanly into the
-- analytics view from `source` without schema change. What we DO need a
-- column for is the boolean presence flags that come from a separate
-- /community/profile call (and a workflow-files count): putting them in
-- their own column keeps them queryable + cheap-to-join without unrolling
-- jsonb.

ALTER TABLE raw.github_repos
    ADD COLUMN IF NOT EXISTS features JSONB NOT NULL DEFAULT '{}'::JSONB;

COMMENT ON COLUMN raw.github_repos.features IS
    'Community-profile + workflow flags collected per-repo. Schema (all keys '
    'optional; absent keys mean unknown / not yet checked): '
    '{has_readme bool, has_security bool, has_contributing bool, '
    'has_coc bool, has_citation bool, has_funding bool, workflow_files int}. '
    'Drives sustainability columns in analytics.github_repos.';
