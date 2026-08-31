"""Tests for the custom universal media player setup and teardown."""

from homeassistant.components.media_player import MediaPlayerDeviceClass
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_DEVICE_CLASS, CONF_DEVICE_CLASS, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .conftest import PLAYER, UNIQUE_ID, SetupPlayer

from tests.common import MockConfigEntry


async def test_setup_entry_adds_the_player(
    hass: HomeAssistant,
    enable_custom_integrations: None,  # noqa: ARG001
    mock_config_entry: MockConfigEntry,
) -> None:
    """The config entry loads and its media player entity shows up."""
    mock_config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get(PLAYER) is not None


async def test_unload_entry_removes_the_player(
    hass: HomeAssistant,
    enable_custom_integrations: None,  # noqa: ARG001
    mock_config_entry: MockConfigEntry,
) -> None:
    """Unloading the config entry leaves its entity behind as unavailable."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED

    # The entity has a unique id, so the registry keeps it around as a
    # restored, unavailable entity rather than dropping it entirely.
    state = hass.states.get(PLAYER)
    assert state is not None
    assert state.state == STATE_UNAVAILABLE


async def test_entity_uses_the_configured_unique_id(
    entity_registry: er.EntityRegistry,
    setup_player: SetupPlayer,
) -> None:
    """The registry entry is keyed on the unique id stored in the config entry."""
    await setup_player()

    entry = entity_registry.async_get(PLAYER)
    assert entry is not None
    assert entry.unique_id == UNIQUE_ID


async def test_device_class_is_published(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
) -> None:
    """The device class stored in the config entry reaches the entity state."""
    await setup_player(**{CONF_DEVICE_CLASS: MediaPlayerDeviceClass.TV})

    state = hass.states.get(PLAYER)
    assert state is not None
    assert state.attributes[ATTR_DEVICE_CLASS] == MediaPlayerDeviceClass.TV
