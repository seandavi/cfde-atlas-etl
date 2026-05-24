-- 0031 — Cross-DCC C2M2 analytics rollups.
--
-- These views are what chat hits to answer "how big is CFDE", "what's in each DCC",
-- "which DCCs cover which diseases", etc. They mirror the numbers surfaced on
-- cfde.cloud/data/processed.

CREATE OR REPLACE VIEW analytics.c2m2_summary AS
SELECT
    d.dcc_id,
    d.dcc_abbreviation,
    d.dcc_name,
    (SELECT COUNT(*) FROM c2m2.file       f WHERE f.dcc_id = d.dcc_id) AS file_count,
    (SELECT COUNT(*) FROM c2m2.biosample  b WHERE b.dcc_id = d.dcc_id) AS biosample_count,
    (SELECT COUNT(*) FROM c2m2.subject    s WHERE s.dcc_id = d.dcc_id) AS subject_count,
    (SELECT COUNT(*) FROM c2m2.collection c WHERE c.dcc_id = d.dcc_id) AS collection_count,
    (SELECT COUNT(*) FROM c2m2.project    p WHERE p.dcc_id = d.dcc_id) AS project_count,
    (SELECT COALESCE(SUM(size_in_bytes), 0) FROM c2m2.file f WHERE f.dcc_id = d.dcc_id) AS total_file_bytes,
    d.submission_date,
    d.fetched_at AS data_refreshed_at
FROM c2m2.dcc d;

COMMENT ON VIEW analytics.c2m2_summary IS
    'One row per CFDE DCC with C2M2 entity counts + on-disk file footprint. Matches '
    'the top-level numbers on cfde.cloud/data/processed. submission_date is when the '
    'underlying C2M2 datapackage was assembled by the DCC.';

COMMENT ON COLUMN analytics.c2m2_summary.dcc_id IS 'C2M2 DCC id (e.g. "cfde_registry_dcc:gtex"). PK.';
COMMENT ON COLUMN analytics.c2m2_summary.dcc_abbreviation IS 'Short program name (GTEx, LINCS, ...).';
COMMENT ON COLUMN analytics.c2m2_summary.file_count IS 'Distinct files in c2m2.file for this DCC.';
COMMENT ON COLUMN analytics.c2m2_summary.biosample_count IS 'Distinct biosamples in c2m2.biosample for this DCC.';
COMMENT ON COLUMN analytics.c2m2_summary.subject_count IS 'Distinct subjects in c2m2.subject for this DCC.';
COMMENT ON COLUMN analytics.c2m2_summary.collection_count IS 'Distinct collections in c2m2.collection for this DCC.';
COMMENT ON COLUMN analytics.c2m2_summary.project_count IS 'Distinct DCC-side projects (parents + sub-projects).';
COMMENT ON COLUMN analytics.c2m2_summary.total_file_bytes IS
    'Sum of size_in_bytes across all files declared by this DCC. Approximate on-disk footprint.';
COMMENT ON COLUMN analytics.c2m2_summary.submission_date IS
    'Date of the underlying C2M2 datapackage submission.';


CREATE OR REPLACE VIEW analytics.c2m2_file_format_mix AS
SELECT
    f.dcc_id,
    d.dcc_abbreviation,
    f.file_format,
    ff.name        AS file_format_name,
    COUNT(*)::BIGINT                        AS file_count,
    COALESCE(SUM(f.size_in_bytes), 0)::BIGINT AS total_bytes
FROM c2m2.file f
LEFT JOIN c2m2.dcc d ON d.dcc_id = f.dcc_id
LEFT JOIN c2m2.file_format ff ON ff.id = f.file_format
WHERE f.file_format IS NOT NULL
GROUP BY f.dcc_id, d.dcc_abbreviation, f.file_format, ff.name;

COMMENT ON VIEW analytics.c2m2_file_format_mix IS
    'Per (DCC, file_format): count of files + total bytes. file_format_name is the '
    'human label resolved via c2m2.file_format. Use to answer "what formats does each '
    'DCC publish?" and "how big is each format across CFDE?".';


CREATE OR REPLACE VIEW analytics.c2m2_assay_coverage AS
SELECT
    f.dcc_id,
    d.dcc_abbreviation,
    f.assay_type,
    at.name AS assay_type_name,
    COUNT(*)::BIGINT AS file_count
FROM c2m2.file f
LEFT JOIN c2m2.dcc d ON d.dcc_id = f.dcc_id
LEFT JOIN c2m2.assay_type at ON at.id = f.assay_type
WHERE f.assay_type IS NOT NULL
GROUP BY f.dcc_id, d.dcc_abbreviation, f.assay_type, at.name;

COMMENT ON VIEW analytics.c2m2_assay_coverage IS
    'Per (DCC, assay_type CURIE): number of files. Drives "which DCCs do scRNA-seq?" '
    '"which programs share assay X?" Filter with WHERE assay_type = ''OBI:0002762''.';


CREATE OR REPLACE VIEW analytics.c2m2_anatomy_coverage AS
SELECT
    b.dcc_id,
    d.dcc_abbreviation,
    b.anatomy,
    a.name AS anatomy_name,
    COUNT(*)::BIGINT AS biosample_count
FROM c2m2.biosample b
LEFT JOIN c2m2.dcc d ON d.dcc_id = b.dcc_id
LEFT JOIN c2m2.anatomy a ON a.id = b.anatomy
WHERE b.anatomy IS NOT NULL
GROUP BY b.dcc_id, d.dcc_abbreviation, b.anatomy, a.name;

COMMENT ON VIEW analytics.c2m2_anatomy_coverage IS
    'Per (DCC, anatomy CURIE): number of biosamples. Uses Uberon ids. Cross-DCC '
    'anatomy overlap can be derived by self-joining on anatomy.';


CREATE OR REPLACE VIEW analytics.c2m2_disease_coverage AS
SELECT
    src.dcc_id,
    d.dcc_abbreviation,
    src.disease,
    dis.name AS disease_name,
    SUM(CASE WHEN src.entity = 'biosample'  THEN 1 ELSE 0 END)::BIGINT AS biosample_count,
    SUM(CASE WHEN src.entity = 'subject'    THEN 1 ELSE 0 END)::BIGINT AS subject_count,
    SUM(CASE WHEN src.entity = 'collection' THEN 1 ELSE 0 END)::BIGINT AS collection_count
FROM (
    SELECT dcc_id, disease, 'biosample'::TEXT  AS entity FROM c2m2.biosample_disease
    UNION ALL
    SELECT dcc_id, disease, 'subject'::TEXT    AS entity FROM c2m2.subject_disease
    UNION ALL
    SELECT dcc_id, disease, 'collection'::TEXT AS entity FROM c2m2.collection_disease
) src
LEFT JOIN c2m2.dcc d ON d.dcc_id = src.dcc_id
LEFT JOIN c2m2.disease dis ON dis.id = src.disease
GROUP BY src.dcc_id, d.dcc_abbreviation, src.disease, dis.name;

COMMENT ON VIEW analytics.c2m2_disease_coverage IS
    'Per (DCC, disease) — biosample / subject / collection counts unioned across the '
    'three disease-association tables. Use to answer "which programs touch disease X?".';


CREATE OR REPLACE VIEW analytics.c2m2_subject_demographics AS
SELECT
    s.dcc_id,
    d.dcc_abbreviation,
    s.sex,
    s.ethnicity,
    sr.race,
    COUNT(*)::BIGINT AS subject_count
FROM c2m2.subject s
LEFT JOIN c2m2.dcc d ON d.dcc_id = s.dcc_id
LEFT JOIN c2m2.subject_race sr
    ON sr.subject_id_namespace = s.id_namespace
   AND sr.subject_local_id     = s.local_id
GROUP BY s.dcc_id, d.dcc_abbreviation, s.sex, s.ethnicity, sr.race;

COMMENT ON VIEW analytics.c2m2_subject_demographics IS
    'Per (DCC, sex, ethnicity, race) subject counts. sex/ethnicity are CURIE-coded '
    '(e.g. cfde_subject_sex:1 = female). race comes from c2m2.subject_race.';
