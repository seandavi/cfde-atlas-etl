-- 0007 — Drop the legacy publications layer.
--
-- Pre-refactor (migrations 0001 + 0002), the publications flow consumed
-- icc-eval-core's pre-baked publications.json. The refactor (#9) replaces
-- that with direct RePORTER + iCite parsing. The new raw shape lives in
-- raw.reporter_publications + raw.icite (0008/0009) and the analytics view
-- is rebuilt to JOIN those (0010).
--
-- Drop the analytics view first (depends on raw.publications), then the
-- raw table.

DROP VIEW IF EXISTS analytics.publications;
DROP TABLE IF EXISTS raw.publications;
