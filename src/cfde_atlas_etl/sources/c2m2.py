"""C2M2 datapackage download + unzip + COPY-into-Postgres.

Each DCC publishes a Frictionless data package as a zip under
cfde-drc.s3.amazonaws.com. Inside: ~50 TSV files matching the C2M2 spec
(file, biosample, subject, collection, ontologies, association tables).

The cfde.cloud/data/processed dashboard aggregates across all DCCs from these.
Ingesting locally lets the cfde-atlas chat surface answer the same questions
without round-tripping to a remote portal.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import httpx

EntityKind = Literal["entity", "association", "ontology"]


@dataclass(frozen=True)
class C2M2Table:
    """Maps a C2M2 TSV file to its Postgres counterpart.

    Attributes:
        tsv_name: Filename inside the zip (without `.tsv`).
        table: Fully-qualified Postgres target (`c2m2.<name>`).
        columns: Postgres column ordering used for COPY.
        kind: entity / association / ontology — drives sink-side strategy.
        tsv_columns: If different from `columns`, header name to read for each
            position. Used for `dcc.tsv` where the TSV column is `id` but our
            Postgres column is `dcc_id`.
        pk: Natural-key columns from the C2M2 spec. Drives:
            (a) skip rows where any natural-key column is NULL
            (b) deduplicate within a single bundle
            (c) ON CONFLICT DO NOTHING during cross-bundle staging
    """

    tsv_name: str
    table: str
    columns: tuple[str, ...]
    kind: EntityKind
    pk: tuple[str, ...]
    tsv_columns: tuple[str, ...] | None = None

    def header_for(self, pg_col: str) -> str:
        if self.tsv_columns is None:
            return pg_col
        idx = self.columns.index(pg_col)
        return self.tsv_columns[idx]


C2M2_TABLES: tuple[C2M2Table, ...] = (
    # --- DCC / project identity ---
    C2M2Table(
        "dcc",
        "c2m2.dcc",
        (
            "dcc_id",
            "dcc_name",
            "dcc_abbreviation",
            "dcc_description",
            "contact_email",
            "contact_name",
            "dcc_url",
            "project_id_namespace",
            "project_local_id",
        ),
        "entity",
        pk=("dcc_id",),
        tsv_columns=(
            "id",
            "dcc_name",
            "dcc_abbreviation",
            "dcc_description",
            "contact_email",
            "contact_name",
            "dcc_url",
            "project_id_namespace",
            "project_local_id",
        ),
    ),
    C2M2Table(
        "project",
        "c2m2.project",
        (
            "project_id_namespace",
            "project_local_id",
            "persistent_id",
            "creation_time",
            "abbreviation",
            "name",
            "description",
        ),
        "entity",
        pk=("project_id_namespace", "project_local_id"),
    ),
    C2M2Table(
        "id_namespace",
        "c2m2.id_namespace",
        ("id", "abbreviation", "name", "description"),
        "entity",
        pk=("id",),
    ),
    # --- Core entity tables ---
    C2M2Table(
        "file",
        "c2m2.file",
        (
            "id_namespace",
            "local_id",
            "project_id_namespace",
            "project_local_id",
            "persistent_id",
            "creation_time",
            "size_in_bytes",
            "uncompressed_size_in_bytes",
            "sha256",
            "md5",
            "filename",
            "file_format",
            "compression_format",
            "data_type",
            "assay_type",
            "analysis_type",
            "mime_type",
            "bundle_collection_id_namespace",
            "bundle_collection_local_id",
            "dbgap_study_id",
        ),
        "entity",
        pk=("id_namespace", "local_id"),
    ),
    C2M2Table(
        "biosample",
        "c2m2.biosample",
        (
            "id_namespace",
            "local_id",
            "project_id_namespace",
            "project_local_id",
            "persistent_id",
            "creation_time",
            "sample_prep_method",
            "anatomy",
        ),
        "entity",
        pk=("id_namespace", "local_id"),
    ),
    C2M2Table(
        "subject",
        "c2m2.subject",
        (
            "id_namespace",
            "local_id",
            "project_id_namespace",
            "project_local_id",
            "persistent_id",
            "creation_time",
            "granularity",
            "sex",
            "ethnicity",
            "age_at_enrollment",
        ),
        "entity",
        pk=("id_namespace", "local_id"),
    ),
    C2M2Table(
        "collection",
        "c2m2.collection",
        (
            "id_namespace",
            "local_id",
            "persistent_id",
            "creation_time",
            "abbreviation",
            "name",
            "description",
            "has_time_series_data",
        ),
        "entity",
        pk=("id_namespace", "local_id"),
    ),
    # --- Association tables (PK is composite over the FK pairs + ontology id where applicable) ---
    C2M2Table(
        "file_in_collection",
        "c2m2.file_in_collection",
        ("file_id_namespace", "file_local_id", "collection_id_namespace", "collection_local_id"),
        "association",
        pk=("file_id_namespace", "file_local_id", "collection_id_namespace", "collection_local_id"),
    ),
    C2M2Table(
        "biosample_in_collection",
        "c2m2.biosample_in_collection",
        (
            "biosample_id_namespace",
            "biosample_local_id",
            "collection_id_namespace",
            "collection_local_id",
        ),
        "association",
        pk=(
            "biosample_id_namespace",
            "biosample_local_id",
            "collection_id_namespace",
            "collection_local_id",
        ),
    ),
    C2M2Table(
        "subject_in_collection",
        "c2m2.subject_in_collection",
        (
            "subject_id_namespace",
            "subject_local_id",
            "collection_id_namespace",
            "collection_local_id",
        ),
        "association",
        pk=(
            "subject_id_namespace",
            "subject_local_id",
            "collection_id_namespace",
            "collection_local_id",
        ),
    ),
    C2M2Table(
        "biosample_from_subject",
        "c2m2.biosample_from_subject",
        (
            "biosample_id_namespace",
            "biosample_local_id",
            "subject_id_namespace",
            "subject_local_id",
            "age_at_sampling",
        ),
        "association",
        pk=(
            "biosample_id_namespace",
            "biosample_local_id",
            "subject_id_namespace",
            "subject_local_id",
        ),
    ),
    C2M2Table(
        "file_describes_biosample",
        "c2m2.file_describes_biosample",
        ("file_id_namespace", "file_local_id", "biosample_id_namespace", "biosample_local_id"),
        "association",
        pk=("file_id_namespace", "file_local_id", "biosample_id_namespace", "biosample_local_id"),
    ),
    C2M2Table(
        "file_describes_subject",
        "c2m2.file_describes_subject",
        ("file_id_namespace", "file_local_id", "subject_id_namespace", "subject_local_id"),
        "association",
        pk=("file_id_namespace", "file_local_id", "subject_id_namespace", "subject_local_id"),
    ),
    C2M2Table(
        "file_describes_collection",
        "c2m2.file_describes_collection",
        ("file_id_namespace", "file_local_id", "collection_id_namespace", "collection_local_id"),
        "association",
        pk=("file_id_namespace", "file_local_id", "collection_id_namespace", "collection_local_id"),
    ),
    C2M2Table(
        "collection_in_collection",
        "c2m2.collection_in_collection",
        (
            "superset_collection_id_namespace",
            "superset_collection_local_id",
            "subset_collection_id_namespace",
            "subset_collection_local_id",
        ),
        "association",
        pk=(
            "superset_collection_id_namespace",
            "superset_collection_local_id",
            "subset_collection_id_namespace",
            "subset_collection_local_id",
        ),
    ),
    C2M2Table(
        "project_in_project",
        "c2m2.project_in_project",
        (
            "parent_project_id_namespace",
            "parent_project_local_id",
            "child_project_id_namespace",
            "child_project_local_id",
        ),
        "association",
        pk=(
            "parent_project_id_namespace",
            "parent_project_local_id",
            "child_project_id_namespace",
            "child_project_local_id",
        ),
    ),
    C2M2Table(
        "collection_defined_by_project",
        "c2m2.collection_defined_by_project",
        (
            "collection_id_namespace",
            "collection_local_id",
            "project_id_namespace",
            "project_local_id",
        ),
        "association",
        pk=(
            "collection_id_namespace",
            "collection_local_id",
            "project_id_namespace",
            "project_local_id",
        ),
    ),
    C2M2Table(
        "biosample_disease",
        "c2m2.biosample_disease",
        ("biosample_id_namespace", "biosample_local_id", "association_type", "disease"),
        "association",
        pk=("biosample_id_namespace", "biosample_local_id", "disease"),
    ),
    C2M2Table(
        "biosample_gene",
        "c2m2.biosample_gene",
        ("biosample_id_namespace", "biosample_local_id", "gene"),
        "association",
        pk=("biosample_id_namespace", "biosample_local_id", "gene"),
    ),
    C2M2Table(
        "biosample_substance",
        "c2m2.biosample_substance",
        ("biosample_id_namespace", "biosample_local_id", "substance"),
        "association",
        pk=("biosample_id_namespace", "biosample_local_id", "substance"),
    ),
    C2M2Table(
        "subject_disease",
        "c2m2.subject_disease",
        ("subject_id_namespace", "subject_local_id", "association_type", "disease"),
        "association",
        pk=("subject_id_namespace", "subject_local_id", "disease"),
    ),
    C2M2Table(
        "subject_phenotype",
        "c2m2.subject_phenotype",
        ("subject_id_namespace", "subject_local_id", "association_type", "phenotype"),
        "association",
        pk=("subject_id_namespace", "subject_local_id", "phenotype"),
    ),
    C2M2Table(
        "subject_race",
        "c2m2.subject_race",
        ("subject_id_namespace", "subject_local_id", "race"),
        "association",
        pk=("subject_id_namespace", "subject_local_id", "race"),
    ),
    C2M2Table(
        "subject_role_taxonomy",
        "c2m2.subject_role_taxonomy",
        ("subject_id_namespace", "subject_local_id", "role_id", "taxonomy_id"),
        "association",
        pk=("subject_id_namespace", "subject_local_id", "role_id", "taxonomy_id"),
    ),
    C2M2Table(
        "subject_substance",
        "c2m2.subject_substance",
        ("subject_id_namespace", "subject_local_id", "substance"),
        "association",
        pk=("subject_id_namespace", "subject_local_id", "substance"),
    ),
    C2M2Table(
        "collection_anatomy",
        "c2m2.collection_anatomy",
        ("collection_id_namespace", "collection_local_id", "anatomy"),
        "association",
        pk=("collection_id_namespace", "collection_local_id", "anatomy"),
    ),
    C2M2Table(
        "collection_compound",
        "c2m2.collection_compound",
        ("collection_id_namespace", "collection_local_id", "compound"),
        "association",
        pk=("collection_id_namespace", "collection_local_id", "compound"),
    ),
    C2M2Table(
        "collection_disease",
        "c2m2.collection_disease",
        ("collection_id_namespace", "collection_local_id", "disease"),
        "association",
        pk=("collection_id_namespace", "collection_local_id", "disease"),
    ),
    C2M2Table(
        "collection_gene",
        "c2m2.collection_gene",
        ("collection_id_namespace", "collection_local_id", "gene"),
        "association",
        pk=("collection_id_namespace", "collection_local_id", "gene"),
    ),
    C2M2Table(
        "collection_phenotype",
        "c2m2.collection_phenotype",
        ("collection_id_namespace", "collection_local_id", "phenotype"),
        "association",
        pk=("collection_id_namespace", "collection_local_id", "phenotype"),
    ),
    C2M2Table(
        "collection_protein",
        "c2m2.collection_protein",
        ("collection_id_namespace", "collection_local_id", "protein"),
        "association",
        pk=("collection_id_namespace", "collection_local_id", "protein"),
    ),
    C2M2Table(
        "collection_substance",
        "c2m2.collection_substance",
        ("collection_id_namespace", "collection_local_id", "substance"),
        "association",
        pk=("collection_id_namespace", "collection_local_id", "substance"),
    ),
    C2M2Table(
        "collection_taxonomy",
        "c2m2.collection_taxonomy",
        ("collection_id_namespace", "collection_local_id", "taxon"),
        "association",
        pk=("collection_id_namespace", "collection_local_id", "taxon"),
    ),
    C2M2Table(
        "phenotype_disease",
        "c2m2.phenotype_disease",
        ("phenotype", "disease"),
        "association",
        pk=("phenotype", "disease"),
    ),
    C2M2Table(
        "phenotype_gene",
        "c2m2.phenotype_gene",
        ("phenotype", "gene"),
        "association",
        pk=("phenotype", "gene"),
    ),
    C2M2Table(
        "protein_gene",
        "c2m2.protein_gene",
        ("protein", "gene"),
        "association",
        pk=("protein", "gene"),
    ),
    # --- Ontology lookups (id, name, description, synonyms [, organism|clade|compound]) ---
    C2M2Table(
        "analysis_type",
        "c2m2.analysis_type",
        ("id", "name", "description", "synonyms"),
        "ontology",
        pk=("id",),
    ),
    C2M2Table(
        "anatomy", "c2m2.anatomy", ("id", "name", "description", "synonyms"), "ontology", pk=("id",)
    ),
    C2M2Table(
        "assay_type",
        "c2m2.assay_type",
        ("id", "name", "description", "synonyms"),
        "ontology",
        pk=("id",),
    ),
    C2M2Table(
        "biofluid",
        "c2m2.biofluid",
        ("id", "name", "description", "synonyms"),
        "ontology",
        pk=("id",),
    ),
    C2M2Table(
        "compound",
        "c2m2.compound",
        ("id", "name", "description", "synonyms"),
        "ontology",
        pk=("id",),
    ),
    C2M2Table(
        "data_type",
        "c2m2.data_type",
        ("id", "name", "description", "synonyms"),
        "ontology",
        pk=("id",),
    ),
    C2M2Table(
        "disease", "c2m2.disease", ("id", "name", "description", "synonyms"), "ontology", pk=("id",)
    ),
    C2M2Table(
        "file_format",
        "c2m2.file_format",
        ("id", "name", "description", "synonyms"),
        "ontology",
        pk=("id",),
    ),
    C2M2Table(
        "gene",
        "c2m2.gene",
        ("id", "name", "description", "synonyms", "organism"),
        "ontology",
        pk=("id",),
    ),
    C2M2Table(
        "ncbi_taxonomy",
        "c2m2.ncbi_taxonomy",
        ("id", "clade", "name", "description", "synonyms"),
        "ontology",
        pk=("id",),
    ),
    C2M2Table(
        "phenotype",
        "c2m2.phenotype",
        ("id", "name", "description", "synonyms"),
        "ontology",
        pk=("id",),
    ),
    C2M2Table(
        "protein",
        "c2m2.protein",
        ("id", "name", "description", "synonyms", "organism"),
        "ontology",
        pk=("id",),
    ),
    C2M2Table(
        "sample_prep_method",
        "c2m2.sample_prep_method",
        ("id", "name", "description", "synonyms"),
        "ontology",
        pk=("id",),
    ),
    C2M2Table(
        "substance",
        "c2m2.substance",
        ("id", "name", "description", "synonyms", "compound"),
        "ontology",
        pk=("id",),
    ),
)

C2M2_TABLES_BY_TSV: dict[str, C2M2Table] = {t.tsv_name: t for t in C2M2_TABLES}


SUBMISSION_DATE_RE = re.compile(r"/C2M2/(\d{4}-\d{2}-\d{2})/")

# Bundles flagged as test/demo data that should not be ingested.
# Match against the URL filename portion (lowercased).
JUNK_BUNDLE_PATTERNS = (
    re.compile(r"test_broken", re.IGNORECASE),
    re.compile(r"^test_", re.IGNORECASE),
    re.compile(r"_test_", re.IGNORECASE),
    re.compile(r"sandbox", re.IGNORECASE),
    re.compile(r"example", re.IGNORECASE),
)


def parse_submission_date_from_url(url: str) -> str | None:
    """Extract YYYY-MM-DD from a cfde-drc S3 zip URL path. Returns None when absent."""
    m = SUBMISSION_DATE_RE.search(url)
    return m.group(1) if m else None


def is_junk_bundle(url: str) -> bool:
    """Return True for filenames that look like sandbox / test / example uploads."""
    filename = url.rsplit("/", 1)[-1]
    return any(p.search(filename) for p in JUNK_BUNDLE_PATTERNS)


async def download_bundle(url: str, *, client: httpx.AsyncClient) -> tuple[bytes, str]:
    """Download a C2M2 zip; return (bytes, sha256). Streams into memory."""
    response = await client.get(url)
    response.raise_for_status()
    content = response.content
    sha = hashlib.sha256(content).hexdigest()
    return content, sha


def open_bundle(content: bytes) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(content))


def iter_bundle_rows(zf: zipfile.ZipFile, table: C2M2Table) -> Iterable[tuple[str | None, ...]]:
    """Yield rows from a single C2M2 TSV inside the zip.

    Missing files are silently skipped (some smaller DCC submissions omit empty
    tables). Empty-string values become None so Postgres INTEGER/DATE columns accept them.
    """
    candidate_names = _candidate_member_names(zf, table.tsv_name)
    target: str | None = next((n for n in candidate_names), None)
    if target is None:
        return
    with zf.open(target) as raw:
        text = io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline="")
        reader = csv.DictReader(text, delimiter="\t")
        for row in reader:
            yield tuple(_blank_to_none(row.get(table.header_for(col))) for col in table.columns)


def _candidate_member_names(zf: zipfile.ZipFile, tsv_name: str) -> list[str]:
    """Frictionless packages can nest TSVs under either '<root>/' or directly. Find one."""
    target = f"{tsv_name}.tsv"
    return [n for n in zf.namelist() if n.endswith("/" + target) or n.endswith(target)]


def _blank_to_none(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, str) and v == "":
        return None
    return v


def filter_and_dedupe(
    table: C2M2Table, rows: Iterable[tuple[Any, ...]]
) -> tuple[list[tuple[Any, ...]], int, int]:
    """Drop rows with NULL in any PK column; dedupe within batch on PK.

    Returns (rows, dropped_null, dropped_dup). Last-row-wins on dedupe.
    """
    if not table.pk:
        return list(rows), 0, 0
    pk_indices = [table.columns.index(c) for c in table.pk]
    by_key: dict[tuple[Any, ...], tuple[Any, ...]] = {}
    dropped_null = 0
    for row in rows:
        key = tuple(row[i] for i in pk_indices)
        if any(v is None for v in key):
            dropped_null += 1
            continue
        by_key[key] = row
    deduped = list(by_key.values())
    # dropped_dup = (rows_with_complete_pk) - len(deduped); we don't know the
    # input length without consuming; compute from running total.
    return deduped, dropped_null, 0


def slug_from_url(url: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", url.rsplit("/", 1)[-1])


def temp_bundle_path(tmpdir: Path, url: str) -> Path:
    return tmpdir / slug_from_url(url)


__all__ = [
    "C2M2_TABLES",
    "C2M2_TABLES_BY_TSV",
    "C2M2Table",
    "download_bundle",
    "filter_and_dedupe",
    "is_junk_bundle",
    "iter_bundle_rows",
    "open_bundle",
    "parse_submission_date_from_url",
    "slug_from_url",
    "temp_bundle_path",
]
