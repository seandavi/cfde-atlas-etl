-- 0020 — Raw layer for GitHub activity.
--
-- One row-per-entity table per logical concept. Many-to-many between repos and
-- CFDE core projects via the explicit raw.github_repo_core_projects link table —
-- a single repo can match multiple core_project_numbers via topic/search hits.

CREATE TABLE IF NOT EXISTS raw.github_repos (
    repo_id        BIGINT      NOT NULL PRIMARY KEY,
    full_name      TEXT        NOT NULL,
    source         JSONB       NOT NULL,
    fetched_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS raw_github_repos_full_name_idx
    ON raw.github_repos (full_name);

COMMENT ON TABLE raw.github_repos IS
    'GitHub repository metadata. One row per repo_id. Use raw.github_repo_core_projects '
    'for the link to CFDE core_project_numbers.';

COMMENT ON COLUMN raw.github_repos.repo_id IS 'GitHub repo id. PK.';
COMMENT ON COLUMN raw.github_repos.full_name IS '"owner/name" GitHub identifier.';


CREATE TABLE IF NOT EXISTS raw.github_repo_core_projects (
    repo_id             BIGINT      NOT NULL,
    core_project_number TEXT        NOT NULL,
    discovered_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (repo_id, core_project_number)
);

CREATE INDEX IF NOT EXISTS raw_github_repo_core_projects_core_idx
    ON raw.github_repo_core_projects (core_project_number);

COMMENT ON TABLE raw.github_repo_core_projects IS
    'Many-to-many link between GitHub repos and CFDE core_project_numbers. '
    'Populated by topic/search hits during the github flow.';


CREATE TABLE IF NOT EXISTS raw.github_stars (
    repo_id    BIGINT      NOT NULL,
    user_id    BIGINT      NOT NULL,
    starred_at TIMESTAMPTZ NOT NULL,
    source     JSONB       NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (repo_id, user_id)
);

CREATE INDEX IF NOT EXISTS raw_github_stars_starred_at_idx
    ON raw.github_stars (starred_at);

COMMENT ON TABLE raw.github_stars IS
    'Per-(repo, user, timestamp) star events. Drives "stars over time" timeseries.';


CREATE TABLE IF NOT EXISTS raw.github_forks (
    fork_id         BIGINT      NOT NULL PRIMARY KEY,
    parent_repo_id  BIGINT      NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL,
    source          JSONB       NOT NULL,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS raw_github_forks_parent_idx
    ON raw.github_forks (parent_repo_id);

COMMENT ON TABLE raw.github_forks IS
    'Forks of tracked repos. parent_repo_id joins to raw.github_repos.repo_id.';


CREATE TABLE IF NOT EXISTS raw.github_commits (
    repo_id      BIGINT      NOT NULL,
    sha          TEXT        NOT NULL,
    committed_at TIMESTAMPTZ,
    source       JSONB       NOT NULL,
    fetched_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (repo_id, sha)
);

CREATE INDEX IF NOT EXISTS raw_github_commits_committed_at_idx
    ON raw.github_commits (committed_at);


CREATE TABLE IF NOT EXISTS raw.github_issues (
    repo_id          BIGINT      NOT NULL,
    number           INTEGER     NOT NULL,
    is_pull_request  BOOLEAN     NOT NULL DEFAULT FALSE,
    state            TEXT,
    created_at       TIMESTAMPTZ,
    closed_at        TIMESTAMPTZ,
    source           JSONB       NOT NULL,
    fetched_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (repo_id, number)
);

CREATE INDEX IF NOT EXISTS raw_github_issues_state_idx
    ON raw.github_issues (repo_id, state, is_pull_request);


CREATE TABLE IF NOT EXISTS raw.github_contributors (
    repo_id       BIGINT      NOT NULL,
    login         TEXT        NOT NULL,
    contributions INTEGER     NOT NULL DEFAULT 0,
    source        JSONB       NOT NULL,
    fetched_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (repo_id, login)
);


CREATE TABLE IF NOT EXISTS raw.github_languages (
    repo_id    BIGINT      NOT NULL,
    language   TEXT        NOT NULL,
    bytes      BIGINT      NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (repo_id, language)
);


CREATE TABLE IF NOT EXISTS raw.github_releases (
    repo_id      BIGINT      NOT NULL,
    tag_name     TEXT        NOT NULL,
    name         TEXT,
    published_at TIMESTAMPTZ,
    is_draft     BOOLEAN     NOT NULL DEFAULT FALSE,
    is_prerelease BOOLEAN    NOT NULL DEFAULT FALSE,
    source       JSONB       NOT NULL,
    fetched_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (repo_id, tag_name)
);
