"""Tests for the README stats rewriter — no DB needed."""

from __future__ import annotations

import datetime as dt

from cfde_atlas_etl.scripts.regen_readme_stats import BEGIN, END, render, replace_block


def test_render_groups_by_section_and_orders_by_row_count() -> None:
    inventory: list[dict[str, object]] = [
        {
            "qname": "analytics.publications",
            "section": "opportunities-projects-pubs",
            "description": "Grant-acknowledging publications.",
            "row_count": 459,
            "data_refreshed_at": dt.datetime(2026, 5, 23, 14, 32, tzinfo=dt.UTC),
        },
        {
            "qname": "analytics.opportunities",
            "section": "opportunities-projects-pubs",
            "description": "Common Fund FOAs.",
            "row_count": 17,
            "data_refreshed_at": None,
        },
        {
            "qname": "analytics.c2m2_summary",
            "section": "c2m2",
            "description": "Per-DCC entity counts.",
            "row_count": 13,
            "data_refreshed_at": None,
        },
    ]
    out = render(inventory)
    assert "### Opportunities, Projects, Publications" in out
    assert "### C2M2 (DCC Contents)" in out
    # 459 row count appears formatted with comma.
    assert "459" in out
    # Larger row_count sorted first within section.
    pub_pos = out.find("analytics.publications")
    opp_pos = out.find("analytics.opportunities")
    assert pub_pos < opp_pos


def test_replace_block_idempotent() -> None:
    original = f"""# Title

Some prose.

## Dataset Stats

{BEGIN}
old content
{END}

## Other

footer.
"""
    new = replace_block(original, "FRESH\n")
    assert "FRESH" in new
    assert "old content" not in new
    # Idempotent — running it again with the same block leaves it stable.
    again = replace_block(new, "FRESH\n")
    assert again == new


def test_replace_block_appends_when_markers_missing() -> None:
    original = "# Title\n\nNo markers here.\n"
    out = replace_block(original, "GENERATED\n")
    assert BEGIN in out
    assert END in out
    assert "GENERATED" in out
