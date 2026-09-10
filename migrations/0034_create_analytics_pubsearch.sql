-- 0034 — Analytics views for the pubsearch (PPST-compatible publication tiers) pipeline.
--
-- See docs/pubsearch/SPEC.md. raw.epmc_* holds one row per (query, hit); these views
-- do the tiering: collapse hits to papers, apply the PPST hierarchy
-- (Awardee > User > Broader.Influence), apply analyst overrides from
-- raw.pubsearch_overrides, and roll up counts the way the PPST Summary sheet does.
--
-- These views are the LLM-facing contract for cfde-atlas's describe_table.
-- Change THESE views, not the raw tables, when adjusting what chat queries see.

CREATE OR REPLACE VIEW analytics.pubsearch_runs AS
SELECT
    r.run_id,
    r.program,
    r.program_yaml_sha,
    r.date_window_start,
    r.date_window_end,
    r.started_at,
    r.finished_at,
    r.notes,
    (SELECT COUNT(*) FROM raw.epmc_queries q WHERE q.run_id = r.run_id)::BIGINT AS query_count,
    (SELECT COUNT(DISTINCT (h.source, h.epmc_id)) FROM raw.epmc_hits h WHERE h.run_id = r.run_id)::BIGINT AS hit_count,
    (SELECT COUNT(DISTINCT h.pmid) FROM raw.epmc_hits h WHERE h.run_id = r.run_id)::BIGINT AS unique_pmids,
    (SELECT COUNT(DISTINCT h.epmc_id) FROM raw.epmc_hits h WHERE h.run_id = r.run_id AND h.source = 'PPR')::BIGINT AS preprint_hits
FROM raw.epmc_runs r;

COMMENT ON VIEW analytics.pubsearch_runs IS
    'One row per pubsearch run (raw.epmc_runs) with headline counts: queries executed, '
    'distinct Europe PMC records hit, distinct PMIDs, and preprint records. Start here to '
    'pick a run_id, then query analytics.pubsearch_matrix / pubsearch_summary for it.';
COMMENT ON COLUMN analytics.pubsearch_runs.run_id IS 'Run identifier (PK). Join key to pubsearch_matrix and pubsearch_summary.';
COMMENT ON COLUMN analytics.pubsearch_runs.program IS 'Common Fund program slug the run covers, e.g. cfde.';
COMMENT ON COLUMN analytics.pubsearch_runs.program_yaml_sha IS 'Git sha of pubsearch/programs/<program>.yaml used for this run; with run_id pins the exact inputs.';
COMMENT ON COLUMN analytics.pubsearch_runs.date_window_start IS 'First publication year included in every query (inclusive). NULL = unbounded.';
COMMENT ON COLUMN analytics.pubsearch_runs.date_window_end IS 'Last publication year included in every query (inclusive). NULL = unbounded.';
COMMENT ON COLUMN analytics.pubsearch_runs.started_at IS 'When the run started.';
COMMENT ON COLUMN analytics.pubsearch_runs.finished_at IS 'When the run completed. NULL while in progress or if it aborted.';
COMMENT ON COLUMN analytics.pubsearch_runs.notes IS 'Free-text operator notes about this run.';
COMMENT ON COLUMN analytics.pubsearch_runs.query_count IS 'Number of queries executed in the run (rows in raw.epmc_queries).';
COMMENT ON COLUMN analytics.pubsearch_runs.hit_count IS 'Distinct Europe PMC records (source, epmc_id) returned by any query in the run. Before overrides.';
COMMENT ON COLUMN analytics.pubsearch_runs.unique_pmids IS 'Distinct non-NULL PMIDs among the hits. Excludes preprints, which have no pmid.';
COMMENT ON COLUMN analytics.pubsearch_runs.preprint_hits IS 'Distinct preprint records (source = PPR) among the hits.';


CREATE OR REPLACE VIEW analytics.pubsearch_matrix AS
WITH hq AS (
    SELECT
        h.run_id,
        q.program,
        COALESCE(h.pmid, h.source || ':' || h.epmc_id) AS paper_key,
        h.pmid, h.pmcid, h.source, h.pub_year, h.title, h.is_open_access,
        q.query_no, q.impact_category, q.query_cluster
    FROM raw.epmc_hits h
    JOIN raw.epmc_queries q USING (run_id, query_no)
),
papers AS (
    -- ponytail: MIN/MAX collapse the rare case of one pmid under two sources; first-seen would need window functions.
    SELECT
        run_id,
        program,
        paper_key,
        MAX(pmid)                                            AS pmid,
        MAX(pmcid)                                           AS pmcid,
        MIN(source)                                          AS source,
        BOOL_OR(source = 'PPR')                              AS is_preprint,
        MAX(pub_year)                                        AS pub_year,
        MAX(title)                                           AS title,
        BOOL_OR(is_open_access)                              AS is_open_access,
        BOOL_OR(impact_category = 'Awardee')                 AS awardee,
        BOOL_OR(impact_category = 'User')                    AS user_tier,
        BOOL_OR(impact_category = 'Broader.Influence')       AS broader_influence,
        COUNT(DISTINCT query_no)::INT                        AS n_queries,
        ARRAY_AGG(DISTINCT query_cluster ORDER BY query_cluster) AS clusters,
        ARRAY_AGG(DISTINCT query_no ORDER BY query_no)       AS query_nos
    FROM hq
    GROUP BY run_id, program, paper_key
),
ev AS (
    SELECT run_id, pmid, STRING_AGG(DISTINCT sentence, E'\n') AS evidence
    FROM raw.epmc_evidence
    WHERE sentence IS NOT NULL
    GROUP BY run_id, pmid
)
SELECT
    p.run_id,
    p.program,
    p.paper_key,
    p.pmid,
    p.pmcid,
    p.source,
    p.is_preprint,
    p.pub_year,
    p.title,
    p.is_open_access,
    p.awardee,
    p.user_tier,
    p.broader_influence,
    CASE WHEN p.awardee THEN 'Awardee'
         WHEN p.user_tier THEN 'User'
         ELSE 'Broader.Influence' END                        AS computed_assignment,
    o.tier                                                   AS override_tier,
    COALESCE(o.tier, CASE WHEN p.awardee THEN 'Awardee'
                          WHEN p.user_tier THEN 'User'
                          ELSE 'Broader.Influence' END)      AS final_assignment,
    p.n_queries,
    p.clusters,
    p.query_nos,
    e.evidence
FROM papers p
LEFT JOIN raw.pubsearch_overrides o ON o.program = p.program AND o.pmid = p.pmid
LEFT JOIN ev e ON e.run_id = p.run_id AND e.pmid = p.pmid
WHERE o.tier IS DISTINCT FROM 'Exclude';

COMMENT ON VIEW analytics.pubsearch_matrix IS
    'One row per (run_id, program, paper) — the PPST Data_Matrixed_Query / '
    'Data_Matrixed_Cluster shape. Collapses raw.epmc_hits to papers (paper_key = pmid, or '
    'source:epmc_id for preprints and other pmid-less records), flags which tiers'' queries '
    'found each paper, applies the PPST hierarchy Awardee > User > Broader.Influence to get '
    'computed_assignment, then applies raw.pubsearch_overrides to get final_assignment. '
    'Papers with an Exclude override are dropped entirely. evidence carries the full-text '
    'sentences from raw.epmc_evidence when the evidence pass has run.';
COMMENT ON COLUMN analytics.pubsearch_matrix.run_id IS 'Run this row belongs to. FK to analytics.pubsearch_runs.run_id.';
COMMENT ON COLUMN analytics.pubsearch_matrix.program IS 'Common Fund program slug, e.g. cfde.';
COMMENT ON COLUMN analytics.pubsearch_matrix.paper_key IS 'Paper identity within the run: pmid when present, else source:epmc_id (preprints). Unique per (run_id, program).';
COMMENT ON COLUMN analytics.pubsearch_matrix.pmid IS 'PubMed identifier as text. NULL for preprints. Join key to analytics.publications.';
COMMENT ON COLUMN analytics.pubsearch_matrix.pmcid IS 'PubMed Central id (PMC1234567) when full text is in PMC.';
COMMENT ON COLUMN analytics.pubsearch_matrix.source IS 'Europe PMC source of the record: MED, PMC, PPR (preprint), ...';
COMMENT ON COLUMN analytics.pubsearch_matrix.is_preprint IS 'TRUE when the record is a preprint (source = PPR). Tier counts are reported with and without these.';
COMMENT ON COLUMN analytics.pubsearch_matrix.pub_year IS 'Publication year from Europe PMC.';
COMMENT ON COLUMN analytics.pubsearch_matrix.title IS 'Article title from Europe PMC.';
COMMENT ON COLUMN analytics.pubsearch_matrix.is_open_access IS 'Europe PMC isOpenAccess flag.';
COMMENT ON COLUMN analytics.pubsearch_matrix.awardee IS 'TRUE if any query with impact_category = Awardee (program grant number in funding) found the paper.';
COMMENT ON COLUMN analytics.pubsearch_matrix.user_tier IS 'TRUE if any query with impact_category = User (program resource in Methods/Acknowledgements) found the paper.';
COMMENT ON COLUMN analytics.pubsearch_matrix.broader_influence IS 'TRUE if any query with impact_category = Broader.Influence (cites an awardee paper, program name elsewhere) found the paper.';
COMMENT ON COLUMN analytics.pubsearch_matrix.computed_assignment IS 'Tier from the PPST hierarchy, highest wins: Awardee if awardee, else User if user_tier, else Broader.Influence.';
COMMENT ON COLUMN analytics.pubsearch_matrix.override_tier IS 'Analyst override from raw.pubsearch_overrides for (program, pmid), or NULL. Exclude overrides never appear here: those rows are dropped.';
COMMENT ON COLUMN analytics.pubsearch_matrix.final_assignment IS 'COALESCE(override_tier, computed_assignment). The tier to report. One of Awardee, User, Broader.Influence.';
COMMENT ON COLUMN analytics.pubsearch_matrix.n_queries IS 'Number of distinct queries in the run that returned this paper.';
COMMENT ON COLUMN analytics.pubsearch_matrix.clusters IS 'Distinct query_cluster labels of the queries that found the paper (PPST Data_Matrixed_Cluster columns), sorted.';
COMMENT ON COLUMN analytics.pubsearch_matrix.query_nos IS 'query_no values of the queries that found the paper (PPST Data_Matrixed_Query columns), sorted. Join to raw.epmc_queries.';
COMMENT ON COLUMN analytics.pubsearch_matrix.evidence IS 'Distinct full-text evidence sentences for this (run_id, pmid) from raw.epmc_evidence, newline-separated. NULL until the evidence pass runs or if the paper has no PMC full text.';


CREATE OR REPLACE VIEW analytics.pubsearch_summary AS
SELECT
    run_id,
    program,
    'tier'::TEXT                                    AS level,
    final_assignment                                AS label,
    NULL::TEXT                                      AS impact_category,
    COUNT(*)::BIGINT                                AS paper_count,
    COUNT(*) FILTER (WHERE NOT is_preprint)::BIGINT AS paper_count_excl_preprints,
    COUNT(DISTINCT pmid)::BIGINT                    AS pmid_count
FROM analytics.pubsearch_matrix
GROUP BY run_id, program, final_assignment
UNION ALL
SELECT
    m.run_id,
    m.program,
    'cluster'::TEXT                                 AS level,
    q.query_cluster                                 AS label,
    MIN(q.impact_category)                          AS impact_category,
    COUNT(DISTINCT m.paper_key)::BIGINT             AS paper_count,
    COUNT(DISTINCT m.paper_key) FILTER (WHERE NOT m.is_preprint)::BIGINT AS paper_count_excl_preprints,
    COUNT(DISTINCT m.pmid)::BIGINT                  AS pmid_count
FROM analytics.pubsearch_matrix m
JOIN raw.epmc_queries q ON q.run_id = m.run_id AND q.query_no = ANY (m.query_nos)
GROUP BY m.run_id, m.program, q.query_cluster;

COMMENT ON VIEW analytics.pubsearch_summary IS
    'Per (run_id, program) paper counts, mirroring the PPST Summary sheet. level = tier '
    'rows (Impact_Category_Summary: one per final_assignment, label = the tier) and '
    'level = cluster rows (Cluster_Summary: one per query_cluster, label = the cluster). '
    'Counts come from analytics.pubsearch_matrix, so overrides and Exclude are already '
    'applied; paper_count_excl_preprints gives the count without PPR records. A paper '
    'found by several clusters is counted in each cluster, so cluster rows do not sum '
    'to the tier rows.';
COMMENT ON COLUMN analytics.pubsearch_summary.run_id IS 'Run the counts are for. FK to analytics.pubsearch_runs.run_id.';
COMMENT ON COLUMN analytics.pubsearch_summary.program IS 'Common Fund program slug, e.g. cfde.';
COMMENT ON COLUMN analytics.pubsearch_summary.level IS 'tier = counts per final_assignment; cluster = counts per query_cluster.';
COMMENT ON COLUMN analytics.pubsearch_summary.label IS 'The tier (Awardee, User, Broader.Influence) for level = tier; the query_cluster name for level = cluster.';
COMMENT ON COLUMN analytics.pubsearch_summary.impact_category IS 'For level = cluster: the tier the cluster''s queries feed. NULL for level = tier (label already is the tier).';
COMMENT ON COLUMN analytics.pubsearch_summary.paper_count IS 'Distinct papers (paper_key) in the group, preprints included.';
COMMENT ON COLUMN analytics.pubsearch_summary.paper_count_excl_preprints IS 'Distinct papers in the group excluding preprints (source = PPR).';
COMMENT ON COLUMN analytics.pubsearch_summary.pmid_count IS 'Distinct non-NULL PMIDs in the group.';
