"""Tests for the curated config loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from cfde_atlas_etl.curated import _load, load_core_projects, load_opportunities


def test_repo_config_loads() -> None:
    _load.cache_clear()
    config = _load(Path("config.yaml"))
    assert "opportunities" in config
    assert "core_projects" in config


def test_opportunities_parse_into_pydantic_models() -> None:
    _load.cache_clear()
    records = load_opportunities(Path("config.yaml"))
    assert len(records) > 0
    ids = {r.id for r in records}
    # Mirrored from icc-eval-core's canonical list; these two are anchors.
    assert "RFA-RM-24-006" in ids
    assert "OTA-20-005" in ids


def test_core_projects_returns_strings() -> None:
    _load.cache_clear()
    records = load_core_projects(Path("config.yaml"))
    assert all(isinstance(c, str) for c in records)
    assert "U54DA049110" in records


def test_missing_config_raises(tmp_path: Path) -> None:
    _load.cache_clear()
    missing = tmp_path / "nope.yaml"
    with pytest.raises(FileNotFoundError):
        _load(missing)
