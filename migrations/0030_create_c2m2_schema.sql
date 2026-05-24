-- 0030 — C2M2 entity, association, and ontology tables.
--
-- One Postgres table per C2M2 TSV. Schema follows the official C2M2 spec column
-- names (https://docs.nih-cfde.org/en/latest/cfde-submit/docs/C2M2/). Each row
-- carries `dcc_id` + `submission_date` so we can answer "which DCC contributed
-- this" cheaply. Types are mostly TEXT — C2M2 uses CURIE strings + ontology IDs
-- as primary identifiers; we cast where the conversion is unambiguous.

CREATE SCHEMA IF NOT EXISTS c2m2;

-- ----------------------------------------------------------------------------
-- DCC + project identity
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS c2m2.dcc (
    dcc_id               TEXT NOT NULL PRIMARY KEY,
    dcc_name             TEXT,
    dcc_abbreviation     TEXT,
    dcc_description      TEXT,
    contact_email        TEXT,
    contact_name         TEXT,
    dcc_url              TEXT,
    project_id_namespace TEXT,
    project_local_id     TEXT,
    submission_date      DATE,
    fetched_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE c2m2.dcc IS
    'CFDE DCC identity from C2M2 dcc.tsv. 16 rows. The canonical mapping between '
    'a C2M2 namespace (e.g. "gtex") and the human-readable program (GTEx). '
    'Use dcc_abbreviation to cross-reference against analytics.core_projects (manual crosswalk).';
COMMENT ON COLUMN c2m2.dcc.dcc_id IS 'C2M2 DCC id, e.g. "cfde_registry_dcc:gtex". PK.';
COMMENT ON COLUMN c2m2.dcc.dcc_abbreviation IS 'Short program name (GTEx, LINCS, KFDRC, ...).';
COMMENT ON COLUMN c2m2.dcc.project_id_namespace IS
    'C2M2 namespace identifying this DCC''s top-level project. Joins to c2m2.project.id_namespace.';

CREATE TABLE IF NOT EXISTS c2m2.project (
    project_id_namespace TEXT NOT NULL,
    project_local_id     TEXT NOT NULL,
    persistent_id        TEXT,
    creation_time        TIMESTAMPTZ,
    abbreviation         TEXT,
    name                 TEXT,
    description          TEXT,
    dcc_id               TEXT,
    submission_date      DATE,
    fetched_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (project_id_namespace, project_local_id)
);
CREATE INDEX IF NOT EXISTS c2m2_project_dcc_idx ON c2m2.project (dcc_id);

COMMENT ON TABLE c2m2.project IS
    'DCC-side projects + sub-projects from C2M2 project.tsv. Hierarchy in c2m2.project_in_project.';
COMMENT ON COLUMN c2m2.project.project_id_namespace IS
    'C2M2 namespace this project lives in. Part of the composite PK.';
COMMENT ON COLUMN c2m2.project.project_local_id IS
    'Project id local to its namespace. Part of the composite PK.';
COMMENT ON COLUMN c2m2.project.dcc_id IS 'DCC this project belongs to. Joins to c2m2.dcc.dcc_id.';


CREATE TABLE IF NOT EXISTS c2m2.id_namespace (
    id           TEXT NOT NULL PRIMARY KEY,
    abbreviation TEXT,
    name         TEXT,
    description  TEXT,
    dcc_id       TEXT,
    submission_date DATE,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE c2m2.id_namespace IS
    'C2M2 identifier namespaces declared by each DCC submission.';

-- ----------------------------------------------------------------------------
-- Core entity: file, biosample, subject, collection
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS c2m2.file (
    id_namespace                    TEXT NOT NULL,
    local_id                        TEXT NOT NULL,
    project_id_namespace            TEXT,
    project_local_id                TEXT,
    persistent_id                   TEXT,
    creation_time                   TIMESTAMPTZ,
    size_in_bytes                   BIGINT,
    uncompressed_size_in_bytes      BIGINT,
    sha256                          TEXT,
    md5                             TEXT,
    filename                        TEXT,
    file_format                     TEXT,
    compression_format              TEXT,
    data_type                       TEXT,
    assay_type                      TEXT,
    analysis_type                   TEXT,
    mime_type                       TEXT,
    bundle_collection_id_namespace  TEXT,
    bundle_collection_local_id      TEXT,
    dbgap_study_id                  TEXT,
    dcc_id                          TEXT,
    submission_date                 DATE,
    fetched_at                      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id_namespace, local_id)
);
CREATE INDEX IF NOT EXISTS c2m2_file_dcc_idx ON c2m2.file (dcc_id);
CREATE INDEX IF NOT EXISTS c2m2_file_file_format_idx ON c2m2.file (file_format) WHERE file_format IS NOT NULL;
CREATE INDEX IF NOT EXISTS c2m2_file_assay_type_idx ON c2m2.file (assay_type) WHERE assay_type IS NOT NULL;
CREATE INDEX IF NOT EXISTS c2m2_file_data_type_idx ON c2m2.file (data_type) WHERE data_type IS NOT NULL;
CREATE INDEX IF NOT EXISTS c2m2_file_project_idx ON c2m2.file (project_id_namespace, project_local_id);

COMMENT ON TABLE c2m2.file IS
    'Every file the DCC has registered with CFDE, from C2M2 file.tsv. '
    'Sum of size_in_bytes across all rows is the program''s on-disk footprint. '
    'assay_type / data_type / file_format are CURIE strings; resolve via c2m2.assay_type / data_type / file_format lookups.';
COMMENT ON COLUMN c2m2.file.id_namespace IS 'C2M2 namespace; part of PK.';
COMMENT ON COLUMN c2m2.file.local_id IS 'File id local to its namespace; part of PK.';
COMMENT ON COLUMN c2m2.file.persistent_id IS 'Globally stable id (e.g. UUID, DOI, URN).';
COMMENT ON COLUMN c2m2.file.size_in_bytes IS 'Compressed file size as registered.';
COMMENT ON COLUMN c2m2.file.uncompressed_size_in_bytes IS 'Uncompressed file size; NULL when not applicable.';
COMMENT ON COLUMN c2m2.file.file_format IS 'C2M2 file_format CURIE; join to c2m2.file_format.id for the human name.';
COMMENT ON COLUMN c2m2.file.assay_type IS 'OBI CURIE for the assay; join to c2m2.assay_type.id for the human name.';

CREATE TABLE IF NOT EXISTS c2m2.biosample (
    id_namespace         TEXT NOT NULL,
    local_id             TEXT NOT NULL,
    project_id_namespace TEXT,
    project_local_id     TEXT,
    persistent_id        TEXT,
    creation_time        TIMESTAMPTZ,
    sample_prep_method   TEXT,
    anatomy              TEXT,
    dcc_id               TEXT,
    submission_date      DATE,
    fetched_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id_namespace, local_id)
);
CREATE INDEX IF NOT EXISTS c2m2_biosample_dcc_idx ON c2m2.biosample (dcc_id);
CREATE INDEX IF NOT EXISTS c2m2_biosample_anatomy_idx ON c2m2.biosample (anatomy) WHERE anatomy IS NOT NULL;

COMMENT ON TABLE c2m2.biosample IS
    'Per-biosample C2M2 records. anatomy is an Uberon CURIE; join c2m2.anatomy.id for label.';

CREATE TABLE IF NOT EXISTS c2m2.subject (
    id_namespace         TEXT NOT NULL,
    local_id             TEXT NOT NULL,
    project_id_namespace TEXT,
    project_local_id     TEXT,
    persistent_id        TEXT,
    creation_time        TIMESTAMPTZ,
    granularity          TEXT,
    sex                  TEXT,
    ethnicity            TEXT,
    age_at_enrollment    TEXT,
    dcc_id               TEXT,
    submission_date      DATE,
    fetched_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id_namespace, local_id)
);
CREATE INDEX IF NOT EXISTS c2m2_subject_dcc_idx ON c2m2.subject (dcc_id);

COMMENT ON TABLE c2m2.subject IS
    'Per-subject C2M2 records. sex/ethnicity/granularity are CURIE-encoded values '
    '(e.g. cfde_subject_sex:1 = female, cfde_subject_sex:2 = male). age_at_enrollment is free text '
    'because C2M2 allows ranges or unit suffixes.';

CREATE TABLE IF NOT EXISTS c2m2.collection (
    id_namespace          TEXT NOT NULL,
    local_id              TEXT NOT NULL,
    persistent_id         TEXT,
    creation_time         TIMESTAMPTZ,
    abbreviation          TEXT,
    name                  TEXT,
    description           TEXT,
    has_time_series_data  TEXT,
    dcc_id                TEXT,
    submission_date       DATE,
    fetched_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id_namespace, local_id)
);
CREATE INDEX IF NOT EXISTS c2m2_collection_dcc_idx ON c2m2.collection (dcc_id);

COMMENT ON TABLE c2m2.collection IS
    'C2M2 collections (cohorts / datasets) declared by each DCC.';

-- ----------------------------------------------------------------------------
-- Association tables (the "Knowledge Graph Assertions" on cfde.cloud)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS c2m2.file_in_collection (
    file_id_namespace        TEXT NOT NULL,
    file_local_id            TEXT NOT NULL,
    collection_id_namespace  TEXT NOT NULL,
    collection_local_id      TEXT NOT NULL,
    dcc_id                   TEXT,
    submission_date          DATE,
    PRIMARY KEY (file_id_namespace, file_local_id, collection_id_namespace, collection_local_id)
);

CREATE TABLE IF NOT EXISTS c2m2.biosample_in_collection (
    biosample_id_namespace   TEXT NOT NULL,
    biosample_local_id       TEXT NOT NULL,
    collection_id_namespace  TEXT NOT NULL,
    collection_local_id      TEXT NOT NULL,
    dcc_id                   TEXT,
    submission_date          DATE,
    PRIMARY KEY (biosample_id_namespace, biosample_local_id, collection_id_namespace, collection_local_id)
);

CREATE TABLE IF NOT EXISTS c2m2.subject_in_collection (
    subject_id_namespace     TEXT NOT NULL,
    subject_local_id         TEXT NOT NULL,
    collection_id_namespace  TEXT NOT NULL,
    collection_local_id      TEXT NOT NULL,
    dcc_id                   TEXT,
    submission_date          DATE,
    PRIMARY KEY (subject_id_namespace, subject_local_id, collection_id_namespace, collection_local_id)
);

CREATE TABLE IF NOT EXISTS c2m2.biosample_from_subject (
    biosample_id_namespace TEXT NOT NULL,
    biosample_local_id     TEXT NOT NULL,
    subject_id_namespace   TEXT NOT NULL,
    subject_local_id       TEXT NOT NULL,
    age_at_sampling        TEXT,
    dcc_id                 TEXT,
    submission_date        DATE,
    PRIMARY KEY (biosample_id_namespace, biosample_local_id, subject_id_namespace, subject_local_id)
);

CREATE TABLE IF NOT EXISTS c2m2.file_describes_biosample (
    file_id_namespace      TEXT NOT NULL,
    file_local_id          TEXT NOT NULL,
    biosample_id_namespace TEXT NOT NULL,
    biosample_local_id     TEXT NOT NULL,
    dcc_id                 TEXT,
    submission_date        DATE,
    PRIMARY KEY (file_id_namespace, file_local_id, biosample_id_namespace, biosample_local_id)
);

CREATE TABLE IF NOT EXISTS c2m2.file_describes_subject (
    file_id_namespace    TEXT NOT NULL,
    file_local_id        TEXT NOT NULL,
    subject_id_namespace TEXT NOT NULL,
    subject_local_id     TEXT NOT NULL,
    dcc_id               TEXT,
    submission_date      DATE,
    PRIMARY KEY (file_id_namespace, file_local_id, subject_id_namespace, subject_local_id)
);

CREATE TABLE IF NOT EXISTS c2m2.file_describes_collection (
    file_id_namespace       TEXT NOT NULL,
    file_local_id           TEXT NOT NULL,
    collection_id_namespace TEXT NOT NULL,
    collection_local_id     TEXT NOT NULL,
    dcc_id                  TEXT,
    submission_date         DATE,
    PRIMARY KEY (file_id_namespace, file_local_id, collection_id_namespace, collection_local_id)
);

CREATE TABLE IF NOT EXISTS c2m2.collection_in_collection (
    superset_collection_id_namespace TEXT NOT NULL,
    superset_collection_local_id     TEXT NOT NULL,
    subset_collection_id_namespace   TEXT NOT NULL,
    subset_collection_local_id       TEXT NOT NULL,
    dcc_id                           TEXT,
    submission_date                  DATE,
    PRIMARY KEY (superset_collection_id_namespace, superset_collection_local_id,
                 subset_collection_id_namespace, subset_collection_local_id)
);

CREATE TABLE IF NOT EXISTS c2m2.project_in_project (
    parent_project_id_namespace TEXT NOT NULL,
    parent_project_local_id     TEXT NOT NULL,
    child_project_id_namespace  TEXT NOT NULL,
    child_project_local_id      TEXT NOT NULL,
    dcc_id                      TEXT,
    submission_date             DATE,
    PRIMARY KEY (parent_project_id_namespace, parent_project_local_id,
                 child_project_id_namespace, child_project_local_id)
);

CREATE TABLE IF NOT EXISTS c2m2.collection_defined_by_project (
    collection_id_namespace TEXT NOT NULL,
    collection_local_id     TEXT NOT NULL,
    project_id_namespace    TEXT NOT NULL,
    project_local_id        TEXT NOT NULL,
    dcc_id                  TEXT,
    submission_date         DATE,
    PRIMARY KEY (collection_id_namespace, collection_local_id, project_id_namespace, project_local_id)
);

-- Ontology-linked association tables
CREATE TABLE IF NOT EXISTS c2m2.biosample_disease (
    biosample_id_namespace TEXT NOT NULL,
    biosample_local_id     TEXT NOT NULL,
    association_type       TEXT,
    disease                TEXT NOT NULL,
    dcc_id                 TEXT,
    submission_date        DATE,
    PRIMARY KEY (biosample_id_namespace, biosample_local_id, disease)
);

CREATE TABLE IF NOT EXISTS c2m2.biosample_gene (
    biosample_id_namespace TEXT NOT NULL,
    biosample_local_id     TEXT NOT NULL,
    gene                   TEXT NOT NULL,
    dcc_id                 TEXT,
    submission_date        DATE,
    PRIMARY KEY (biosample_id_namespace, biosample_local_id, gene)
);

CREATE TABLE IF NOT EXISTS c2m2.biosample_substance (
    biosample_id_namespace TEXT NOT NULL,
    biosample_local_id     TEXT NOT NULL,
    substance              TEXT NOT NULL,
    dcc_id                 TEXT,
    submission_date        DATE,
    PRIMARY KEY (biosample_id_namespace, biosample_local_id, substance)
);

CREATE TABLE IF NOT EXISTS c2m2.subject_disease (
    subject_id_namespace TEXT NOT NULL,
    subject_local_id     TEXT NOT NULL,
    association_type     TEXT,
    disease              TEXT NOT NULL,
    dcc_id               TEXT,
    submission_date      DATE,
    PRIMARY KEY (subject_id_namespace, subject_local_id, disease)
);

CREATE TABLE IF NOT EXISTS c2m2.subject_phenotype (
    subject_id_namespace TEXT NOT NULL,
    subject_local_id     TEXT NOT NULL,
    association_type     TEXT,
    phenotype            TEXT NOT NULL,
    dcc_id               TEXT,
    submission_date      DATE,
    PRIMARY KEY (subject_id_namespace, subject_local_id, phenotype)
);

CREATE TABLE IF NOT EXISTS c2m2.subject_race (
    subject_id_namespace TEXT NOT NULL,
    subject_local_id     TEXT NOT NULL,
    race                 TEXT NOT NULL,
    dcc_id               TEXT,
    submission_date      DATE,
    PRIMARY KEY (subject_id_namespace, subject_local_id, race)
);

CREATE TABLE IF NOT EXISTS c2m2.subject_role_taxonomy (
    subject_id_namespace TEXT NOT NULL,
    subject_local_id     TEXT NOT NULL,
    role_id              TEXT NOT NULL,
    taxonomy_id          TEXT NOT NULL,
    dcc_id               TEXT,
    submission_date      DATE,
    PRIMARY KEY (subject_id_namespace, subject_local_id, role_id, taxonomy_id)
);

CREATE TABLE IF NOT EXISTS c2m2.subject_substance (
    subject_id_namespace TEXT NOT NULL,
    subject_local_id     TEXT NOT NULL,
    substance            TEXT NOT NULL,
    dcc_id               TEXT,
    submission_date      DATE,
    PRIMARY KEY (subject_id_namespace, subject_local_id, substance)
);

CREATE TABLE IF NOT EXISTS c2m2.collection_anatomy (
    collection_id_namespace TEXT NOT NULL,
    collection_local_id     TEXT NOT NULL,
    anatomy                 TEXT NOT NULL,
    dcc_id                  TEXT,
    submission_date         DATE,
    PRIMARY KEY (collection_id_namespace, collection_local_id, anatomy)
);

CREATE TABLE IF NOT EXISTS c2m2.collection_compound (
    collection_id_namespace TEXT NOT NULL,
    collection_local_id     TEXT NOT NULL,
    compound                TEXT NOT NULL,
    dcc_id                  TEXT,
    submission_date         DATE,
    PRIMARY KEY (collection_id_namespace, collection_local_id, compound)
);

CREATE TABLE IF NOT EXISTS c2m2.collection_disease (
    collection_id_namespace TEXT NOT NULL,
    collection_local_id     TEXT NOT NULL,
    disease                 TEXT NOT NULL,
    dcc_id                  TEXT,
    submission_date         DATE,
    PRIMARY KEY (collection_id_namespace, collection_local_id, disease)
);

CREATE TABLE IF NOT EXISTS c2m2.collection_gene (
    collection_id_namespace TEXT NOT NULL,
    collection_local_id     TEXT NOT NULL,
    gene                    TEXT NOT NULL,
    dcc_id                  TEXT,
    submission_date         DATE,
    PRIMARY KEY (collection_id_namespace, collection_local_id, gene)
);

CREATE TABLE IF NOT EXISTS c2m2.collection_phenotype (
    collection_id_namespace TEXT NOT NULL,
    collection_local_id     TEXT NOT NULL,
    phenotype               TEXT NOT NULL,
    dcc_id                  TEXT,
    submission_date         DATE,
    PRIMARY KEY (collection_id_namespace, collection_local_id, phenotype)
);

CREATE TABLE IF NOT EXISTS c2m2.collection_protein (
    collection_id_namespace TEXT NOT NULL,
    collection_local_id     TEXT NOT NULL,
    protein                 TEXT NOT NULL,
    dcc_id                  TEXT,
    submission_date         DATE,
    PRIMARY KEY (collection_id_namespace, collection_local_id, protein)
);

CREATE TABLE IF NOT EXISTS c2m2.collection_substance (
    collection_id_namespace TEXT NOT NULL,
    collection_local_id     TEXT NOT NULL,
    substance               TEXT NOT NULL,
    dcc_id                  TEXT,
    submission_date         DATE,
    PRIMARY KEY (collection_id_namespace, collection_local_id, substance)
);

CREATE TABLE IF NOT EXISTS c2m2.collection_taxonomy (
    collection_id_namespace TEXT NOT NULL,
    collection_local_id     TEXT NOT NULL,
    taxon                   TEXT NOT NULL,
    dcc_id                  TEXT,
    submission_date         DATE,
    PRIMARY KEY (collection_id_namespace, collection_local_id, taxon)
);

CREATE TABLE IF NOT EXISTS c2m2.phenotype_disease (
    phenotype TEXT NOT NULL,
    disease   TEXT NOT NULL,
    dcc_id    TEXT,
    submission_date DATE,
    PRIMARY KEY (phenotype, disease)
);

CREATE TABLE IF NOT EXISTS c2m2.phenotype_gene (
    phenotype TEXT NOT NULL,
    gene      TEXT NOT NULL,
    dcc_id    TEXT,
    submission_date DATE,
    PRIMARY KEY (phenotype, gene)
);

CREATE TABLE IF NOT EXISTS c2m2.protein_gene (
    protein TEXT NOT NULL,
    gene    TEXT NOT NULL,
    dcc_id  TEXT,
    submission_date DATE,
    PRIMARY KEY (protein, gene)
);

-- ----------------------------------------------------------------------------
-- Ontology lookups (id, name, description, synonyms)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS c2m2.analysis_type        (id TEXT NOT NULL PRIMARY KEY, name TEXT, description TEXT, synonyms TEXT, dcc_id TEXT, submission_date DATE, fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE IF NOT EXISTS c2m2.anatomy              (id TEXT NOT NULL PRIMARY KEY, name TEXT, description TEXT, synonyms TEXT, dcc_id TEXT, submission_date DATE, fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE IF NOT EXISTS c2m2.assay_type           (id TEXT NOT NULL PRIMARY KEY, name TEXT, description TEXT, synonyms TEXT, dcc_id TEXT, submission_date DATE, fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE IF NOT EXISTS c2m2.biofluid             (id TEXT NOT NULL PRIMARY KEY, name TEXT, description TEXT, synonyms TEXT, dcc_id TEXT, submission_date DATE, fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE IF NOT EXISTS c2m2.compound             (id TEXT NOT NULL PRIMARY KEY, name TEXT, description TEXT, synonyms TEXT, dcc_id TEXT, submission_date DATE, fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE IF NOT EXISTS c2m2.data_type            (id TEXT NOT NULL PRIMARY KEY, name TEXT, description TEXT, synonyms TEXT, dcc_id TEXT, submission_date DATE, fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE IF NOT EXISTS c2m2.disease              (id TEXT NOT NULL PRIMARY KEY, name TEXT, description TEXT, synonyms TEXT, dcc_id TEXT, submission_date DATE, fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE IF NOT EXISTS c2m2.file_format          (id TEXT NOT NULL PRIMARY KEY, name TEXT, description TEXT, synonyms TEXT, dcc_id TEXT, submission_date DATE, fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE IF NOT EXISTS c2m2.gene                 (id TEXT NOT NULL PRIMARY KEY, name TEXT, description TEXT, synonyms TEXT, organism TEXT, dcc_id TEXT, submission_date DATE, fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE IF NOT EXISTS c2m2.ncbi_taxonomy        (id TEXT NOT NULL PRIMARY KEY, clade TEXT, name TEXT, description TEXT, synonyms TEXT, dcc_id TEXT, submission_date DATE, fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE IF NOT EXISTS c2m2.phenotype            (id TEXT NOT NULL PRIMARY KEY, name TEXT, description TEXT, synonyms TEXT, dcc_id TEXT, submission_date DATE, fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE IF NOT EXISTS c2m2.protein              (id TEXT NOT NULL PRIMARY KEY, name TEXT, description TEXT, synonyms TEXT, organism TEXT, dcc_id TEXT, submission_date DATE, fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE IF NOT EXISTS c2m2.sample_prep_method   (id TEXT NOT NULL PRIMARY KEY, name TEXT, description TEXT, synonyms TEXT, dcc_id TEXT, submission_date DATE, fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE IF NOT EXISTS c2m2.substance            (id TEXT NOT NULL PRIMARY KEY, name TEXT, description TEXT, synonyms TEXT, compound TEXT, dcc_id TEXT, submission_date DATE, fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW());

COMMENT ON TABLE c2m2.anatomy IS 'Uberon-aligned anatomy ontology terms used across all C2M2 submissions. id is a CURIE (e.g. UBERON:0013756).';
COMMENT ON TABLE c2m2.assay_type IS 'OBI-aligned assay type ontology terms.';
COMMENT ON TABLE c2m2.disease IS 'MONDO/DOID disease ontology terms.';
COMMENT ON TABLE c2m2.gene IS 'Gene ontology entries; id is typically NCBI or HGNC CURIE.';
COMMENT ON TABLE c2m2.file_format IS 'File format ontology (EDAM-derived).';
COMMENT ON TABLE c2m2.ncbi_taxonomy IS 'NCBI Taxonomy nodes referenced by subjects + biosamples.';
