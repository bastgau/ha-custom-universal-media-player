"""Fixtures for the custom universal media player tests."""

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

# Home Assistant discovers custom integrations by importing the top-level
# `custom_components` package (see homeassistant.loader._get_custom_components).
# The vendored test config dir ships its own (empty) `custom_components`
# package, and it lands first on sys.path once Home Assistant mounts the config
# dir. Importing the repository's package here, at collection time, puts it in
# sys.modules first so it is the one Home Assistant ends up scanning.
import custom_components  # noqa: F401
from custom_components.custom_universal_media_player.const import (
    CONF_ATTRS,
    CONF_CHILDREN,
    CONF_COMMANDS,
    DOMAIN,
)
import pytest

from homeassistant.components.media_player import DOMAIN as MEDIA_PLAYER_DOMAIN, MediaPlayerEntity
from homeassistant.const import CONF_NAME, CONF_UNIQUE_ID
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from tests.common import MockConfigEntry

if TYPE_CHECKING:
    from homeassistant.helpers.entity_component import EntityComponent

CHILD_TV = "media_player.living_room_tv"
CHILD_SPEAKER = "media_player.living_room_speaker"
PLAYER = "media_player.test_player"

type SetupPlayer = Callable[..., Awaitable[MockConfigEntry]]

UNIQUE_ID = "0123456789abcdef"


def build_config_entry(**overrides: Any) -> MockConfigEntry:
    """Build a config entry from partial entry data.

    Args:
        **overrides: The entry data keys to set, on top of a player named
            "Test player" with no children, commands or attribute overrides.

    Returns:
        The config entry, not yet added to Home Assistant.

    """
    data: dict[str, Any] = {
        CONF_NAME: "Test player",
        CONF_UNIQUE_ID: UNIQUE_ID,
        CONF_CHILDREN: [],
        CONF_COMMANDS: {},
        CONF_ATTRS: {},
    }
    data.update(overrides)

    return MockConfigEntry(
        domain=DOMAIN,
        title=data[CONF_NAME],
        unique_id=data[CONF_UNIQUE_ID],
        data=data,
    )


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a config entry with the minimal set of options.

    Returns:
        A config entry for a player named "Test player" with no children.

    """
    return build_config_entry()


@pytest.fixture
async def setup_player(
    hass: HomeAssistant,
    enable_custom_integrations: None,  # noqa: ARG001
) -> SetupPlayer:
    """Return a helper setting up a player from partial config entry data.

    Args:
        hass: The Home Assistant instance.
        enable_custom_integrations: Makes the integration loadable from the
            repository's custom_components directory.

    Returns:
        An awaitable taking config entry data overrides as keyword arguments
        and returning the loaded config entry.

    """

    async def _setup_player(**overrides: Any) -> MockConfigEntry:
        entry = build_config_entry(**overrides)
        entry.add_to_hass(hass)

        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        return entry

    return _setup_player


@pytest.fixture
async def media_player_component(hass: HomeAssistant) -> None:
    """Set up the media_player integration, registering its actions.

    Args:
        hass: The Home Assistant instance.

    """
    assert await async_setup_component(hass, MEDIA_PLAYER_DOMAIN, {})
    await hass.async_block_till_done()


def get_player(hass: HomeAssistant, entity_id: str = PLAYER) -> MediaPlayerEntity:
    """Return the entity object behind a media player entity id.

    Calling a service on the player itself would be intercepted by the mocked
    media_player actions the tests use to observe the calls it forwards to its
    children, so the tests drive the entity object directly instead.

    Args:
        hass: The Home Assistant instance.
        entity_id: The entity id to look up.

    Returns:
        The media player entity.

    """
    component: EntityComponent[MediaPlayerEntity] = hass.data[MEDIA_PLAYER_DOMAIN]
    entity = component.get_entity(entity_id)
    assert entity is not None
    return entity


async def set_child_state(
    hass: HomeAssistant,
    entity_id: str,
    state: str,
    **attributes: Any,
) -> None:
    """Set the state of a (fake) child media player and let the player react.

    The player only refreshes itself from the state change events of the
    entities it depends on, so a child state has to be published after it has
    been set up for it to be taken into account.

    Args:
        hass: The Home Assistant instance.
        entity_id: The child entity id.
        state: The state to set.
        **attributes: The state attributes to set.

    """
    hass.states.async_set(entity_id, state, attributes)
    await hass.async_block_till_done()
