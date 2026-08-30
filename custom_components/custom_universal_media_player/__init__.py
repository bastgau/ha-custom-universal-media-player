"""The custom universal media player component."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from homeassistant.const import CONF_STATE_TEMPLATE, Platform

from .const import (
    ATTR_ENTITY_PICTURE_LOCAL,  # pyright: ignore[reportUnusedImport] # noqa: F401
    CONF_ACTIVE_CHILD_TEMPLATE,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

PLATFORMS: list[Platform] = [Platform.MEDIA_PLAYER]

# repr() of a Template, e.g. "Template<template=({{ 1 }}) renders=0>". Versions
# 1.6 and 1.7 stored that instead of the template's own source, so the entry
# they wrote holds a string that renders to another repr() rather than a state.
_TEMPLATE_REPR = re.compile(r"^Template<template=\((?P<source>.*)\) renders=\d+>$", re.DOTALL)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate a config entry to the current schema.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry to migrate.

    Returns:
        True if the entry could be migrated.

    """
    if entry.version > 1:
        # Downgrade: an entry written by a newer version is not readable here.
        return False

    if entry.minor_version < 2:
        data = dict(entry.data)
        for key in (CONF_ACTIVE_CHILD_TEMPLATE, CONF_STATE_TEMPLATE):
            value = data.get(key)
            if isinstance(value, str) and (match := _TEMPLATE_REPR.match(value)):
                data[key] = match.group("source")
        hass.config_entries.async_update_entry(entry, data=data, minor_version=2)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the custom universal media player from a config entry.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry to set up.

    Returns:
        True if the setup was successful.

    """
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a custom universal media player config entry.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry to unload.

    Returns:
        True if the unload was successful.

    """
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
