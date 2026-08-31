# Vendored from home-assistant/core 2026.7.1 - tests/testing_config/custom_components/test_constant_deprecation/__init__.py
# Licensed under the Apache License 2.0, see tests/README.md.
# Do not edit by hand: run `python3 scripts/fetch_ha_test_helpers` instead.
"""Test deprecated constants custom integration."""

from types import ModuleType
from typing import Any


def import_deprecated_constant(module: ModuleType, constant_name: str) -> Any:
    """Import and return deprecated constant."""
    return getattr(module, constant_name)
