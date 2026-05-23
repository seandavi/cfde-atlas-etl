-- 0027 — Per-repo README text + parsed CITATION.cff.
--
-- README text gives chat the "what does this repo do?" context. CITATION.cff
-- is the official software-citation file format; when present it carries the
-- explicit (repo) -> (DOI, PMID) crosswalk that lets us trace from "tool" to
-- "paper" — a missing link in the current data model.

CREATE TABLE IF NOT EXISTS raw.github_readmes (
    repo_id      BIGINT      NOT NULL PRIMARY KEY,
    path         TEXT,
    sha          TEXT,
    content      TEXT,
    truncated    BOOLEAN     NOT NULL DEFAULT FALSE,
    fetched_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE raw.github_readmes IS
    'Decoded README text per repo (one row per repo_id). Truncated to 256 KB '
    'to keep the row compact; truncated=true flags when the original was longer.';

COMMENT ON COLUMN raw.github_readmes.repo_id IS
    'GitHub repo id. PK. FK to raw.github_repos.repo_id.';

COMMENT ON COLUMN raw.github_readmes.path IS
    'File path in the repo (e.g. README.md, README.rst, docs/README.md). '
    'GitHub picks the canonical README per repo.';

COMMENT ON COLUMN raw.github_readmes.content IS
    'Decoded README text (UTF-8). NULL when content was binary or the fetch failed. '
    'Truncated to 256 KB.';

COMMENT ON COLUMN raw.github_readmes.truncated IS
    'TRUE when the original README exceeded 256 KB and content is a prefix.';


CREATE TABLE IF NOT EXISTS raw.github_citations (
    repo_id     BIGINT      NOT NULL PRIMARY KEY,
    source      JSONB       NOT NULL,
    doi         TEXT,
    pmid        INTEGER,
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS raw_github_citations_doi_idx
    ON raw.github_citations (doi) WHERE doi IS NOT NULL;
CREATE INDEX IF NOT EXISTS raw_github_citations_pmid_idx
    ON raw.github_citations (pmid) WHERE pmid IS NOT NULL;

COMMENT ON TABLE raw.github_citations IS
    'Parsed CITATION.cff for repos that publish one. Software-citation file format. '
    'doi/pmid are extracted from preferred-citation.doi/pmid or from identifiers[] '
    'where type=doi/pmid. NULL when CITATION.cff is absent or unparseable.';

COMMENT ON COLUMN raw.github_citations.repo_id IS
    'GitHub repo id. PK. FK to raw.github_repos.repo_id.';

COMMENT ON COLUMN raw.github_citations.source IS
    'Full parsed CITATION.cff (yaml -> json). Includes title, authors[], version, '
    'date-released, identifiers[], preferred-citation, etc.';

COMMENT ON COLUMN raw.github_citations.doi IS
    'DOI of the canonical paper for this software, if declared. Join key to '
    'analytics.publications.doi.';

COMMENT ON COLUMN raw.github_citations.pmid IS
    'PubMed ID of the canonical paper for this software, if declared. Join key to '
    'analytics.publications.pmid.';
