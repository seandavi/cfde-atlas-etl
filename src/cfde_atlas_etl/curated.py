"""Load the PR-curated config (`config.yaml`).

Replaces the commonfund.nih.gov scrape (issue #33). Single source of truth
for FOAs and manually-added core projects.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from cfde_atlas_etl.models.opportunity import CommonFundOpportunity

CONFIG_PATH = Path("config.yaml")


@lru_cache(maxsize=1)
def _load(path: Path = CONFIG_PATH) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(
            f"Expected curated config at {path}. Run from the repo root or set the path explicitly."
        )
    payload = yaml.safe_load(path.read_text()) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must be a mapping at the top level.")
    return payload


def load_opportunities(path: Path = CONFIG_PATH) -> list[CommonFundOpportunity]:
    raw = _load(path).get("opportunities") or []
    return [CommonFundOpportunity.model_validate(r) for r in raw]


def load_core_projects(path: Path = CONFIG_PATH) -> list[str]:
    raw = _load(path).get("core_projects") or []
    return [str(c) for c in raw if c]
