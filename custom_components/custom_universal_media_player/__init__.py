"""The custom universal media player component."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.const import Platform

from .const import ATTR_ENTITY_PICTURE_LOCAL  # pyright: ignore[reportUnusedImport] # noqa: F401

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

PLATFORMS: list[Platform] = [Platform.MEDIA_PLAYER]


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
