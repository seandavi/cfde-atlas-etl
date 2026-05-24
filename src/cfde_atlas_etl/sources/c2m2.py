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

# C2M2 TSV name -> Postgres column ordering (column names match the TSV header).
# Order matches the TSV exactly so COPY works without a header.
# `dcc_id` + `submission_date` are appended last as ETL-side metadata.

EntityKind = Literal["entity", "association", "ontology"]


@dataclass(frozen=True)
class C2M2Table:
    """Maps a C2M2 TSV file to its Postgres counterpart.

    `columns` is the Postgres column ordering used for COPY. `tsv_columns`, when
    different from `columns`, gives the TSV header name to read from for each
    position. Used for `dcc.tsv` where the TSV header is `id` but our Postgres
    column is `dcc_id`.
    """

    tsv_name: str
    table: str
    columns: tuple[str, ...]
    kind: EntityKind
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
    ),
    C2M2Table(
        "id_namespace", "c2m2.id_namespace", ("id", "abbreviation", "name", "description"), "entity"
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
    ),
    # --- Association tables ---
    C2M2Table(
        "file_in_collection",
        "c2m2.file_in_collection",
        ("file_id_namespace", "file_local_id", "collection_id_namespace", "collection_local_id"),
        "association",
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
    ),
    C2M2Table(
        "file_describes_biosample",
        "c2m2.file_describes_biosample",
        ("file_id_namespace", "file_local_id", "biosample_id_namespace", "biosample_local_id"),
        "association",
    ),
    C2M2Table(
        "file_describes_subject",
        "c2m2.file_describes_subject",
        ("file_id_namespace", "file_local_id", "subject_id_namespace", "subject_local_id"),
        "association",
    ),
    C2M2Table(
        "file_describes_collection",
        "c2m2.file_describes_collection",
        ("file_id_namespace", "file_local_id", "collection_id_namespace", "collection_local_id"),
        "association",
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
    ),
    C2M2Table(
        "biosample_disease",
        "c2m2.biosample_disease",
        ("biosample_id_namespace", "biosample_local_id", "association_type", "disease"),
        "association",
    ),
    C2M2Table(
        "biosample_gene",
        "c2m2.biosample_gene",
        ("biosample_id_namespace", "biosample_local_id", "gene"),
        "association",
    ),
    C2M2Table(
        "biosample_substance",
        "c2m2.biosample_substance",
        ("biosample_id_namespace", "biosample_local_id", "substance"),
        "association",
    ),
    C2M2Table(
        "subject_disease",
        "c2m2.subject_disease",
        ("subject_id_namespace", "subject_local_id", "association_type", "disease"),
        "association",
    ),
    C2M2Table(
        "subject_phenotype",
        "c2m2.subject_phenotype",
        ("subject_id_namespace", "subject_local_id", "association_type", "phenotype"),
        "association",
    ),
    C2M2Table(
        "subject_race",
        "c2m2.subject_race",
        ("subject_id_namespace", "subject_local_id", "race"),
        "association",
    ),
    C2M2Table(
        "subject_role_taxonomy",
        "c2m2.subject_role_taxonomy",
        ("subject_id_namespace", "subject_local_id", "role_id", "taxonomy_id"),
        "association",
    ),
    C2M2Table(
        "subject_substance",
        "c2m2.subject_substance",
        ("subject_id_namespace", "subject_local_id", "substance"),
        "association",
    ),
    C2M2Table(
        "collection_anatomy",
        "c2m2.collection_anatomy",
        ("collection_id_namespace", "collection_local_id", "anatomy"),
        "association",
    ),
    C2M2Table(
        "collection_compound",
        "c2m2.collection_compound",
        ("collection_id_namespace", "collection_local_id", "compound"),
        "association",
    ),
    C2M2Table(
        "collection_disease",
        "c2m2.collection_disease",
        ("collection_id_namespace", "collection_local_id", "disease"),
        "association",
    ),
    C2M2Table(
        "collection_gene",
        "c2m2.collection_gene",
        ("collection_id_namespace", "collection_local_id", "gene"),
        "association",
    ),
    C2M2Table(
        "collection_phenotype",
        "c2m2.collection_phenotype",
        ("collection_id_namespace", "collection_local_id", "phenotype"),
        "association",
    ),
    C2M2Table(
        "collection_protein",
        "c2m2.collection_protein",
        ("collection_id_namespace", "collection_local_id", "protein"),
        "association",
    ),
    C2M2Table(
        "collection_substance",
        "c2m2.collection_substance",
        ("collection_id_namespace", "collection_local_id", "substance"),
        "association",
    ),
    C2M2Table(
        "collection_taxonomy",
        "c2m2.collection_taxonomy",
        ("collection_id_namespace", "collection_local_id", "taxon"),
        "association",
    ),
    C2M2Table(
        "phenotype_disease", "c2m2.phenotype_disease", ("phenotype", "disease"), "association"
    ),
    C2M2Table("phenotype_gene", "c2m2.phenotype_gene", ("phenotype", "gene"), "association"),
    C2M2Table("protein_gene", "c2m2.protein_gene", ("protein", "gene"), "association"),
    # --- Ontology lookups ---
    C2M2Table(
        "analysis_type", "c2m2.analysis_type", ("id", "name", "description", "synonyms"), "ontology"
    ),
    C2M2Table("anatomy", "c2m2.anatomy", ("id", "name", "description", "synonyms"), "ontology"),
    C2M2Table(
        "assay_type", "c2m2.assay_type", ("id", "name", "description", "synonyms"), "ontology"
    ),
    C2M2Table("biofluid", "c2m2.biofluid", ("id", "name", "description", "synonyms"), "ontology"),
    C2M2Table("compound", "c2m2.compound", ("id", "name", "description", "synonyms"), "ontology"),
    C2M2Table("data_type", "c2m2.data_type", ("id", "name", "description", "synonyms"), "ontology"),
    C2M2Table("disease", "c2m2.disease", ("id", "name", "description", "synonyms"), "ontology"),
    C2M2Table(
        "file_format", "c2m2.file_format", ("id", "name", "description", "synonyms"), "ontology"
    ),
    C2M2Table(
        "gene", "c2m2.gene", ("id", "name", "description", "synonyms", "organism"), "ontology"
    ),
    C2M2Table(
        "ncbi_taxonomy",
        "c2m2.ncbi_taxonomy",
        ("id", "clade", "name", "description", "synonyms"),
        "ontology",
    ),
    C2M2Table("phenotype", "c2m2.phenotype", ("id", "name", "description", "synonyms"), "ontology"),
    C2M2Table(
        "protein", "c2m2.protein", ("id", "name", "description", "synonyms", "organism"), "ontology"
    ),
    C2M2Table(
        "sample_prep_method",
        "c2m2.sample_prep_method",
        ("id", "name", "description", "synonyms"),
        "ontology",
    ),
    C2M2Table(
        "substance",
        "c2m2.substance",
        ("id", "name", "description", "synonyms", "compound"),
        "ontology",
    ),
)

C2M2_TABLES_BY_TSV: dict[str, C2M2Table] = {t.tsv_name: t for t in C2M2_TABLES}


SUBMISSION_DATE_RE = re.compile(r"/C2M2/(\d{4}-\d{2}-\d{2})/")


def parse_submission_date_from_url(url: str) -> str | None:
    """Extract YYYY-MM-DD from a cfde-drc S3 zip URL path. Returns None when absent."""
    m = SUBMISSION_DATE_RE.search(url)
    return m.group(1) if m else None


async def download_bundle(url: str, *, client: httpx.AsyncClient) -> tuple[bytes, str]:
    """Download a C2M2 zip; return (bytes, sha256). Streams into memory.

    Caller is responsible for bounding concurrency given GTEx's ~9 GB zip.
    """
    response = await client.get(url)
    response.raise_for_status()
    content = response.content
    sha = hashlib.sha256(content).hexdigest()
    return content, sha


def open_bundle(content: bytes) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(content))


def iter_bundle_rows(zf: zipfile.ZipFile, table: C2M2Table) -> Iterable[tuple[str | None, ...]]:
    """Yield rows from a single C2M2 TSV inside the zip.

    Returns tuples shaped exactly like `table.columns`. Missing files are silently
    skipped (some smaller DCC submissions omit empty tables). Empty-string values
    become None so Postgres `INTEGER`/`DATE` columns accept them.
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


def slug_from_url(url: str) -> str:
    """For debugging / temp-file names."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", url.rsplit("/", 1)[-1])


def temp_bundle_path(tmpdir: Path, url: str) -> Path:
    return tmpdir / slug_from_url(url)


__all__ = [
    "C2M2_TABLES",
    "C2M2_TABLES_BY_TSV",
    "C2M2Table",
    "download_bundle",
    "iter_bundle_rows",
    "open_bundle",
    "parse_submission_date_from_url",
    "slug_from_url",
    "temp_bundle_path",
]
