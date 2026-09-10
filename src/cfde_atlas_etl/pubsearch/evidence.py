"""JATS full text -> per-section plain text -> exact-match evidence sentences.

Pure functions, no network or DB. The Europe PMC API tokenizer is loose on
dotted strings (``portal.kidsfirstdrc.org`` matches ``portal``, ``kidsfirstdrc``
and ``org`` as separate tokens), so an API hit may not survive exact matching
here; ``evidence_for`` returns ``None`` for those so the caller can record
"API hit, no exact match".
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator

MAX_SENTENCE = 500

# Substrings of a lower-cased sec-type / <title> -> template Field_Search name.
# First match wins, so "Results and Discussion" -> Results.
_SEC_KEYWORDS: list[tuple[str, str]] = [
    ("intro", "Introduction"),
    ("background", "Introduction"),
    ("method", "Methods"),
    ("material", "Methods"),
    ("availability", "Methods"),  # accessions live in "Data availability"
    ("experimental procedure", "Methods"),
    ("result", "Results"),
    ("finding", "Results"),
    ("discussion", "Discussion"),
    ("conclusion", "Conclusion"),
    ("supplement", "Supplemental"),
    ("acknowledg", "Acknowledgement & Funding"),
    ("funding", "Acknowledgement & Funding"),
]

_WS = re.compile(r"\s+")
_SENTENCE_SPLIT = re.compile(r"\n+|(?<=[.?!])\s+(?=[A-Z0-9])")
_CITES_TERM = re.compile(r"^\d+_med$")
# Elements whose end is a sentence boundary, so a <title> never glues onto the
# first <p> and one <p> never runs into the next.
_BLOCK = frozenset(
    {
        "title",
        "p",
        "sec",
        "abstract",
        "ack",
        "ref",
        "label",
        "caption",
        "list-item",
        "tr",
        # front/back-matter leaves that sit side by side with no text between them
        "award-id",
        "funding-source",
        "custom-meta",
        "kwd",
        "contrib",
        "aff",
        "article-id",
    }
)


def _chunks(el: ET.Element) -> Iterator[str]:
    if el.text:
        yield _WS.sub(" ", el.text)
    for child in el:
        yield from _chunks(child)
        if child.tag in _BLOCK:
            yield "\n"
        if child.tail:
            yield _WS.sub(" ", child.tail)


def _text(*elements: ET.Element) -> str:
    """Plain text: inline whitespace collapsed, one line per block element."""
    raw = "\n".join("".join(_chunks(el)) for el in elements)
    lines = (line.strip() for line in raw.split("\n"))
    return "\n".join(line for line in lines if line)


def _classify(sec: ET.Element) -> str | None:
    title = sec.find("title")
    label = f"{sec.get('sec-type', '')} {_text(title) if title is not None else ''}".lower()
    return next((name for kw, name in _SEC_KEYWORDS if kw in label), None)


def sections(xml: str) -> dict[str, str]:
    """Plain text per logical section, keyed by template Field_Search name.

    Keys: "", Title, Abstract, Title and Abstract, Introduction, Methods, Results,
    Discussion, Conclusion, Acknowledgement & Funding, References, Supplemental,
    Other. Missing sections are empty strings; "" is the whole document.
    """
    root = ET.fromstring(xml)
    front = root.find("front")
    body = root.find("body")
    back = root.find("back")

    out: dict[str, list[ET.Element]] = {}

    def add(key: str, el: ET.Element) -> None:
        out.setdefault(key, []).append(el)

    if front is not None:
        title = front.find(".//title-group/article-title")
        if title is not None:
            add("Title", title)
        for el in front.iter("abstract"):
            add("Abstract", el)

    for parent in (body, back):
        if parent is None:
            continue
        for child in parent:
            if child.tag == "sec":
                add(_classify(child) or "Other", child)
            elif parent is body:
                add("Other", child)

    for tag in ("ack", "funding-group", "funding-statement"):
        for el in root.iter(tag):
            add("Acknowledgement & Funding", el)
    for el in root.iter("ref-list"):
        add("References", el)
    for el in root.iter("supplementary-material"):
        add("Supplemental", el)

    result = {key: _text(*els) for key, els in out.items()}
    for key in (
        "Title",
        "Abstract",
        "Introduction",
        "Methods",
        "Results",
        "Discussion",
        "Conclusion",
        "Acknowledgement & Funding",
        "References",
        "Supplemental",
        "Other",
    ):
        result.setdefault(key, "")
    result["Title and Abstract"] = f"{result['Title']} {result['Abstract']}".strip()
    result[""] = _text(root)
    return result


def find_sentence(text: str, term: str) -> str | None:
    """First sentence of `text` containing `term` (case-insensitive substring).

    `term` follows PPST conventions: comma-separated alternatives are OR-ed, a
    leading ``*`` wildcard (grant serials) is dropped, and ``<pmid>_med`` cites
    terms return None (a citation is not sentence evidence).
    """
    alts = [a.strip().strip('"').lstrip("*").lower() for a in term.split(",")]
    alts = [a for a in alts if a and not _CITES_TERM.match(a)]
    if not alts:
        return None
    for sentence in _SENTENCE_SPLIT.split(text):
        low = sentence.lower()
        if any(a in low for a in alts):
            return sentence[:MAX_SENTENCE]
    return None


def evidence_for(
    xml: str, queries: list[tuple[int, str, str]]
) -> list[tuple[int, str, str | None]]:
    """For each (query_no, search_terms, search_field): (query_no, section, sentence|None).

    Looks in the query's section; unknown or blank fields search the whole text.
    """
    secs = sections(xml)
    return [
        (qno, field, find_sentence(secs.get(field, secs[""]), terms))
        for qno, terms, field in queries
    ]
