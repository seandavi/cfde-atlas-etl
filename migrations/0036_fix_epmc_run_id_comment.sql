-- 0036 — Comment-only fix: run_id format is <program>-<YYYYMMDDTHHMMSS>-<sha7>
-- (flows.pubsearch_run), not sha-before-timestamp as 0033 said. Lexical max = newest.
COMMENT ON COLUMN raw.epmc_runs.run_id IS
    'Run identifier: <program>-<YYYYMMDDTHHMMSS>-<program_yaml_sha7>, e.g. '
    'cfde-20260911T181425-356da48. Sorts lexically by time within a program, so '
    'max(run_id) is the newest run. Reproducible from (program yaml git sha, run_id).';
