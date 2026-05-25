-- 0032 — Single source of truth for "what's in this database".
--
-- A regular Postgres table populated by flows.refresh_inventory (which the
-- end of load_all calls). We rebuild rather than maintain it incrementally
-- because the work is cheap and the source-of-truth signal is clearer.

CREATE TABLE IF NOT EXISTS analytics.data_inventory (
    qname               TEXT        NOT NULL PRIMARY KEY,
    schema_name         TEXT        NOT NULL,
    relation_name       TEXT        NOT NULL,
    kind                TEXT        NOT NULL,
    section             TEXT,
    description         TEXT,
    row_count           BIGINT,
    data_refreshed_at   TIMESTAMPTZ,
    last_inventoried_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS data_inventory_section_idx ON analytics.data_inventory (section);

COMMENT ON TABLE analytics.data_inventory IS
    'Single canonical inventory of every table/view/matview the cfde-atlas ETL '
    'maintains. Populated by flows.refresh_inventory after load_all completes. '
    'Powers the chat "what data is in this database?" answer, the auto-generated '
    'README stats block, and the cfde-atlas /about page. Refreshes are full-rebuild '
    '(TRUNCATE + INSERT) so the row set always matches current reality.';

COMMENT ON COLUMN analytics.data_inventory.qname IS
    'Fully-qualified relation name (schema.name). PK.';

COMMENT ON COLUMN analytics.data_inventory.schema_name IS
    'Postgres schema this relation lives in: analytics, raw, c2m2, etc.';

COMMENT ON COLUMN analytics.data_inventory.relation_name IS 'Relation name without schema.';

COMMENT ON COLUMN analytics.data_inventory.kind IS
    'One of: table, view, matview. Useful for chat to know what kind of object backs a name.';

COMMENT ON COLUMN analytics.data_inventory.section IS
    'Topical grouping for presentation. Examples: opportunities-projects-pubs, '
    'forward-citations, drc, c2m2, github, ga, infra.';

COMMENT ON COLUMN analytics.data_inventory.description IS
    'obj_description() of the relation — the human/LLM-facing prose comment authored '
    'in the migration. The same string describe_table returns to the chat.';

COMMENT ON COLUMN analytics.data_inventory.row_count IS
    'COUNT(*) snapshot taken at last_inventoried_at. Approximate for actively-loading tables.';

COMMENT ON COLUMN analytics.data_inventory.data_refreshed_at IS
    'MAX(data_refreshed_at) from the underlying relation if that column exists, else NULL. '
    'Independent of last_inventoried_at — tells you how fresh the actual data is, not when '
    'we counted it.';

COMMENT ON COLUMN analytics.data_inventory.last_inventoried_at IS
    'When refresh_inventory last wrote this row.';
