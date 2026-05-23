"""Scrape Common Fund funding opportunities.

Listing page is server-rendered HTML — no JS required. Per-document parse:

- HTML guide page (grants.nih.gov): pull the `.noticenum` span and the
  "Activity Code" datacolumn anchor.
- PDF (commonfund.nih.gov/sites/default/files/*.pdf): regex the first page text
  for the opportunity number.
"""

from __future__ import annotations

import io
import re
from typing import Any
from urllib.parse import urljoin

import httpx
from pypdf import PdfReader
from selectolax.parser import HTMLParser

LISTING_URL = "https://commonfund.nih.gov/dataecosystem/FundingOpportunities"

OPPORTUNITY_NUMBER_PATTERN = re.compile(
    r"((RFA|NOT)-RM-\d+-\d+|OTA-\d+-\d+)",
    re.IGNORECASE,
)

USER_AGENT = "cfde-atlas-etl/0.1 (+https://github.com/seandavi/cfde-atlas-etl)"


def _prefix(opportunity_id: str) -> str:
    upper = opportunity_id.upper()
    for p in ("RFA", "NOT", "OTA"):
        if upper.startswith(p):
            return p
    return ""


def extract_document_links(html: str, base_url: str = LISTING_URL) -> list[str]:
    """Pull every linked HTML/PDF opportunity document from the listing page."""
    tree = HTMLParser(html)
    links: list[str] = []
    for a in tree.css("a[href]"):
        href = a.attributes.get("href") or ""
        if href.endswith(".html") or href.endswith(".pdf"):
            absolute = urljoin(base_url, href)
            if OPPORTUNITY_NUMBER_PATTERN.search(absolute):
                links.append(absolute)
    return list(dict.fromkeys(links))


def parse_html_opportunity(html: str) -> dict[str, Any]:
    tree = HTMLParser(html)

    notice = tree.css_first("span.noticenum")
    opportunity_id = notice.text(strip=True) if notice else ""

    if not OPPORTUNITY_NUMBER_PATTERN.search(opportunity_id):
        raise ValueError(f"Invalid opportunity number on HTML page: {opportunity_id!r}")

    activity_code = ""
    for label in tree.css("div.datalabel"):
        if "activity code" in label.text(strip=True).lower():
            sibling = label.parent.css_first("div.datacolumn") if label.parent else None
            if sibling is not None:
                link = sibling.css_first("a")
                if link is not None:
                    activity_code = link.text(strip=True)
                else:
                    activity_code = sibling.text(strip=True).split()[0] if sibling.text() else ""
            break

    return {
        "id": opportunity_id,
        "prefix": _prefix(opportunity_id),
        "activity_code": activity_code,
    }


def parse_pdf_opportunity(pdf_bytes: bytes) -> dict[str, Any]:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    if not reader.pages:
        raise ValueError("PDF has no pages")
    text = reader.pages[0].extract_text() or ""
    match = OPPORTUNITY_NUMBER_PATTERN.search(text)
    if not match:
        raise ValueError("Could not find opportunity number on PDF first page")
    opportunity_id = match.group(1)
    return {
        "id": opportunity_id,
        "prefix": _prefix(opportunity_id),
        "activity_code": "",
    }


async def fetch_listing(client: httpx.AsyncClient) -> list[str]:
    response = await client.get(LISTING_URL, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return extract_document_links(response.text)


async def fetch_opportunity(url: str, client: httpx.AsyncClient) -> dict[str, Any]:
    response = await client.get(url, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    if url.lower().endswith(".pdf"):
        record = parse_pdf_opportunity(response.content)
    elif url.lower().endswith(".html"):
        record = parse_html_opportunity(response.text)
    else:
        raise ValueError(f"Unrecognized document extension: {url}")
    record["source_url"] = url
    return record


async def gather_opportunities(client: httpx.AsyncClient | None = None) -> list[dict[str, Any]]:
    """End-to-end scrape: listing page -> per-doc parse. De-duplicate by id."""
    own_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=60.0, follow_redirects=True)

    try:
        urls = await fetch_listing(client)
        records: list[dict[str, Any]] = []
        seen: set[str] = set()
        for url in urls:
            try:
                record = await fetch_opportunity(url, client)
            except (httpx.HTTPError, ValueError):
                continue
            if record["id"] in seen:
                continue
            seen.add(record["id"])
            records.append(record)
        return records
    finally:
        if own_client:
            await client.aclose()
