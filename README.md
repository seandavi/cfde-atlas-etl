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
migrations/                       — numbered SQL migrations, applied with psql for now
src/cfde_atlas_etl/
  flows/                          — Prefect flow entrypoints, one per source
  sources/                        — async fetchers (icc-eval-core, etc.)
  models/                         — pydantic source-schema guards
  transform/                      — flow-local transforms (kept thin; prefer SQL views)
  sinks/postgres.py               — upserts into raw.* tables
```

## Current flows

| Flow | Source | Target |
|---|---|---|
| `flows.opportunities` | commonfund.nih.gov scrape + `raw/manual-opportunities.yaml` | `raw.opportunities` → `analytics.opportunities` |
| `flows.projects` | NIH RePORTER `/v2/projects/search` | `raw.reporter_projects` → `analytics.projects` + `analytics.core_projects` |
| `flows.publications` | NIH RePORTER `/v2/publications/search` + iCite `/api/pubs` | `raw.reporter_publications` + `raw.icite` → `analytics.publications` |
| `flows.journals` | Scimago journal rank CSV + NCBI Entrez esummary | `raw.scimago_ranks` + `raw.entrez_journals` → `analytics.journals` |
| `flows.citing_publications` | iCite cited_by + per-citing-pmid iCite lookup | `raw.icite_citations` + `raw.icite_citing_pubs` → `analytics.citing_publications` |
| `flows.citing_grants` | RePORTER `/v2/publications/search?pmids=...` for citing pmids | `raw.reporter_citing_publications` → `analytics.citing_grants` + `analytics.citing_grants_rollup` |
| `flows.drc` | `cfde-drc.s3.amazonaws.com` TSV manifests (dcc/file/code) | `raw.drc_*` → `analytics.drc_*` + `analytics.drc_assets` |
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

## Run

Until a long-running Prefect server exists (filed as [#5](https://github.com/seandavi/cfde-atlas-etl/issues/5)), run flows directly:

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
