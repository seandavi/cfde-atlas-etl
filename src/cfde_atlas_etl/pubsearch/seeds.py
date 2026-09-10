"""Seed rows for a program's PPST Script_Input sheet. See docs/pubsearch/SPEC.md.

Each seed kind is one SQL statement plus a pure builder that turns the fetched
tuples into `SeedRow`s, so the transforms are testable without a database.
Which kinds run, and the hand-typed rows, come from `programs/<program>.yaml`.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import psycopg
import yaml
from pydantic import BaseModel, ConfigDict

from cfde_atlas_etl.config import get_settings
from cfde_atlas_etl.pubsearch.models import ImpactCategory, SeedRow

PROGRAMS_DIR = Path(__file__).parent / "programs"

SeedKind = Literal["grants", "cites", "accessions", "dcc_domains", "drc_urls", "curated"]

_TIER_RANK: dict[str, int] = {"Awardee": 0, "User": 1, "Broader.Influence": 2}
_TEMPLATE_SEGMENT = re.compile(r"[{<]")


class CuratedRow(BaseModel):
    """A hand-typed Script_Input row; `quote: true` wraps multi-word/dotted terms in quotes."""

    model_config = ConfigDict(extra="forbid")

    impact_category: ImpactCategory
    query_cluster: str
    search_terms: str
    search_field: str = ""
    or_terms: str = ""
    or_search_field: str = ""
    and_terms: str = ""
    and_search_field: str = ""
    not_terms: str = ""
    not_search_field: str = ""
    quote: bool = False

    def to_seed(self, notes: str) -> SeedRow:
        data = self.model_dump(exclude={"quote"})
        if self.quote:
            for k in ("search_terms", "or_terms", "and_terms", "not_terms"):
                data[k] = quote_term(data[k])
        return SeedRow(**data, notes=notes)


class ProgramConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program: str
    display_name: str
    date_window: tuple[int, int] | None = None
    seed_kinds: list[SeedKind]
    accession_namespaces: list[str] = []
    dcc_abbreviations: list[str] = []
    drc_url_contains: list[str] = []
    curated: list[CuratedRow] = []


def load_program(program: str, programs_dir: Path = PROGRAMS_DIR) -> ProgramConfig:
    path = programs_dir / f"{program}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"No program yaml at {path}")
    return ProgramConfig.model_validate(yaml.safe_load(path.read_text()) or {})


# --- pure transforms -----------------------------------------------------------


def quote_term(term: str) -> str:
    return f'"{term}"' if (" " in term or "." in term) and not term.startswith('"') else term


def grant_serial(core_project_number: str, activity_code: str) -> str:
    """R03OD030596 + R03 -> *OD030596 (PPST searches the serial with a leading wildcard)."""
    return "*" + core_project_number.removeprefix(activity_code)


def bare_host(url: str) -> str:
    """https://www.Example.org/ -> example.org"""
    host = urlsplit(url.strip()).netloc or url.strip()
    return host.lower().removeprefix("www.").rstrip("/")


def url_host_path(url: str) -> str:
    """https://a.org/x/{ID}?q=1 -> a.org/x  (template segments, query, fragment dropped)."""
    parts = urlsplit(url.strip())
    segments = [s for s in parts.path.split("/") if s and not _TEMPLATE_SEGMENT.search(s)]
    return "/".join([bare_host(url), *segments])


def accession(study_id: str) -> str:
    """phs001138.v2.p1 -> phs001138"""
    return study_id.strip().split(".", 1)[0]


def order_rows(rows: list[SeedRow]) -> list[SeedRow]:
    """Dedupe, then Awardee (grouped by cluster) -> User -> Broader.Influence, source order kept."""
    unique = list(dict.fromkeys(rows))
    return sorted(
        unique,
        key=lambda r: (
            _TIER_RANK[r.impact_category],
            r.query_cluster if r.impact_category == "Awardee" else "",
        ),
    )


# --- builders over fetched tuples ------------------------------------------------


def grant_rows(fetched: list[tuple[str, str]]) -> list[SeedRow]:
    return [
        SeedRow("Awardee", code, grant_serial(cpn, code), notes="analytics.core_projects")
        for cpn, code in fetched
    ]


def cites_rows(fetched: list[tuple[int | str]]) -> list[SeedRow]:
    return [
        SeedRow(
            "Broader.Influence",
            "Cites_Awardee_Paper",
            f"{pmid}_med",
            "Cites",
            notes="analytics.publications",
        )
        for (pmid,) in fetched
    ]


def accession_rows(fetched: list[tuple[str]]) -> list[SeedRow]:
    return [
        SeedRow("User", "dBGap_accession_number", accession(sid), notes="c2m2.file")
        for (sid,) in fetched
    ]


def domain_rows(fetched: list[tuple[str, str]]) -> list[SeedRow]:
    return [
        SeedRow("User", "Data_Resource_Identifier", bare_host(url), field, notes="c2m2.dcc")
        for _abbr, url in fetched
        for field in ("Methods", "Acknowledgement & Funding", "")
    ]


def drc_url_rows(fetched: list[tuple[str, str]], contains: list[str]) -> list[SeedRow]:
    return [
        SeedRow(
            "User",
            "Data_Resource_Identifier",
            url_host_path(url),
            field,
            notes="analytics.drc_code",
        )
        for _name, url in fetched
        if any(s.lower() in url.lower() for s in contains)
        for field in ("Methods", "")
    ]


def curated_rows(cfg: ProgramConfig) -> list[SeedRow]:
    notes = f"curated:programs/{cfg.program}.yaml"
    return [r.to_seed(notes) for r in cfg.curated]


# --- SQL ---------------------------------------------------------------------------

_SQL: dict[str, str] = {
    "grants": (
        "SELECT core_project_number, activity_code FROM analytics.core_projects "
        "ORDER BY activity_code, core_project_number"
    ),
    "cites": "SELECT DISTINCT pmid FROM analytics.publications ORDER BY pmid",
    "accessions": (
        "SELECT DISTINCT dbgap_study_id FROM c2m2.file "
        "WHERE dbgap_study_id LIKE 'phs%%' AND id_namespace = ANY(%s) ORDER BY dbgap_study_id"
    ),
    "dcc_domains": (
        "SELECT dcc_abbreviation, dcc_url FROM c2m2.dcc "
        "WHERE dcc_abbreviation = ANY(%s) ORDER BY dcc_abbreviation"
    ),
    "drc_urls": (
        "SELECT name, code_url FROM analytics.drc_code "
        "WHERE asset_type IN ('Apps URL','API','Entity Page Template') ORDER BY name, code_url"
    ),
}


async def build_seeds(program: str) -> list[SeedRow]:
    cfg = load_program(program)
    params: dict[str, tuple] = {
        "accessions": (cfg.accession_namespaces,),
        "dcc_domains": (cfg.dcc_abbreviations,),
    }
    rows: list[SeedRow] = []
    async with (
        await psycopg.AsyncConnection.connect(get_settings().database_url) as conn,
        conn.cursor() as cur,
    ):
        for kind in cfg.seed_kinds:
            if kind == "curated":
                rows += curated_rows(cfg)
                continue
            await cur.execute(_SQL[kind], params.get(kind))
            fetched = await cur.fetchall()
            if kind == "grants":
                rows += grant_rows(fetched)
            elif kind == "cites":
                rows += cites_rows(fetched)
            elif kind == "accessions":
                rows += accession_rows(fetched)
            elif kind == "dcc_domains":
                rows += domain_rows(fetched)
            elif kind == "drc_urls":
                rows += drc_url_rows(fetched, cfg.drc_url_contains)
    return order_rows(rows)
