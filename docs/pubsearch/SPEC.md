# Publication impact tiers (PPST-compatible) — specification

Status: accepted 2026-09-10. Background analysis lives in `seandavi/cfde-atlas` under
`coc-prep/` (README, DESIGN-publication-search, DESIGN-eval-team-delivery,
NOTE-query-provenance). This document is the contract the issues implement.

## Goal

Produce, for a Common Fund program, the same three publication tiers the NIH OSC Eval team
produces with their PPST spreadsheet-and-script, from data this repo already holds, on a
schedule, with evidence and versioning. First program: CFDE. Output must be directly
comparable to a PPST run.

Tiers, highest wins: **Awardee** (program grant number in funding metadata) >
**User** (program resource named in Methods or Acknowledgements) >
**Broader Influence** (cites an awardee paper, or program name elsewhere).

## Non-goals

- No local full-text index. Europe PMC REST is the search backend (measured: its wildcards and
  section prefixes already exceed what PPST uses; a local OA index is a strict subset).
- No X01 support. X01 award numbers are not in RePORTER; on Kids First they add 14 papers.
- No UI in this repo. Report page and review queue UI belong to `cfde-atlas`.

## Data contract

### Inputs (seed table), generated per program

| Seed kind | Tier | Source | Query shape |
|---|---|---|---|
| Grant serial (`*OD030596`) | Awardee | `analytics.core_projects` (RePORTER via curated FOAs in `config.yaml`) | bare term, no section |
| dbGaP accession | User | `c2m2.file.dbgap_study_id` | bare term |
| Resource domain | User | `c2m2.dcc.dcc_url` bare domain | Methods, Ack & Funding, bare |
| Resource URL | User | `analytics.drc_code` (Apps URL, Entity Page, API) | Methods, bare |
| Program name variants, disambiguators, methods | User / Broader | hand-curated `pubsearch/programs/<program>.yaml`, versioned | per row |
| Awardee PMIDs (cites seed) | Broader | `analytics.publications` for the program's cores | `CITES:<pmid>_med` |

Every seed row records its provenance (source table or `curated`).

### Tables

- `raw.epmc_queries (run_id, query_no, program, tier, cluster, term, section, epmc_query, hit_count, fetched_at)`
- `raw.epmc_hits (run_id, query_no, pmid, pmcid, source, pub_year, is_open_access)`
- `raw.epmc_evidence (run_id, pmid, query_no, section, sentence)` — from per-PMCID fullTextXML, candidates only
- `raw.pubsearch_overrides (program, pmid, tier, reason, decided_by, decided_at)` — analyst overrides, respected by views
- `analytics.pubsearch_runs`, `analytics.pubsearch_matrix` (one row per (program, pmid): awardee/user/broader flags, final_assignment, evidence), `analytics.pubsearch_summary` (per program/run: tier counts, per-cluster counts)

Column comments are part of the contract (they drive `describe_table` in cfde-atlas).

### Outputs

- PPST-shaped input workbook (`Script_Input` sheet, template preserved) for a program.
- PPST-shaped output workbook: Summary, Query_Summary, Data_Tabular, Data_Matrixed_Query,
  Data_Matrixed_Cluster, plus evidence column and run id.

## Acceptance

- Kids First oracle: for the 15 non-grant Kids First queries in the Eval team's run, our
  Europe PMC runner reproduces their hit counts exactly when given their query strings
  (already verified by hand for query 130: 29 hits).
- Every seed row has provenance; the curated YAML is the only hand-typed input.
- A run is reproducible from `(program yaml git sha, run_id)`.
- Preprints are included and flagged (`source = PPR`); tier counts are reported with and
  without them.

## Milestones

1. **Input workbook for CFDE** — generate the PPST `Script_Input` sheet from the seed table so
   the program officer can hand it to the Eval team.
2. **Seeds and runner** — seed generation + Europe PMC query runner landing in `raw.epmc_*`.
3. **Evidence and views** — full-text evidence pass, overrides table, analytics views.
4. **Exports** — PPST-shaped output workbook and per-program summary JSON for the atlas.
