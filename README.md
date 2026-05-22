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
| `flows.publications` | `nih-cfde/icc-eval-core` `publications.json` | `raw.publications` → `analytics.publications` |

The publications source can acknowledge multiple grants per paper, so the raw key is `(pmid, core_project_number)`.

## Setup

Requires `uv`, `psql`, and a reachable Postgres.

```bash
uv sync --extra dev
cp .env.example .env   # then fill in DATABASE_URL
psql "$DATABASE_URL" -f migrations/0001_create_raw_publications.sql
psql "$DATABASE_URL" -f migrations/0002_create_analytics_publications.sql
```

For the onclappc02 dev environment, the password lives in GSM (project `cdsci-infra`, secret `cfde-atlas-dev-db-password-onclappc02`) — see `.env.example` for the snippet.

## Run

Until a long-running Prefect server exists (filed as [#5](https://github.com/seandavi/cfde-atlas-etl/issues/5)), run flows directly:

```bash
export PREFECT_API_URL= PREFECT_SERVER_ALLOW_EPHEMERAL_MODE=true
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
