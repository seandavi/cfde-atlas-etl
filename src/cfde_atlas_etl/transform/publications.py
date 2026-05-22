"""Transforms for publications live in SQL (see migrations/).

This module is intentionally near-empty under the ELT pattern. The
analytics.publications view in `migrations/0002_create_analytics_publications.sql`
is where source jsonb is reshaped into the typed columns cfde-atlas queries.

Keep transforms in SQL; this module exists only to host any pre-load
normalization that genuinely belongs in Python (e.g., unit conversions
that SQL can't express ergonomically). Resist the urge to move SQL
logic here.
"""

from __future__ import annotations
