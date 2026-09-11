# cfde-atlas-etl

Prefect/Python ETL for the CFDE evaluation data surface. Lands data from upstream sources into Postgres so the [`cfde-atlas`](https://github.com/seandavi/cfde-atlas) chat UI can query it directly.

## What this is

The data side of cfde-atlas. The chat app introspects Postgres at request time via `list_tables` / `describe_table` / `run_query`; this repo is what fills that database.

Architectural decisions live in [`seandavi/cfde-atlas#15`](https://github.com/seandavi/cfde-atlas/issues/15). Decisions that belong here rather than there:

- **ELT, not ETL.** Sources land in `raw.*` as `jsonb` exactly as fetched; transformation is a `analytics.*` SQL view layer keyed on stable typed columns.
- **Per-column comments in the analytics views are part of the contract.** They drive `describe_table` in cfde-atlas, which is what the LLM reads.
- **Migrations are plain SQL files in `migrations/`** for now. Alembic init is filed as [#1](https://github.com/seandavi/cfde-atlas-etl/issues/1).

## Layout

```
config.yaml                       — PR-curated FOAs + manual core projects (single source of truth)
migrations/                       — numbered SQL migrations, applied with psql for now
src/cfde_atlas_etl/
  curated.py                      — loader for config.yaml
  flows/                          — Prefect flow entrypoints, one per source
  sources/                        — async fetchers (RePORTER, iCite, Entrez, GA, GitHub, DRC, …)
  models/                         — pydantic source-schema guards
  sinks/                          — Postgres upserts into raw.* tables
```

## `config.yaml`

The set of CFDE FOAs (RFA / NOT / OTA) and any orphan core projects not reachable via those FOAs is **curated by PR**, not scraped. See [#33](https://github.com/seandavi/cfde-atlas-etl/issues/33) for the decision record.

To add a new FOA or core project, edit `config.yaml` and open a PR. The diff is the audit trail.

## Current flows

| Flow | Source | Target |
|---|---|---|
| `flows.opportunities` | PR-curated `config.yaml` (`opportunities:`) | `raw.opportunities` → `analytics.opportunities` |
| `flows.projects` | NIH RePORTER `/v2/projects/search` (opportunities from `raw.opportunities` + manual `core_projects:` from `config.yaml`) | `raw.reporter_projects` → `analytics.projects` + `analytics.core_projects` |
| `flows.publications` | NIH RePORTER `/v2/publications/search` + iCite `/api/pubs` | `raw.reporter_publications` + `raw.icite` → `analytics.publications` |
| `flows.journals` | Scimago journal rank CSV + NCBI Entrez esummary | `raw.scimago_ranks` + `raw.entrez_journals` → `analytics.journals` |
| `flows.citing_publications` | iCite cited_by + per-citing-pmid iCite lookup | `raw.icite_citations` + `raw.icite_citing_pubs` → `analytics.citing_publications` |
| `flows.citing_grants` | RePORTER `/v2/publications/search?pmids=...` for citing pmids | `raw.reporter_citing_publications` → `analytics.citing_grants` + `analytics.citing_grants_rollup` |
| `flows.citing_grant_details` | RePORTER `/v2/projects/search?project_nums=...` for downstream cores | `raw.reporter_citing_projects` → `analytics.citing_grant_details` + `analytics.citing_grants_full` + `analytics.citing_funding_by_*` |
| `flows.drc` | `cfde-drc.s3.amazonaws.com` TSV manifests (dcc/file/code) | `raw.drc_*` → `analytics.drc_*` + `analytics.drc_assets` |
| `flows.c2m2` | Latest C2M2 datapackage per DCC (from raw.drc_file); unzip + COPY each TSV; idempotent via `raw.c2m2_bundles` ledger | `c2m2.*` (50 tables) → `analytics.c2m2_summary` + `analytics.c2m2_file_format_mix` + `analytics.c2m2_assay_coverage` + `analytics.c2m2_anatomy_coverage` + `analytics.c2m2_disease_coverage` + `analytics.c2m2_subject_demographics` |
| `flows.github` | GitHub REST search + per-repo detail (needs `GITHUB_TOKEN`) | `raw.github_*` → `analytics.github_repos` + `analytics.github_activity_weekly` + `analytics.github_contributors` |
| `flows.ga` | GA4 Data API runReport per curated property (needs `GOOGLE_APPLICATION_CREDENTIALS`) | `raw.ga_properties` + `raw.ga_reports` → `analytics.ga_pageviews` + `analytics.ga_top_pages` + `analytics.ga_geo` + `analytics.ga_traffic_sources` + `analytics.ga_property_coverage` |
| `flows.load_all` | Orchestrates everything above in dep order with safe per-flow isolation | — |

The publications source acknowledges multiple grants per paper, so the raw key in `raw.reporter_publications` is `(pmid, core_project_number)`. The analytics view JOINs `raw.icite` onto it for title/journal/RCR/citation enrichment.

## Setup

Requires `uv`, `psql`, and a reachable Postgres.

```bash
uv sync --extra dev
cp .env.example .env   # then fill in DATABASE_URL
for f in migrations/*.sql; do psql "$DATABASE_URL" -f "$f"; done
```

For the onclappc02 dev environment, the password lives in GSM (project `cdsci-infra`, secret `cfde-atlas-dev-db-password-onclappc02`) — see `.env.example` for the snippet.

## Dataset Stats

<!-- BEGIN STATS -->
*Auto-generated from `analytics.data_inventory` at 2026-09-10 22:48 UTC. Edit `config.yaml` + re-run `flows.load_all` to update.*

### Opportunities, Projects, Publications

| Object | Rows | Data Refreshed | Description |
|---|---:|---|---|
| `analytics.publications` | 505 | 2026-09-10 21:12 UTC | Grant-acknowledging publications, one row per (pmid, core_project_number). A paper acknowledging multiple grants yields one row per grant. Join key to grants… |
| `analytics.journals` | 196 | 2026-09-10 21:20 UTC | Journal metadata keyed on NLM abbreviation. Use to resolve analytics.publications.journal to a full name and Scimago Journal Rank. |
| `analytics.projects` | 178 | 2026-09-10 21:12 UTC | One row per NIH RePORTER project_num. Multiple project_nums roll up into one core_project_number (see analytics.core_projects). Join key for publications, gi… |
| `analytics.core_projects` | 91 | 2026-09-10 21:12 UTC | One row per NIH core_project_number, rolled up from analytics.projects. Total award amount sums all project_nums (fiscal years + supplements) under the core. |
| `analytics.opportunities` | 17 | 2026-09-10 21:12 UTC | NIH Common Fund Data Ecosystem funding opportunity numbers. One row per opportunity. Used as a join key in analytics.projects.opportunity_number. |

### Forward Citations & Downstream Impact

| Object | Rows | Data Refreshed | Description |
|---|---:|---|---|
| `analytics.citing_grants_full` | 226,153 | 2026-09-10 21:18 UTC | Forward citations expanded to include downstream grant-side details (PI, institution, mechanism, award amount). One row per (cfde_pmid, citing_pmid, downstre… |
| `analytics.citing_grant_details` | 64,629 | 2026-09-10 21:18 UTC | Per-(downstream project_num) detail for grants that fund publications citing CFDE work. Use to surface PI, institution, mechanism, and award amount alongside… |
| `analytics.citing_grants` | 23,102 | 2026-09-10 21:13 UTC | For each CFDE pmid that gets cited, the downstream NIH grants the citing paper acknowledges. One row per (cfde_pmid, citing_pmid, downstream_core_project_num… |
| `analytics.citing_publications` | 11,551 | 2026-09-10 21:13 UTC | Forward citations of CFDE-funded papers. One row per (cfde_pmid, citing_pmid). Join to analytics.publications on cfde_pmid for the CFDE paper, or to analytic… |
| `analytics.citing_funding_by_institution` | 546 | 2026-09-10 21:18 UTC | Per downstream institution: count of citing grants + total award amount. Use to rank institutions whose work cites CFDE-funded outputs. |
| `analytics.citing_funding_by_mechanism` | 114 | 2026-09-10 21:18 UTC | Per NIH activity code (U54, R01, ...) among downstream citing grants. Use to see whether CFDE outputs feed primarily small-grant work, large U-mechanism cent… |
| `analytics.citing_funding_by_cfde_core` | 58 | 2026-09-10 21:18 UTC | Per CFDE core_project_number: counts of distinct downstream grants, institutions, PI strings, and a SUM of downstream award_amount (note: this sums per-fisca… |
| `analytics.citing_grants_rollup` | 58 | 2026-09-10 21:13 UTC | Per CFDE core project, counts of citing publications, distinct downstream NIH core_project_numbers, and distinct downstream institutions. Chat-friendly aggre… |

### DRC Asset Manifests

| Object | Rows | Data Refreshed | Description |
|---|---:|---|---|
| `analytics.drc_assets` | 1,044 | 2026-09-10 21:13 UTC | Union of analytics.drc_dcc_assets / drc_files / drc_code with an asset_kind discriminator. Use the per-kind views for typed columns; use this for "show me ev… |
| `analytics.drc_dcc_assets` | 522 | 2026-09-10 21:13 UTC | CFDE DRC dcc-level assets: linkout templates and DCC-specific resources. dcc_id is a DRC-side UUID; map to NIH core_project_number via a crosswalk (not yet p… |
| `analytics.drc_files` | 349 | 2026-09-10 21:13 UTC | CFDE DRC downloadable file assets (e.g. C2M2 datapackages). One row per URL. |
| `analytics.drc_code` | 173 | 2026-09-10 21:13 UTC | CFDE DRC code/API assets: APIs, smartAPI specs, JSON-LD endpoints, ETL scripts. |

### C2M2 (DCC Contents)

| Object | Rows | Data Refreshed | Description |
|---|---:|---|---|
| `c2m2.file` | 15,771,533 | — | Every file the DCC has registered with CFDE, from C2M2 file.tsv. Sum of size_in_bytes across all rows is the program's on-disk footprint. assay_type / data_t… |
| `c2m2.file_describes_collection` | 10,565,024 | — | — |
| `c2m2.file_describes_biosample` | 3,692,180 | — | — |
| `c2m2.file_describes_subject` | 2,236,737 | — | — |
| `c2m2.file_in_collection` | 706,046 | — | — |
| `c2m2.biosample` | 702,810 | — | Per-biosample C2M2 records. anatomy is an Uberon CURIE; join c2m2.anatomy.id for label. |
| `c2m2.collection_compound` | 687,321 | — | — |
| `c2m2.biosample_from_subject` | 684,097 | — | — |
| `c2m2.collection_defined_by_project` | 482,055 | — | — |
| `c2m2.collection` | 438,875 | — | C2M2 collections (cohorts / datasets) declared by each DCC. |
| `c2m2.collection_taxonomy` | 348,786 | — | — |
| `c2m2.collection_protein` | 311,087 | — | — |
| `c2m2.protein` | 198,007 | — | — |
| `c2m2.biosample_in_collection` | 154,629 | — | — |
| `c2m2.biosample_disease` | 151,603 | — | — |
| `c2m2.collection_anatomy` | 150,296 | — | — |
| `c2m2.subject_phenotype` | 146,958 | — | — |
| `c2m2.subject_role_taxonomy` | 66,585 | — | — |
| `c2m2.subject_disease` | 51,765 | — | — |
| `c2m2.subject` | 46,732 | — | Per-subject C2M2 records. sex/ethnicity/granularity are CURIE-encoded values (e.g. cfde_subject_sex:1 = female, cfde_subject_sex:2 = male). age_at_enrollment… |
| `c2m2.subject_in_collection` | 41,912 | — | — |
| `c2m2.collection_gene` | 37,774 | — | — |
| `c2m2.collection_in_collection` | 34,966 | — | — |
| `c2m2.subject_race` | 30,352 | — | — |
| `c2m2.phenotype_gene` | 26,458 | — | — |
| `c2m2.gene` | 5,407 | — | Gene ontology entries; id is typically NCBI or HGNC CURIE. |
| `c2m2.project_in_project` | 4,242 | — | — |
| `c2m2.ncbi_taxonomy` | 2,524 | — | NCBI Taxonomy nodes referenced by subjects + biosamples. |
| `analytics.c2m2_disease_coverage` | 2,145 | — | Per (DCC, disease) — biosample / subject / collection counts unioned across the three disease-association tables. Use to answer "which programs touch disease… |
| `c2m2.collection_disease` | 1,960 | — | — |
| `c2m2.disease` | 1,932 | — | MONDO/DOID disease ontology terms. |
| `c2m2.biosample_gene` | 1,420 | — | — |
| `c2m2.project` | 1,124 | — | DCC-side projects + sub-projects from C2M2 project.tsv. Hierarchy in c2m2.project_in_project. |
| `analytics.c2m2_anatomy_coverage` | 459 | — | Per (DCC, anatomy CURIE): number of biosamples. Uses Uberon ids. Cross-DCC anatomy overlap can be derived by self-joining on anatomy. |
| `c2m2.anatomy` | 327 | — | Uberon-aligned anatomy ontology terms used across all C2M2 submissions. id is a CURIE (e.g. UBERON:0013756). |
| `analytics.c2m2_subject_demographics` | 156 | — | Per (DCC, sex, ethnicity, race) subject counts. sex/ethnicity are CURIE-coded (e.g. cfde_subject_sex:1 = female). race comes from c2m2.subject_race. |
| `analytics.c2m2_file_format_mix` | 135 | — | Per (DCC, file_format): count of files + total bytes. file_format_name is the human label resolved via c2m2.file_format. Use to answer "what formats does eac… |
| `analytics.c2m2_assay_coverage` | 97 | — | Per (DCC, assay_type CURIE): number of files. Drives "which DCCs do scRNA-seq?" "which programs share assay X?" Filter with WHERE assay_type = 'OBI:0002762'. |
| `c2m2.assay_type` | 80 | — | OBI-aligned assay type ontology terms. |
| `c2m2.file_format` | 66 | — | File format ontology (EDAM-derived). |
| `c2m2.phenotype` | 55 | — | — |
| `c2m2.data_type` | 47 | — | — |
| `c2m2.id_namespace` | 28 | — | C2M2 identifier namespaces declared by each DCC submission. |
| `analytics.c2m2_summary` | 14 | 2026-09-10 22:36 UTC | One row per CFDE DCC with C2M2 entity counts + on-disk file footprint. Matches the top-level numbers on cfde.cloud/data/processed. submission_date is when th… |
| `c2m2.dcc` | 14 | — | CFDE DCC identity from C2M2 dcc.tsv. 16 rows. The canonical mapping between a C2M2 namespace (e.g. "gtex") and the human-readable program (GTEx). Use dcc_abb… |
| `c2m2.analysis_type` | 13 | — | — |
| `c2m2.biofluid` | 13 | — | — |
| `c2m2.sample_prep_method` | 6 | — | — |
| `c2m2.biosample_substance` | 4 | — | — |
| `c2m2.collection_phenotype` | 0 | — | — |
| `c2m2.collection_substance` | 0 | — | — |
| `c2m2.compound` | 0 | — | — |
| `c2m2.phenotype_disease` | 0 | — | — |
| `c2m2.protein_gene` | 0 | — | — |
| `c2m2.subject_substance` | 0 | — | — |
| `c2m2.substance` | 0 | — | — |

### GitHub Activity

| Object | Rows | Data Refreshed | Description |
|---|---:|---|---|
| `analytics.github_activity_weekly` | 20,304 | — | Per-(repo, week, kind) activity counts. kind in {commit, issue, pull_request, star}. Drives "trend over time" chat queries. Join on repo_id to analytics.gith… |
| `analytics.github_contributors` | 961 | 2026-09-10 21:20 UTC | Per-(repo, contributor) contribution counts. Aggregate across repos to find top contributors. login may be a bot account. |
| `analytics.github_repos` | 182 | 2026-09-10 21:20 UTC | Per-GitHub-repo summary. One row per repo_id. core_project_numbers is a TEXT[] — filter with WHERE 'U54OD036472' = ANY (core_project_numbers). Sustainability… |
| `analytics.github_readmes` | 166 | 2026-09-10 21:20 UTC | Decoded README text per GitHub repo (one row per repo_id). Join to analytics.github_repos on repo_id. content is UTF-8 plain text, truncated to 256 KB. |
| `analytics.github_citations` | 0 | — | CITATION.cff contents for repos that publish one. doi/pmid are the direct crosswalk to analytics.publications: WHERE doi IS NOT NULL → join on doi; WHERE pmi… |

### Google Analytics

| Object | Rows | Data Refreshed | Description |
|---|---:|---|---|
| `analytics.ga_geo` | 0 | — | Geographic rollups: continent/country/region/city distinct totalUsers per property. geo_level discriminates which dimension the row is for. |
| `analytics.ga_pageviews` | 0 | — | Per-(property, date) GA pageviews timeseries. Sourced from over_time runReport (dimensions=[date], metrics=[screenPageViews, totalUsers, sessions, averageSes… |
| `analytics.ga_property_coverage` | 0 | — | GA properties this ETL is authorized for, plus how many reports we have stored. Use to answer "do we have GA data for DCC X?" — zero report_count means acces… |
| `analytics.ga_top_pages` | 0 | — | Per-page pageview rollup. From top_pages runReport (dimensions=[pagePath, pageTitle], metrics=[screenPageViews, totalUsers, averageSessionDuration]). page_pa… |
| `analytics.ga_traffic_sources` | 0 | — | Sessions and users grouped by GA default channel group / source / medium. Use to answer "where is traffic to DCC X coming from?" |

### Infrastructure

| Object | Rows | Data Refreshed | Description |
|---|---:|---|---|
| `analytics.data_inventory` | 111 | 2026-05-24 23:29 UTC | Single canonical inventory of every table/view/matview the cfde-atlas ETL maintains. Populated by flows.refresh_inventory after load_all completes. Powers th… |

### Raw Layer

| Object | Rows | Data Refreshed | Description |
|---|---:|---|---|
| `raw.github_commits` | 126,111 | — | — |
| `raw.reporter_citing_projects` | 64,629 | — | NIH RePORTER project records for downstream grants that fund publications citing CFDE work. NOT a CFDE cohort. Use analytics.citing_grant_details and the cit… |
| `raw.github_issues` | 28,037 | — | — |
| `raw.reporter_citing_publications` | 17,616 | — | RePORTER /v2/publications/search rows for pmids that cite CFDE publications. PK is (citing_pmid, core_project_number) — a citing paper acknowledging multiple… |
| `raw.epmc_hits` | 13,068 | — | One row per (query, Europe PMC record) returned in a pubsearch run. Written by flows.pubsearch_run. A paper matched by several queries appears once per query… |
| `raw.icite_citations` | 11,551 | — | Forward-citation edges: one row per (CFDE pmid, pmid that cites it). Derived from raw.icite.source -> cited_by[]. Drives the "downstream impact" queries used… |
| `raw.icite_citing_pubs` | 10,476 | — | iCite metadata for pmids that cite CFDE-funded papers (downstream impact). Same /api/pubs schema as raw.icite — kept in a separate table so the CFDE set stay… |
| `raw.github_releases` | 2,542 | — | — |
| `raw.github_contributors` | 961 | — | — |
| `raw.github_stars` | 891 | — | Per-(repo, user, timestamp) star events. Drives "stars over time" timeseries. |
| `raw.epmc_evidence` | 782 | — | Full-text evidence for candidate papers: the sentence in which a query's term was found, per section. Written by flows.pubsearch_evidence (milestone 3) from … |
| `raw.epmc_queries` | 603 | — | One row per query executed in a pubsearch run. Written by flows.pubsearch_run. Columns program..notes mirror the PPST Script_Input sheet one-to-one so a run … |
| `raw.github_languages` | 560 | — | — |
| `raw.drc_dcc` | 522 | — | CFDE DRC current_dcc_assets manifest. Linkout templates and per-DCC assets. dcc_id is the DRC-side DCC UUID; mapping to NIH core_project_number requires a se… |
| `raw.reporter_publications` | 505 | — | RePORTER /v2/publications/search rows. PK is (pmid, core_project_number) because a paper acknowledging multiple grants yields multiple rows. |
| `raw.icite` | 445 | — | NIH iCite /api/pubs records, one per pmid. Source for citation counts, RCR, authors, journal, and cited_by (forward citations used in #12). |
| `raw.github_forks` | 387 | — | Forks of tracked repos. parent_repo_id joins to raw.github_repos.repo_id. |
| `raw.drc_file` | 349 | — | CFDE DRC current_file_assets manifest. Downloadable files (e.g. C2M2 packages). Keyed on download URL. |
| `raw.entrez_journals` | 196 | — | NCBI Entrez esummary results for journal abbreviations. Used to resolve analytics.publications.journal abbreviations to full names + ISSNs. |
| `raw.github_repo_core_projects` | 184 | — | Many-to-many link between GitHub repos and CFDE core_project_numbers. Populated by topic/search hits during the github flow. |
| `raw.github_repos` | 182 | — | GitHub repository metadata. One row per repo_id. Use raw.github_repo_core_projects for the link to CFDE core_project_numbers. |
| `raw.reporter_projects` | 178 | — | NIH RePORTER projects fetched from /v2/projects/search. One row per project_num; multiple projects share a core_project_number. |
| `raw.drc_code` | 173 | — | CFDE DRC current_code_assets manifest. Code references (APIs, smartAPI specs, JSON-LD endpoints, ETL scripts). Keyed on code URL. |
| `raw.github_readmes` | 166 | — | Decoded README text per repo (one row per repo_id). Truncated to 256 KB to keep the row compact; truncated=true flags when the original was longer. |
| `raw.c2m2_bundles` | 24 | — | Ingest ledger for C2M2 datapackages. One row per (dcc_id, submission_date). The flow inserts status=in_progress before unzipping; flips to ok or failed on co… |
| `raw.opportunities` | 17 | — | Common Fund funding opportunity numbers (RFA-RM-*, NOT-RM-*, OTA-*). Driven by scrape of commonfund.nih.gov plus manual curation. Use analytics.opportunities… |
| `raw.epmc_runs` | 2 | — | One row per pubsearch run of a Common Fund program against Europe PMC. Written by flows.pubsearch_run. run_id = program yaml git sha + run timestamp, so a ru… |
| `raw.ga_properties` | 0 | — | GA4 properties this ETL has access to, with the CFDE core_project_number crosswalk. Loaded from raw/manual-ga-properties.yaml because GA access is granted pe… |
| `raw.ga_reports` | 0 | — | GA4 Data API runReport responses landed as-is. One row per (property_id, report_kind, period_start, period_end). report_kind values: over_time, top_pages, to… |
| `raw.github_citations` | 0 | — | Parsed CITATION.cff for repos that publish one. Software-citation file format. doi/pmid are extracted from preferred-citation.doi/pmid or from identifiers[] … |
| `raw.pubsearch_overrides` | 0 | — | Analyst decisions that override the computed tier for a (program, pmid). Written by humans via the cfde-atlas review queue, never by a flow, and not tied to … |
| `raw.scimago_ranks` | 0 | — | Scimago Journal Rank export. One row per Scimago Sourceid. Use the GIN index on issns to join from raw.entrez_journals.issn. |
<!-- END STATS -->

## Run

Scheduled: `systemd/cfde-atlas-etl-load.timer` runs `load_all` weekly (Sunday 03:00) with `PUBSEARCH_PROGRAMS=cfde`, alerting on failure to the shared `cdsci-lake-ops` ntfy topic via `ntfy-notify@.service` — the platform convention in `monode/infrastructure/SCHEDULING.md`. Install by copying (not symlinking) the units into `~/.config/systemd/user/`, then `systemctl --user daemon-reload && systemctl --user enable --now cfde-atlas-etl-load.timer`. Check with `systemctl --user list-timers cfde-atlas-etl-load.timer` and `journalctl --user -u cfde-atlas-etl-load.service`.

To run by hand:

```bash
export PREFECT_API_URL= PREFECT_SERVER_ALLOW_EPHEMERAL_MODE=true

# Run everything in dep order (recommended):
uv run python -m cfde_atlas_etl.flows.load_all

# Or run a single flow:
uv run python -m cfde_atlas_etl.flows.opportunities
uv run python -m cfde_atlas_etl.flows.projects
uv run python -m cfde_atlas_etl.flows.publications
```

Verify:

```bash
psql "$DATABASE_URL" -c "SELECT count(*), max(data_refreshed_at) FROM analytics.publications;"
```

## Postgres backend

Lives on `pg_ducklake_18` (plain Postgres 18) on `onclappc02`. Specifically NOT `pg_duckdb_18` — pg_duckdb's planner hooks interfere with the LLM-driven query path in cfde-atlas. See `monode/infrastructure/compose/cfde_atlas/` for the production wiring.

## Adding a new flow

The pattern, in order:

1. Source schema as a `pydantic.BaseModel` in `models/` with `extra="allow"` so upstream additions don't break us. Validate at fetch time.
2. Migration: `raw.<name>` table with `(natural_key…, source jsonb, fetched_at timestamptz)`, plus an `analytics.<name>` view that projects typed columns AND carries per-column `COMMENT ON COLUMN` text written for the LLM (this is what `describe_table` returns to cfde-atlas).
3. Flow in `flows/`: fetch → validate → upsert. Mirror `flows/publications.py`.
4. Smoke-test by running the flow and checking `SELECT count(*) FROM analytics.<name>`.

## Open follow-ups

- [#1](https://github.com/seandavi/cfde-atlas-etl/issues/1) Initialize Alembic
- [#2](https://github.com/seandavi/cfde-atlas-etl/issues/2) Grants flow (blocks the next two)
- [#3](https://github.com/seandavi/cfde-atlas-etl/issues/3) GitHub activity flow
- [#4](https://github.com/seandavi/cfde-atlas-etl/issues/4) GA pageviews flow
- [#5](https://github.com/seandavi/cfde-atlas-etl/issues/5) Internal Prefect server (optional)
