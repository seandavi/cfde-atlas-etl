"""Smoke tests that don't touch external services."""

from __future__ import annotations

import importlib


def test_package_imports() -> None:
    importlib.import_module("cfde_atlas_etl")


def test_config_module_imports() -> None:
    importlib.import_module("cfde_atlas_etl.config")
