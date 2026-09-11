-- 0035 — "Latest completed run per program" views for the chat surface.
--
-- analytics.pubsearch_matrix / pubsearch_summary carry every run. The LLM in
-- cfde-atlas should not have to discover run ids, so these views pin each
-- program to its most recent finished, non-smoke run. run_id sorts
-- lexically as <program>-<YYYYMMDDTHHMMSS>-<sha7>, so max(run_id) is the newest.
-- Column comments are copied from the underlying views (they drive describe_table).

CREATE OR REPLACE VIEW analytics.pubsearch_latest_run AS
SELECT program, max(run_id) AS run_id
FROM raw.epmc_runs
WHERE finished_at IS NOT NULL AND coalesce(notes, '') NOT ILIKE 'smoke%'
GROUP BY program;

COMMENT ON VIEW analytics.pubsearch_latest_run IS
    'One row per program: the run_id of its most recent completed, non-smoke pubsearch run. '
    'Join key for pinning pubsearch_matrix / pubsearch_summary to the current numbers.';
COMMENT ON COLUMN analytics.pubsearch_latest_run.program IS 'Program id, e.g. cfde.';
COMMENT ON COLUMN analytics.pubsearch_latest_run.run_id IS 'Newest finished run for the program (lexical max; format <program>-<timestamp>-<yaml sha7>).';

CREATE OR REPLACE VIEW analytics.pubsearch_current AS
SELECT m.*
FROM analytics.pubsearch_matrix m
JOIN analytics.pubsearch_latest_run l USING (program, run_id);

COMMENT ON VIEW analytics.pubsearch_current IS
    'PPST-style publication impact tiers, LATEST run per program: one row per paper found by '
    'the Europe PMC search, with awardee / user_tier / broader_influence flags and '
    'final_assignment (Awardee > User > Broader.Influence, analyst overrides applied). '
    'Use this instead of pubsearch_matrix unless a specific run_id is wanted. Counts should '
    'usually exclude preprints (is_preprint). Awardee here is Europe PMC grant-number search; '
    'analytics.publications is NIH RePORTER linkage — the two overlap but differ.';

CREATE OR REPLACE VIEW analytics.pubsearch_current_summary AS
SELECT s.*
FROM analytics.pubsearch_summary s
JOIN analytics.pubsearch_latest_run l USING (program, run_id);

COMMENT ON VIEW analytics.pubsearch_current_summary IS
    'Tier and cluster counts for the LATEST pubsearch run per program (level = tier | cluster). '
    'paper_count_excl_preprints is the number to report. Never sum Broader.Influence with the '
    'other tiers: it is citation chasing and dwarfs them.';

DO $$
DECLARE r record; src text; dst text;
BEGIN
  FOR src, dst IN VALUES ('analytics.pubsearch_matrix', 'analytics.pubsearch_current'),
                         ('analytics.pubsearch_summary', 'analytics.pubsearch_current_summary') LOOP
    FOR r IN SELECT a.attname, col_description(src::regclass, a.attnum) AS d
             FROM pg_attribute a WHERE a.attrelid = src::regclass AND a.attnum > 0 AND NOT a.attisdropped LOOP
      IF r.d IS NOT NULL THEN
        EXECUTE format('COMMENT ON COLUMN %s.%I IS %L', dst, r.attname, r.d);
      END IF;
    END LOOP;
  END LOOP;
END $$;
