-- 0033 — Raw tables for the pubsearch (PPST-compatible publication tiers) pipeline.
--
-- See docs/pubsearch/SPEC.md. One Europe PMC search run per (program, git sha of
-- the program yaml, timestamp) lands here verbatim: the queries we rendered, the
-- hits Europe PMC returned per query, later the full-text evidence sentences per
-- candidate paper. Analyst overrides live alongside so the analytics views can
-- respect them. Nothing here is derived; analytics.pubsearch_* views do the
-- tiering.
--
-- run_id is the reproducibility handle: it encodes the program yaml git sha
-- (stored separately in program_yaml_sha) plus the run timestamp, so any row in
-- this schema can be traced back to the exact curated inputs that produced it.

CREATE TABLE IF NOT EXISTS raw.epmc_runs (
    run_id            TEXT        PRIMARY KEY,
    program           TEXT        NOT NULL,
    program_yaml_sha  TEXT,
    date_window_start INT,
    date_window_end   INT,
    started_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at       TIMESTAMPTZ,
    notes             TEXT
);

COMMENT ON TABLE raw.epmc_runs IS
    'One row per pubsearch run of a Common Fund program against Europe PMC. Written by '
    'flows.pubsearch_run. run_id = program yaml git sha + run timestamp, so a run is '
    'reproducible from (program_yaml_sha, run_id). Parent of raw.epmc_queries and '
    'raw.epmc_hits.';
COMMENT ON COLUMN raw.epmc_runs.run_id IS
    'Run identifier, e.g. cfde-<sha7>-<YYYYMMDDTHHMMSS>. PK; FK target for epmc_queries.';
COMMENT ON COLUMN raw.epmc_runs.program IS
    'Common Fund program slug the run covers, e.g. cfde. Matches pubsearch/programs/<program>.yaml.';
COMMENT ON COLUMN raw.epmc_runs.program_yaml_sha IS
    'Git commit sha of pubsearch/programs/<program>.yaml used to generate the seeds. '
    'Together with run_id this pins the exact curated inputs.';
COMMENT ON COLUMN raw.epmc_runs.date_window_start IS
    'First publication year included in every query (inclusive). NULL = unbounded.';
COMMENT ON COLUMN raw.epmc_runs.date_window_end IS
    'Last publication year included in every query (inclusive). NULL = unbounded.';
COMMENT ON COLUMN raw.epmc_runs.started_at IS 'When flows.pubsearch_run started this run.';
COMMENT ON COLUMN raw.epmc_runs.finished_at IS
    'When the run completed. NULL while in progress or if it aborted.';
COMMENT ON COLUMN raw.epmc_runs.notes IS 'Free-text operator notes about this run.';


CREATE TABLE IF NOT EXISTS raw.epmc_queries (
    run_id           TEXT        NOT NULL REFERENCES raw.epmc_runs (run_id),
    query_no         INT         NOT NULL,
    program          TEXT        NOT NULL,
    impact_category  TEXT        NOT NULL,
    query_cluster    TEXT        NOT NULL,
    search_terms     TEXT        NOT NULL,
    search_field     TEXT        NOT NULL DEFAULT '',
    or_terms         TEXT,
    or_search_field  TEXT,
    and_terms        TEXT,
    and_search_field TEXT,
    not_terms        TEXT,
    not_search_field TEXT,
    notes            TEXT,
    epmc_query       TEXT        NOT NULL,
    hit_count        INT,
    fetched_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, query_no)
);

COMMENT ON TABLE raw.epmc_queries IS
    'One row per query executed in a pubsearch run. Written by flows.pubsearch_run. '
    'Columns program..notes mirror the PPST Script_Input sheet one-to-one so a run can '
    'be exported back to the Eval team''s format; epmc_query is the rendered Europe PMC '
    'query string and hit_count what Europe PMC reported for it. run_id ties the row to '
    'the program yaml sha + timestamp in raw.epmc_runs.';
COMMENT ON COLUMN raw.epmc_queries.run_id IS 'FK to raw.epmc_runs.run_id.';
COMMENT ON COLUMN raw.epmc_queries.query_no IS
    'Row number of the query within the run (PPST Script_Input row order, 1-based).';
COMMENT ON COLUMN raw.epmc_queries.program IS 'PPST Program column: program slug/name.';
COMMENT ON COLUMN raw.epmc_queries.impact_category IS
    'PPST Impact_Category column: the tier this query feeds. One of Awardee, User, Broader.Influence.';
COMMENT ON COLUMN raw.epmc_queries.query_cluster IS
    'PPST Query_Cluster column: grouping label for the summary (e.g. grant, dbgap, resource_url, program_name).';
COMMENT ON COLUMN raw.epmc_queries.search_terms IS
    'PPST Search_Terms column: primary term(s), the seed value.';
COMMENT ON COLUMN raw.epmc_queries.search_field IS
    'PPST Search_Field column: Europe PMC section prefix for search_terms (METHODS, ACK_FUND, ...). Empty string = whole record.';
COMMENT ON COLUMN raw.epmc_queries.or_terms IS 'PPST OR_Terms column: OR-ed alternatives to search_terms.';
COMMENT ON COLUMN raw.epmc_queries.or_search_field IS 'PPST OR_Search_Field column: section prefix for or_terms.';
COMMENT ON COLUMN raw.epmc_queries.and_terms IS 'PPST AND_Terms column: terms that must also match (disambiguators).';
COMMENT ON COLUMN raw.epmc_queries.and_search_field IS 'PPST AND_Search_Field column: section prefix for and_terms.';
COMMENT ON COLUMN raw.epmc_queries.not_terms IS 'PPST NOT_Terms column: terms that exclude a record.';
COMMENT ON COLUMN raw.epmc_queries.not_search_field IS 'PPST NOT_Search_Field column: section prefix for not_terms.';
COMMENT ON COLUMN raw.epmc_queries.notes IS 'PPST Notes column: free text, includes seed provenance (source table or curated).';
COMMENT ON COLUMN raw.epmc_queries.epmc_query IS
    'Fully rendered Europe PMC query string actually sent, including the date window.';
COMMENT ON COLUMN raw.epmc_queries.hit_count IS
    'hitCount reported by Europe PMC for epmc_query. NULL if the request failed.';
COMMENT ON COLUMN raw.epmc_queries.fetched_at IS 'When the query was executed.';


CREATE TABLE IF NOT EXISTS raw.epmc_hits (
    run_id         TEXT        NOT NULL,
    query_no       INT         NOT NULL,
    epmc_id        TEXT        NOT NULL,
    source         TEXT        NOT NULL,
    pmid           TEXT,
    pmcid          TEXT,
    pub_year       INT,
    is_open_access BOOLEAN,
    title          TEXT,
    fetched_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, query_no, source, epmc_id),
    FOREIGN KEY (run_id, query_no) REFERENCES raw.epmc_queries (run_id, query_no)
);

CREATE INDEX IF NOT EXISTS epmc_hits_run_pmid_idx ON raw.epmc_hits (run_id, pmid);

COMMENT ON TABLE raw.epmc_hits IS
    'One row per (query, Europe PMC record) returned in a pubsearch run. Written by '
    'flows.pubsearch_run. A paper matched by several queries appears once per query; '
    'analytics.pubsearch_matrix collapses to one row per (program, pmid). Preprints have '
    'source = PPR and no pmid. run_id ties the row to the program yaml sha + timestamp '
    'in raw.epmc_runs.';
COMMENT ON COLUMN raw.epmc_hits.run_id IS 'FK (with query_no) to raw.epmc_queries.';
COMMENT ON COLUMN raw.epmc_hits.query_no IS 'FK (with run_id) to raw.epmc_queries.';
COMMENT ON COLUMN raw.epmc_hits.epmc_id IS
    'Europe PMC record id. Only unique together with source (PMID for MED, PPR id for preprints, etc.).';
COMMENT ON COLUMN raw.epmc_hits.source IS
    'Europe PMC source: MED (MEDLINE), PMC, PPR (preprint), AGR, CBA, ... PPR rows have no pmid.';
COMMENT ON COLUMN raw.epmc_hits.pmid IS
    'PubMed identifier as text. NULL for preprints and non-MEDLINE records. Join key to analytics.publications.';
COMMENT ON COLUMN raw.epmc_hits.pmcid IS
    'PubMed Central id (PMC1234567). Present when full text is in PMC; drives the evidence pass.';
COMMENT ON COLUMN raw.epmc_hits.pub_year IS 'Publication year from Europe PMC.';
COMMENT ON COLUMN raw.epmc_hits.is_open_access IS 'Europe PMC isOpenAccess flag.';
COMMENT ON COLUMN raw.epmc_hits.title IS 'Article title from Europe PMC.';
COMMENT ON COLUMN raw.epmc_hits.fetched_at IS 'When this hit was fetched.';


CREATE TABLE IF NOT EXISTS raw.epmc_evidence (
    run_id     TEXT        NOT NULL,
    pmid       TEXT        NOT NULL,
    query_no   INT         NOT NULL,
    section    TEXT        NOT NULL,
    sentence   TEXT,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, pmid, query_no, section)
);

COMMENT ON TABLE raw.epmc_evidence IS
    'Full-text evidence for candidate papers: the sentence in which a query''s term was '
    'found, per section. Written by flows.pubsearch_evidence (milestone 3) from each '
    'candidate''s Europe PMC fullTextXML; candidates only, never the whole corpus. '
    'run_id ties the row to the program yaml sha + timestamp in raw.epmc_runs.';
COMMENT ON COLUMN raw.epmc_evidence.run_id IS 'Run this evidence was collected for. See raw.epmc_runs.';
COMMENT ON COLUMN raw.epmc_evidence.pmid IS 'PubMed identifier of the candidate paper.';
COMMENT ON COLUMN raw.epmc_evidence.query_no IS 'Query (within run_id) whose terms this sentence matched.';
COMMENT ON COLUMN raw.epmc_evidence.section IS
    'Full-text section the sentence came from (e.g. methods, ack_fund, results).';
COMMENT ON COLUMN raw.epmc_evidence.sentence IS 'The matching sentence, verbatim.';
COMMENT ON COLUMN raw.epmc_evidence.fetched_at IS 'When the full text was scanned.';


CREATE TABLE IF NOT EXISTS raw.pubsearch_overrides (
    program    TEXT        NOT NULL,
    pmid       TEXT        NOT NULL,
    tier       TEXT        NOT NULL CHECK (tier IN ('Awardee', 'User', 'Broader.Influence', 'Exclude')),
    reason     TEXT,
    decided_by TEXT,
    decided_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (program, pmid)
);

COMMENT ON TABLE raw.pubsearch_overrides IS
    'Analyst decisions that override the computed tier for a (program, pmid). Written by '
    'humans via the cfde-atlas review queue, never by a flow, and not tied to a run: '
    'analytics.pubsearch_* views apply the override to every run. tier = Exclude removes '
    'the paper from the program entirely.';
COMMENT ON COLUMN raw.pubsearch_overrides.program IS 'Program slug the override applies to.';
COMMENT ON COLUMN raw.pubsearch_overrides.pmid IS 'PubMed identifier of the paper.';
COMMENT ON COLUMN raw.pubsearch_overrides.tier IS
    'Forced tier: Awardee, User, Broader.Influence, or Exclude (drop the paper).';
COMMENT ON COLUMN raw.pubsearch_overrides.reason IS 'Why the analyst overrode the computed tier.';
COMMENT ON COLUMN raw.pubsearch_overrides.decided_by IS 'Who made the decision (email or handle).';
COMMENT ON COLUMN raw.pubsearch_overrides.decided_at IS 'When the decision was recorded.';
