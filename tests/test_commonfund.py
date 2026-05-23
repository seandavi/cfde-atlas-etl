"""Tests for the commonfund scraper.

Pure unit tests against HTML/PDF fixtures inline below. No network.
"""

from __future__ import annotations

from cfde_atlas_etl.sources.commonfund import (
    extract_document_links,
    parse_html_opportunity,
)

LISTING_FIXTURE = """
<html><body>
  <table>
    <tr><td><a href="https://grants.nih.gov/grants/guide/rfa-files/RFA-RM-24-006.html">RFA-RM-24-006</a></td></tr>
    <tr><td><a href="https://commonfund.nih.gov/sites/default/files/OTA-24-005.pdf">OTA-24-005</a></td></tr>
    <tr><td><a href="https://grants.nih.gov/grants/guide/notice-files/NOT-RM-24-006.html">NOT-RM-24-006</a></td></tr>
    <tr><td><a href="https://example.org/unrelated.html">other</a></td></tr>
  </table>
</body></html>
"""

HTML_OPPORTUNITY_FIXTURE = """
<html><body>
  <div class="row">
    <div class="col-md-4 datalabel">Notice Number</div>
    <div class="col-md-8 datacolumn">
      <span class="noticenum">RFA-RM-24-006</span>
    </div>
  </div>
  <div class="row">
    <div class="col-md-4 datalabel">Activity Code</div>
    <div class="col-md-8 datacolumn">
      <p><a href="//grants.nih.gov/...">U54</a> Cooperative Agreement</p>
    </div>
  </div>
</body></html>
"""


def test_extract_document_links_filters_non_opportunity_anchors() -> None:
    links = extract_document_links(LISTING_FIXTURE)
    assert len(links) == 3
    assert "RFA-RM-24-006.html" in links[0]
    assert "OTA-24-005.pdf" in links[1]
    assert all("unrelated" not in link for link in links)


def test_extract_document_links_dedupes() -> None:
    duplicate = LISTING_FIXTURE + LISTING_FIXTURE
    links = extract_document_links(duplicate)
    assert len(links) == 3


def test_parse_html_opportunity_extracts_id_and_activity_code() -> None:
    record = parse_html_opportunity(HTML_OPPORTUNITY_FIXTURE)
    assert record["id"] == "RFA-RM-24-006"
    assert record["prefix"] == "RFA"
    assert record["activity_code"] == "U54"
