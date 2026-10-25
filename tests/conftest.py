"""Shared fixtures for the custom universal media player test suite."""

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(  # pylint: disable=unused-argument
    enable_custom_integrations: None,
) -> None:
    """Enable custom_components/ discovery for every test, through the upstream fixture."""
