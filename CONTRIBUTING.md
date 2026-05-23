# Contributing

## Local setup

```bash
uv sync --extra dev
uv run pre-commit install
```

## PR workflow

1. Branch from `main`. Naming: `feat/<short>`, `fix/<short>`, `refactor/<short>`, `chore/<short>`.
2. Commit early; pre-commit runs ruff lint+format on staged files.
3. Open PR. CI runs ruff lint, ruff format check, pyrefly typecheck, pytest.
4. Wait for CI green.
5. Squash merge.

A consolidated human/AI review pass happens after a batch of related PRs lands rather than per-PR.

## Adding a new source flow

Pattern (mirror `flows/publications.py` once the upstream refactor lands):

1. `sources/<name>.py` — async fetch (httpx). Generic, no domain coupling.
2. `models/<name>.py` — pydantic source guard with `model_config = ConfigDict(extra="allow")`. Validates at fetch boundary.
3. `migrations/000X_create_raw_<name>.sql` — `raw.<name>` table with `(natural_key…, source jsonb, fetched_at timestamptz)`.
4. `migrations/000Y_create_analytics_<name>.sql` — `analytics.<name>` view with typed columns and per-column `COMMENT ON COLUMN` written for the LLM (this is what `describe_table` returns to cfde-atlas).
5. `sinks/postgres.py` — add an `upsert_raw_<name>` function.
6. `flows/<name>.py` — `@flow` orchestrating fetch → validate → upsert.
7. `tests/test_<name>.py` — pytest-httpx mock; assert row counts + key shape.

## Style

- Async by default in sources, sinks, flows.
- No comments stating what the code does. Comments only when the why is non-obvious.
- Per-column SQL `COMMENT ON COLUMN` is mandatory on analytics views. cfde-atlas's `describe_table` exposes them to the LLM verbatim.

## Tests

Run all checks locally:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pyrefly check src tests
uv run pytest
```
