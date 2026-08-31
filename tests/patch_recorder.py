# Vendored from home-assistant/core 2026.7.1 - tests/patch_recorder.py
# Licensed under the Apache License 2.0, see tests/README.md.
# Do not edit by hand: run `python3 scripts/fetch_ha_test_helpers` instead.
"""Patch recorder related functions."""

from contextlib import contextmanager
import sys

# Patch recorder util session scope
from homeassistant.helpers import recorder as recorder_helper

# Make sure homeassistant.components.recorder.util is not already imported
assert "homeassistant.components.recorder.util" not in sys.modules

real_session_scope = recorder_helper.session_scope


@contextmanager
def _session_scope_wrapper(*args, **kwargs):
    """Make session_scope patchable.

    This function will be imported by recorder modules.
    """
    with real_session_scope(*args, **kwargs) as ses:
        yield ses


recorder_helper.session_scope = _session_scope_wrapper
