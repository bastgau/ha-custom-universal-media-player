"""Tests for the custom universal media player entity."""

from typing import Any
from unittest.mock import AsyncMock, Mock, patch

from custom_components.custom_universal_media_player.const import (
    ATTR_ACTIVE_CHILD,
    ATTR_ENTITY_PICTURE_LOCAL,
    CONF_ACTIVE_CHILD_TEMPLATE,
    CONF_ATTRS,
    CONF_BROWSE_MEDIA_ENTITY,
    CONF_CHILDREN,
    CONF_COMMANDS,
    DOMAIN,
)
from custom_components.custom_universal_media_player.media_player import async_setup_platform
import pytest

from homeassistant.components.media_player import (
    ATTR_APP_ID,
    ATTR_APP_NAME,
    ATTR_GROUP_MEMBERS,
    ATTR_INPUT_SOURCE,
    ATTR_INPUT_SOURCE_LIST,
    ATTR_MEDIA_ALBUM_ARTIST,
    ATTR_MEDIA_ALBUM_NAME,
    ATTR_MEDIA_ARTIST,
    ATTR_MEDIA_CHANNEL,
    ATTR_MEDIA_CONTENT_ID,
    ATTR_MEDIA_CONTENT_TYPE,
    ATTR_MEDIA_DURATION,
    ATTR_MEDIA_EPISODE,
    ATTR_MEDIA_PLAYLIST,
    ATTR_MEDIA_POSITION,
    ATTR_MEDIA_POSITION_UPDATED_AT,
    ATTR_MEDIA_REPEAT,
    ATTR_MEDIA_SEASON,
    ATTR_MEDIA_SERIES_TITLE,
    ATTR_MEDIA_SHUFFLE,
    ATTR_MEDIA_TITLE,
    ATTR_MEDIA_TRACK,
    ATTR_MEDIA_VOLUME_LEVEL,
    ATTR_MEDIA_VOLUME_MUTED,
    ATTR_SOUND_MODE,
    ATTR_SOUND_MODE_LIST,
    DOMAIN as MEDIA_PLAYER_DOMAIN,
    BrowseMedia,
    MediaClass,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
    RepeatMode,
)
from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.const import (
    ATTR_ASSUMED_STATE,
    ATTR_ENTITY_ID,
    ATTR_ENTITY_PICTURE,
    ATTR_SUPPORTED_FEATURES,
    CONF_NAME,
    CONF_STATE,
    CONF_STATE_TEMPLATE,
    EVENT_HOMEASSISTANT_START,
    SERVICE_MEDIA_NEXT_TRACK,
    SERVICE_MEDIA_PAUSE,
    SERVICE_MEDIA_PLAY,
    SERVICE_MEDIA_PLAY_PAUSE,
    SERVICE_MEDIA_PREVIOUS_TRACK,
    SERVICE_MEDIA_SEEK,
    SERVICE_MEDIA_STOP,
    SERVICE_REPEAT_SET,
    SERVICE_SHUFFLE_SET,
    SERVICE_TOGGLE,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    SERVICE_VOLUME_DOWN,
    SERVICE_VOLUME_MUTE,
    SERVICE_VOLUME_SET,
    SERVICE_VOLUME_UP,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .conftest import CHILD_SPEAKER, CHILD_TV, PLAYER, SetupPlayer, get_player, set_child_state

from tests.common import async_mock_service


async def test_state_is_off_without_children(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
) -> None:
    """A player with no children and no overrides reports off."""
    await setup_player()

    state = hass.states.get(PLAYER)
    assert state is not None
    assert state.state == STATE_OFF


@pytest.mark.parametrize(
    ("tv_state", "speaker_state", "expected_child"),
    [
        (MediaPlayerState.PLAYING, MediaPlayerState.PAUSED, CHILD_TV),
        (MediaPlayerState.PAUSED, MediaPlayerState.PLAYING, CHILD_SPEAKER),
        (MediaPlayerState.IDLE, MediaPlayerState.IDLE, CHILD_TV),
        (MediaPlayerState.OFF, MediaPlayerState.IDLE, CHILD_SPEAKER),
        (MediaPlayerState.BUFFERING, MediaPlayerState.ON, CHILD_TV),
    ],
)
async def test_active_child_is_the_most_active_one(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
    tv_state: str,
    speaker_state: str,
    expected_child: str,
) -> None:
    """The child whose state ranks highest becomes the active one."""
    await setup_player(**{CONF_CHILDREN: [CHILD_TV, CHILD_SPEAKER]})

    await set_child_state(hass, CHILD_TV, tv_state)
    await set_child_state(hass, CHILD_SPEAKER, speaker_state)

    state = hass.states.get(PLAYER)
    assert state is not None
    assert state.attributes[ATTR_ACTIVE_CHILD] == expected_child


@pytest.mark.parametrize("child_state", [MediaPlayerState.OFF, STATE_UNAVAILABLE, STATE_UNKNOWN])
async def test_children_below_idle_are_never_active(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
    child_state: str,
) -> None:
    """A child that is off, unavailable or unknown is not picked as active."""
    await setup_player(**{CONF_CHILDREN: [CHILD_TV]})

    await set_child_state(hass, CHILD_TV, child_state)

    state = hass.states.get(PLAYER)
    assert state is not None
    assert ATTR_ACTIVE_CHILD not in state.attributes
    assert state.state == STATE_OFF


async def test_unknown_child_entity_is_ignored(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
) -> None:
    """A child that has no state at all is skipped."""
    await setup_player(**{CONF_CHILDREN: ["media_player.does_not_exist", CHILD_TV]})

    await set_child_state(hass, CHILD_TV, MediaPlayerState.PLAYING)

    state = hass.states.get(PLAYER)
    assert state.attributes[ATTR_ACTIVE_CHILD] == CHILD_TV


async def test_state_follows_the_active_child(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
) -> None:
    """The player mirrors the active child's state, and updates with it."""
    await setup_player(**{CONF_CHILDREN: [CHILD_TV]})

    await set_child_state(hass, CHILD_TV, MediaPlayerState.PLAYING)
    assert hass.states.get(PLAYER).state == MediaPlayerState.PLAYING

    await set_child_state(hass, CHILD_TV, MediaPlayerState.PAUSED)
    assert hass.states.get(PLAYER).state == MediaPlayerState.PAUSED


async def test_state_attribute_override_wins_over_children(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
) -> None:
    """An off master state shuts the player off whatever the children do."""
    await setup_player(
        **{
            CONF_CHILDREN: [CHILD_TV],
            CONF_ATTRS: {CONF_STATE: "switch.amplifier"},
        },
    )

    await set_child_state(hass, CHILD_TV, MediaPlayerState.PLAYING)
    await set_child_state(hass, "switch.amplifier", STATE_OFF)

    assert hass.states.get(PLAYER).state == STATE_OFF

    # A master state that isn't off hands control back to the active child.
    await set_child_state(hass, "switch.amplifier", STATE_ON)

    assert hass.states.get(PLAYER).state == MediaPlayerState.PLAYING


async def test_state_attribute_override_without_children(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
) -> None:
    """Without an active child the master state is reported as-is."""
    await setup_player(**{CONF_ATTRS: {CONF_STATE: "switch.amplifier"}})

    await set_child_state(hass, "switch.amplifier", STATE_ON)

    assert hass.states.get(PLAYER).state == STATE_ON


async def test_missing_state_override_entity_falls_back_to_off(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
) -> None:
    """A state override pointing at a missing entity reads as off."""
    await setup_player(**{CONF_ATTRS: {CONF_STATE: "switch.does_not_exist"}})

    assert hass.states.get(PLAYER).state == STATE_OFF


async def test_state_template_overrides_everything(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
) -> None:
    """A state template is used verbatim, ignoring the active child."""
    await setup_player(
        **{
            CONF_CHILDREN: [CHILD_TV],
            CONF_STATE_TEMPLATE: "{{ states('input_select.player_state') }}",
        },
    )

    await set_child_state(hass, CHILD_TV, MediaPlayerState.PLAYING)
    await set_child_state(hass, "input_select.player_state", "paused")

    assert hass.states.get(PLAYER).state == MediaPlayerState.PAUSED

    await set_child_state(hass, "input_select.player_state", "playing")

    assert hass.states.get(PLAYER).state == MediaPlayerState.PLAYING


async def test_templates_are_refreshed_when_home_assistant_starts(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
) -> None:
    """Templates rendered before startup are refreshed on the start event."""
    hass.states.async_set("input_select.player_state", "playing")

    await setup_player(
        **{CONF_STATE_TEMPLATE: "{{ states('input_select.player_state') }}"},
    )

    hass.bus.async_fire(EVENT_HOMEASSISTANT_START)
    await hass.async_block_till_done()

    assert hass.states.get(PLAYER).state == MediaPlayerState.PLAYING


async def test_active_child_template_selects_the_child(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
) -> None:
    """The active child template picks the child, bypassing the state ranking."""
    await setup_player(
        **{
            CONF_CHILDREN: [CHILD_TV, CHILD_SPEAKER],
            CONF_ACTIVE_CHILD_TEMPLATE: "{{ states('input_text.active_child') }}",
        },
    )

    await set_child_state(hass, CHILD_TV, MediaPlayerState.PLAYING)
    await set_child_state(hass, CHILD_SPEAKER, MediaPlayerState.OFF)
    await set_child_state(hass, "input_text.active_child", CHILD_SPEAKER)

    state = hass.states.get(PLAYER)
    assert state.attributes[ATTR_ACTIVE_CHILD] == CHILD_SPEAKER
    assert state.state == MediaPlayerState.OFF


CHILD_ATTRIBUTES: dict[str, Any] = {
    ATTR_MEDIA_VOLUME_LEVEL: 0.5,
    ATTR_MEDIA_VOLUME_MUTED: False,
    ATTR_MEDIA_CONTENT_ID: "content-id",
    ATTR_MEDIA_CONTENT_TYPE: MediaType.MUSIC,
    ATTR_MEDIA_DURATION: 300,
    ATTR_MEDIA_POSITION: 42,
    ATTR_MEDIA_TITLE: "A title",
    ATTR_MEDIA_ARTIST: "An artist",
    ATTR_MEDIA_ALBUM_NAME: "An album",
    ATTR_MEDIA_ALBUM_ARTIST: "An album artist",
    ATTR_MEDIA_TRACK: 3,
    ATTR_MEDIA_SERIES_TITLE: "A series",
    ATTR_MEDIA_SEASON: "1",
    ATTR_MEDIA_EPISODE: "2",
    ATTR_MEDIA_CHANNEL: "A channel",
    ATTR_MEDIA_PLAYLIST: "A playlist",
    ATTR_APP_ID: "app-id",
    ATTR_APP_NAME: "An app",
    ATTR_INPUT_SOURCE: "HDMI 1",
    ATTR_INPUT_SOURCE_LIST: ["HDMI 1", "HDMI 2"],
    ATTR_SOUND_MODE: "Movie",
    ATTR_SOUND_MODE_LIST: ["Movie", "Music"],
    ATTR_MEDIA_SHUFFLE: True,
    ATTR_MEDIA_REPEAT: RepeatMode.ALL,
    ATTR_ASSUMED_STATE: True,
    ATTR_ENTITY_PICTURE: "https://example.com/cover.png",
}


@pytest.mark.parametrize(
    ("attribute", "expected"),
    [
        (ATTR_MEDIA_VOLUME_LEVEL, 0.5),
        (ATTR_MEDIA_VOLUME_MUTED, False),
        (ATTR_MEDIA_CONTENT_ID, "content-id"),
        (ATTR_MEDIA_CONTENT_TYPE, MediaType.MUSIC),
        (ATTR_MEDIA_DURATION, 300),
        (ATTR_MEDIA_POSITION, 42),
        (ATTR_MEDIA_TITLE, "A title"),
        (ATTR_MEDIA_ARTIST, "An artist"),
        (ATTR_MEDIA_ALBUM_NAME, "An album"),
        (ATTR_MEDIA_ALBUM_ARTIST, "An album artist"),
        (ATTR_MEDIA_TRACK, 3),
        (ATTR_MEDIA_SERIES_TITLE, "A series"),
        (ATTR_MEDIA_SEASON, "1"),
        (ATTR_MEDIA_EPISODE, "2"),
        (ATTR_MEDIA_CHANNEL, "A channel"),
        (ATTR_MEDIA_PLAYLIST, "A playlist"),
        (ATTR_APP_ID, "app-id"),
        (ATTR_APP_NAME, "An app"),
        (ATTR_INPUT_SOURCE, "HDMI 1"),
        (ATTR_SOUND_MODE, "Movie"),
        (ATTR_MEDIA_SHUFFLE, True),
        (ATTR_MEDIA_REPEAT, RepeatMode.ALL),
    ],
)
async def test_active_child_attributes_are_published(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
    attribute: str,
    expected: Any,
) -> None:
    """The player republishes the attributes of its active child."""
    await setup_player(**{CONF_CHILDREN: [CHILD_TV]})

    await set_child_state(hass, CHILD_TV, MediaPlayerState.PLAYING, **CHILD_ATTRIBUTES)

    assert hass.states.get(PLAYER).attributes[attribute] == expected


async def test_child_only_attributes(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
) -> None:
    """assumed_state and the source list come from the active child."""
    await setup_player(**{CONF_CHILDREN: [CHILD_TV]})

    await set_child_state(hass, CHILD_TV, MediaPlayerState.PLAYING, **CHILD_ATTRIBUTES)

    player = get_player(hass)
    assert player.assumed_state is True
    assert player.source_list == ["HDMI 1", "HDMI 2"]
    assert player.sound_mode_list == ["Movie", "Music"]
    assert player.media_content_id == "content-id"


async def test_attributes_are_empty_without_an_active_child(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
) -> None:
    """Every child-backed attribute reads as None when no child is active."""
    await setup_player(**{CONF_CHILDREN: [CHILD_TV]})

    player = get_player(hass)
    assert player.assumed_state is None
    assert player.volume_level is None
    assert player.media_title is None
    assert player.source_list is None
    assert player.extra_state_attributes == {}


async def test_attribute_override_reads_another_entity_state(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
) -> None:
    """An override without an attribute name reads the entity's state."""
    await setup_player(
        **{
            CONF_CHILDREN: [CHILD_TV],
            CONF_ATTRS: {ATTR_MEDIA_VOLUME_LEVEL: "number.amplifier_volume"},
        },
    )

    await set_child_state(hass, CHILD_TV, MediaPlayerState.PLAYING, **CHILD_ATTRIBUTES)
    await set_child_state(hass, "number.amplifier_volume", "0.8")

    assert hass.states.get(PLAYER).attributes[ATTR_MEDIA_VOLUME_LEVEL] == 0.8


async def test_attribute_override_reads_another_entity_attribute(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
) -> None:
    """An "entity|attribute" override reads that attribute."""
    await setup_player(
        **{
            CONF_CHILDREN: [CHILD_TV],
            CONF_ATTRS: {ATTR_MEDIA_TITLE: f"{CHILD_SPEAKER}|{ATTR_MEDIA_TITLE}"},
        },
    )

    await set_child_state(hass, CHILD_TV, MediaPlayerState.PLAYING, **CHILD_ATTRIBUTES)
    await set_child_state(
        hass,
        CHILD_SPEAKER,
        MediaPlayerState.PLAYING,
        **{ATTR_MEDIA_TITLE: "Another title"},
    )

    assert hass.states.get(PLAYER).attributes[ATTR_MEDIA_TITLE] == "Another title"


async def test_attribute_override_falls_through_to_the_next_entity(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
) -> None:
    """Dash-separated entities are tried in order until one has the attribute."""
    await setup_player(
        **{
            CONF_CHILDREN: [CHILD_TV],
            CONF_ATTRS: {
                ATTR_MEDIA_TITLE: f"media_player.missing-{CHILD_SPEAKER}-{CHILD_TV}|{ATTR_MEDIA_TITLE}",
            },
        },
    )

    await set_child_state(hass, CHILD_TV, MediaPlayerState.PLAYING, **CHILD_ATTRIBUTES)
    await set_child_state(hass, CHILD_SPEAKER, MediaPlayerState.OFF)

    # The first entity has no state and the second one no title, so the title
    # comes from the third one.
    assert hass.states.get(PLAYER).attributes[ATTR_MEDIA_TITLE] == "A title"


async def test_attribute_override_without_any_match(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
) -> None:
    """An override that matches nothing leaves the attribute out."""
    await setup_player(
        **{
            CONF_CHILDREN: [CHILD_TV],
            CONF_ATTRS: {ATTR_MEDIA_TITLE: f"media_player.missing|{ATTR_MEDIA_TITLE}"},
        },
    )

    await set_child_state(hass, CHILD_TV, MediaPlayerState.PLAYING, **CHILD_ATTRIBUTES)

    assert ATTR_MEDIA_TITLE not in hass.states.get(PLAYER).attributes


@pytest.mark.parametrize("volume", ["not-a-number", None])
async def test_unparseable_volume_level_reads_as_none(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
    volume: Any,
) -> None:
    """A volume level that isn't a number is dropped rather than crashing."""
    await setup_player(**{CONF_CHILDREN: [CHILD_TV]})

    await set_child_state(
        hass,
        CHILD_TV,
        MediaPlayerState.PLAYING,
        **{ATTR_MEDIA_VOLUME_LEVEL: volume},
    )

    assert get_player(hass).volume_level is None


@pytest.mark.parametrize(
    ("muted", "expected"),
    [(True, True), (STATE_ON, True), (False, False), ("anything else", False), (None, False)],
)
async def test_is_volume_muted(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
    muted: Any,
    expected: bool,
) -> None:
    """Only True and "on" count as muted."""
    await setup_player(**{CONF_CHILDREN: [CHILD_TV]})

    await set_child_state(
        hass,
        CHILD_TV,
        MediaPlayerState.PLAYING,
        **{ATTR_MEDIA_VOLUME_MUTED: muted},
    )

    assert get_player(hass).is_volume_muted is expected


async def test_media_position_updated_at_is_forwarded(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
) -> None:
    """The position timestamp of the active child is forwarded as-is."""
    updated_at = dt_util.utcnow()

    await setup_player(**{CONF_CHILDREN: [CHILD_TV]})
    await set_child_state(
        hass,
        CHILD_TV,
        MediaPlayerState.PLAYING,
        **{ATTR_MEDIA_POSITION_UPDATED_AT: updated_at},
    )

    assert get_player(hass).media_position_updated_at == updated_at


async def test_entity_picture_mirrors_the_media_image(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
) -> None:
    """The entity picture is the child's picture, not a re-proxied one."""
    await setup_player(**{CONF_CHILDREN: [CHILD_TV]})
    await set_child_state(hass, CHILD_TV, MediaPlayerState.PLAYING, **CHILD_ATTRIBUTES)

    player = get_player(hass)
    assert player.entity_picture == "https://example.com/cover.png"
    assert player.media_image_url == "https://example.com/cover.png"


@pytest.mark.parametrize(
    ("picture", "proxied"),
    [
        ("http://example.com/cover.png", True),
        ("https://example.com/cover.png", False),
        ("/api/media_player_proxy/media_player.living_room_tv", False),
    ],
)
async def test_only_plain_http_pictures_are_proxied_locally(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
    picture: str,
    proxied: bool,
) -> None:
    """Only a remote http picture is republished through the local proxy."""
    await setup_player(**{CONF_CHILDREN: [CHILD_TV]})
    await set_child_state(
        hass,
        CHILD_TV,
        MediaPlayerState.PLAYING,
        **{ATTR_ENTITY_PICTURE: picture},
    )

    attributes = hass.states.get(PLAYER).attributes
    assert (ATTR_ENTITY_PICTURE_LOCAL in attributes) is proxied
    if proxied:
        assert attributes[ATTR_ENTITY_PICTURE_LOCAL].startswith("/api/media_player_proxy/")


async def test_state_attributes_are_dropped_when_off(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
) -> None:
    """A player that is off publishes no media attributes."""
    await setup_player(
        **{
            CONF_CHILDREN: [CHILD_TV],
            CONF_ATTRS: {CONF_STATE: "switch.amplifier"},
        },
    )

    await set_child_state(hass, CHILD_TV, MediaPlayerState.PLAYING, **CHILD_ATTRIBUTES)
    await set_child_state(hass, "switch.amplifier", STATE_OFF)

    attributes = hass.states.get(PLAYER).attributes
    assert ATTR_MEDIA_TITLE not in attributes
    assert ATTR_MEDIA_VOLUME_LEVEL not in attributes


def _command(action: str, entity_id: str = CHILD_SPEAKER) -> dict[str, Any]:
    """Build a plain command override.

    Args:
        action: The action the command triggers.
        entity_id: The entity the command targets.

    Returns:
        A command dict as the config flow stores it.

    """
    return {"action": action, "target": {ATTR_ENTITY_ID: entity_id}}


async def test_supported_features_come_from_the_active_child(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
) -> None:
    """The child's own features are forwarded, minus the ones we re-derive."""
    await setup_player(**{CONF_CHILDREN: [CHILD_TV]})

    await set_child_state(
        hass,
        CHILD_TV,
        MediaPlayerState.PLAYING,
        **{
            ATTR_SUPPORTED_FEATURES: MediaPlayerEntityFeature.PLAY
            | MediaPlayerEntityFeature.GROUPING
            | MediaPlayerEntityFeature.BROWSE_MEDIA,
        },
    )

    features = get_player(hass).supported_features
    assert MediaPlayerEntityFeature.PLAY in features
    # Grouping and browsing are only offered when this integration can back them.
    assert MediaPlayerEntityFeature.GROUPING not in features
    assert MediaPlayerEntityFeature.BROWSE_MEDIA not in features


@pytest.mark.parametrize(
    ("commands", "attributes", "expected"),
    [
        ([SERVICE_TURN_ON], {}, MediaPlayerEntityFeature.TURN_ON),
        ([SERVICE_TURN_OFF], {}, MediaPlayerEntityFeature.TURN_OFF),
        (
            [SERVICE_MEDIA_PLAY_PAUSE],
            {},
            MediaPlayerEntityFeature.PLAY | MediaPlayerEntityFeature.PAUSE,
        ),
        ([SERVICE_MEDIA_PLAY], {}, MediaPlayerEntityFeature.PLAY),
        ([SERVICE_MEDIA_PAUSE], {}, MediaPlayerEntityFeature.PAUSE),
        ([SERVICE_MEDIA_STOP], {}, MediaPlayerEntityFeature.STOP),
        ([SERVICE_MEDIA_NEXT_TRACK], {}, MediaPlayerEntityFeature.NEXT_TRACK),
        ([SERVICE_MEDIA_PREVIOUS_TRACK], {}, MediaPlayerEntityFeature.PREVIOUS_TRACK),
        ([SERVICE_VOLUME_UP], {}, MediaPlayerEntityFeature.VOLUME_STEP),
        ([SERVICE_VOLUME_DOWN], {}, MediaPlayerEntityFeature.VOLUME_STEP),
        ([SERVICE_VOLUME_SET], {}, MediaPlayerEntityFeature.VOLUME_SET),
        ("join", {}, MediaPlayerEntityFeature.GROUPING),
        ("play_media", {}, MediaPlayerEntityFeature.PLAY_MEDIA),
        ("clear_playlist", {}, MediaPlayerEntityFeature.CLEAR_PLAYLIST),
        (
            [SERVICE_VOLUME_MUTE],
            {ATTR_MEDIA_VOLUME_MUTED: CHILD_TV},
            MediaPlayerEntityFeature.VOLUME_MUTE,
        ),
        (
            ["select_source"],
            {ATTR_INPUT_SOURCE_LIST: CHILD_TV},
            MediaPlayerEntityFeature.SELECT_SOURCE,
        ),
        (
            ["select_sound_mode"],
            {ATTR_SOUND_MODE_LIST: CHILD_TV},
            MediaPlayerEntityFeature.SELECT_SOUND_MODE,
        ),
        (
            [SERVICE_SHUFFLE_SET],
            {ATTR_MEDIA_SHUFFLE: CHILD_TV},
            MediaPlayerEntityFeature.SHUFFLE_SET,
        ),
        (
            [SERVICE_REPEAT_SET],
            {ATTR_MEDIA_REPEAT: CHILD_TV},
            MediaPlayerEntityFeature.REPEAT_SET,
        ),
    ],
)
async def test_commands_add_supported_features(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
    commands: list[str] | str,
    attributes: dict[str, str],
    expected: MediaPlayerEntityFeature,
) -> None:
    """A configured command advertises the feature it implements."""
    keys = [commands] if isinstance(commands, str) else commands

    await setup_player(
        **{
            CONF_COMMANDS: {key: _command(f"{MEDIA_PLAYER_DOMAIN}.{key}") for key in keys},
            CONF_ATTRS: attributes,
        },
    )

    assert expected in get_player(hass).supported_features


@pytest.mark.parametrize(
    ("command", "attribute"),
    [
        (SERVICE_VOLUME_MUTE, MediaPlayerEntityFeature.VOLUME_MUTE),
        ("select_source", MediaPlayerEntityFeature.SELECT_SOURCE),
        ("select_sound_mode", MediaPlayerEntityFeature.SELECT_SOUND_MODE),
        (SERVICE_SHUFFLE_SET, MediaPlayerEntityFeature.SHUFFLE_SET),
        (SERVICE_REPEAT_SET, MediaPlayerEntityFeature.REPEAT_SET),
    ],
)
async def test_commands_needing_an_attribute_override(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
    command: str,
    attribute: MediaPlayerEntityFeature,
) -> None:
    """A command whose state is read from an override needs that override."""
    await setup_player(
        **{CONF_COMMANDS: {command: _command(f"{MEDIA_PLAYER_DOMAIN}.{command}")}},
    )

    assert attribute not in get_player(hass).supported_features


async def test_browse_media_entity_advertises_browsing(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
) -> None:
    """Configuring a browse media entity turns the browse feature back on."""
    await setup_player(**{CONF_BROWSE_MEDIA_ENTITY: CHILD_SPEAKER})

    assert MediaPlayerEntityFeature.BROWSE_MEDIA in get_player(hass).supported_features


@pytest.mark.parametrize(
    ("method", "arguments", "service", "expected_data"),
    [
        ("async_turn_on", (), SERVICE_TURN_ON, {}),
        ("async_turn_off", (), SERVICE_TURN_OFF, {}),
        ("async_media_play", (), SERVICE_MEDIA_PLAY, {}),
        ("async_media_pause", (), SERVICE_MEDIA_PAUSE, {}),
        ("async_media_stop", (), SERVICE_MEDIA_STOP, {}),
        ("async_media_play_pause", (), SERVICE_MEDIA_PLAY_PAUSE, {}),
        ("async_media_next_track", (), SERVICE_MEDIA_NEXT_TRACK, {}),
        ("async_media_previous_track", (), SERVICE_MEDIA_PREVIOUS_TRACK, {}),
        ("async_volume_up", (), SERVICE_VOLUME_UP, {}),
        ("async_volume_down", (), SERVICE_VOLUME_DOWN, {}),
        ("async_clear_playlist", (), "clear_playlist", {}),
        ("async_unjoin_player", (), "unjoin", {}),
        ("async_mute_volume", (True,), SERVICE_VOLUME_MUTE, {ATTR_MEDIA_VOLUME_MUTED: True}),
        ("async_set_volume_level", (0.4,), SERVICE_VOLUME_SET, {ATTR_MEDIA_VOLUME_LEVEL: 0.4}),
        ("async_media_seek", (12,), SERVICE_MEDIA_SEEK, {"seek_position": 12}),
        ("async_set_shuffle", (True,), SERVICE_SHUFFLE_SET, {ATTR_MEDIA_SHUFFLE: True}),
        (
            "async_set_repeat",
            (RepeatMode.ONE,),
            SERVICE_REPEAT_SET,
            {ATTR_MEDIA_REPEAT: RepeatMode.ONE},
        ),
        ("async_select_source", ("HDMI 2",), "select_source", {ATTR_INPUT_SOURCE: "HDMI 2"}),
        (
            "async_select_sound_mode",
            ("Music",),
            "select_sound_mode",
            {ATTR_SOUND_MODE: "Music"},
        ),
    ],
)
async def test_commands_are_forwarded_to_the_active_child(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
    method: str,
    arguments: tuple[Any, ...],
    service: str,
    expected_data: dict[str, Any],
) -> None:
    """Without an override, a command is sent to the active child."""
    await setup_player(**{CONF_CHILDREN: [CHILD_TV]})
    await set_child_state(hass, CHILD_TV, MediaPlayerState.PLAYING)

    calls = async_mock_service(hass, MEDIA_PLAYER_DOMAIN, service)

    await getattr(get_player(hass), method)(*arguments)
    await hass.async_block_till_done()

    assert len(calls) == 1
    assert calls[0].data == {ATTR_ENTITY_ID: CHILD_TV, **expected_data}


async def test_play_media_is_forwarded_to_the_active_child(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
) -> None:
    """play_media carries its content type and id to the active child."""
    await setup_player(**{CONF_CHILDREN: [CHILD_TV]})
    await set_child_state(hass, CHILD_TV, MediaPlayerState.PLAYING)

    calls = async_mock_service(hass, MEDIA_PLAYER_DOMAIN, "play_media")

    await get_player(hass).async_play_media(MediaType.MUSIC, "content-id")
    await hass.async_block_till_done()

    assert len(calls) == 1
    assert calls[0].data[ATTR_MEDIA_CONTENT_TYPE] == MediaType.MUSIC
    assert calls[0].data[ATTR_MEDIA_CONTENT_ID] == "content-id"
    assert calls[0].data[ATTR_ENTITY_ID] == CHILD_TV


async def test_commands_are_dropped_without_an_active_child(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
) -> None:
    """With no active child and no override there is nothing to call."""
    await setup_player(**{CONF_CHILDREN: [CHILD_TV]})

    calls = async_mock_service(hass, MEDIA_PLAYER_DOMAIN, SERVICE_TURN_ON)

    await get_player(hass).async_turn_on()
    await hass.async_block_till_done()

    assert calls == []


async def test_override_replaces_the_child_call(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
) -> None:
    """A command override is called instead of the active child."""
    await setup_player(
        **{
            CONF_CHILDREN: [CHILD_TV],
            CONF_COMMANDS: {
                SERVICE_TURN_ON: {
                    "action": "script.turn_on",
                    "target": {ATTR_ENTITY_ID: "script.start_everything"},
                },
            },
        },
    )
    await set_child_state(hass, CHILD_TV, MediaPlayerState.PLAYING)

    media_player_calls = async_mock_service(hass, MEDIA_PLAYER_DOMAIN, SERVICE_TURN_ON)
    script_calls = async_mock_service(hass, "script", SERVICE_TURN_ON)

    await get_player(hass).async_turn_on()
    await hass.async_block_till_done()

    assert media_player_calls == []
    assert len(script_calls) == 1
    assert script_calls[0].data[ATTR_ENTITY_ID] == ["script.start_everything"]


async def test_pass_through_override_receives_the_call_data(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
) -> None:
    """An override onto the same media_player action keeps the call's data."""
    await setup_player(
        **{
            CONF_CHILDREN: [CHILD_TV],
            CONF_COMMANDS: {SERVICE_VOLUME_SET: _command(f"{MEDIA_PLAYER_DOMAIN}.{SERVICE_VOLUME_SET}")},
        },
    )
    await set_child_state(hass, CHILD_TV, MediaPlayerState.PLAYING)

    calls = async_mock_service(hass, MEDIA_PLAYER_DOMAIN, SERVICE_VOLUME_SET)

    await get_player(hass).async_set_volume_level(0.4)
    await hass.async_block_till_done()

    assert len(calls) == 1
    assert calls[0].data[ATTR_ENTITY_ID] == [CHILD_SPEAKER]
    assert calls[0].data[ATTR_MEDIA_VOLUME_LEVEL] == 0.4


async def test_override_data_wins_over_the_call_data(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
) -> None:
    """An explicit key in the override's data takes priority."""
    await setup_player(
        **{
            CONF_CHILDREN: [CHILD_TV],
            CONF_COMMANDS: {
                SERVICE_VOLUME_SET: {
                    "action": f"{MEDIA_PLAYER_DOMAIN}.{SERVICE_VOLUME_SET}",
                    "target": {ATTR_ENTITY_ID: CHILD_SPEAKER},
                    "data": {ATTR_MEDIA_VOLUME_LEVEL: 0.1},
                },
            },
        },
    )
    await set_child_state(hass, CHILD_TV, MediaPlayerState.PLAYING)

    calls = async_mock_service(hass, MEDIA_PLAYER_DOMAIN, SERVICE_VOLUME_SET)

    await get_player(hass).async_set_volume_level(0.4)
    await hass.async_block_till_done()

    assert calls[0].data[ATTR_MEDIA_VOLUME_LEVEL] == 0.1


async def test_override_onto_another_domain_only_gets_its_own_data(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
) -> None:
    """A non pass-through override receives its own data, templated."""
    await setup_player(
        **{
            CONF_CHILDREN: [CHILD_TV],
            CONF_COMMANDS: {
                SERVICE_VOLUME_SET: {
                    "action": "number.set_value",
                    "target": {ATTR_ENTITY_ID: "number.amplifier_volume"},
                    "data": {"value": "{{ volume_level * 100 }}"},
                },
            },
        },
    )
    await set_child_state(hass, CHILD_TV, MediaPlayerState.PLAYING)

    calls = async_mock_service(hass, "number", "set_value")

    await get_player(hass).async_set_volume_level(0.4)
    await hass.async_block_till_done()

    assert len(calls) == 1
    # The call's own data would be rejected as extra keys by number.set_value.
    assert ATTR_MEDIA_VOLUME_LEVEL not in calls[0].data
    assert calls[0].data["value"] == pytest.approx(40)


async def test_override_without_a_target_uses_the_active_child(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
) -> None:
    """An override that names no target falls back to the active child."""
    await setup_player(
        **{
            CONF_CHILDREN: [CHILD_TV],
            CONF_COMMANDS: {SERVICE_TURN_ON: {"action": f"{MEDIA_PLAYER_DOMAIN}.{SERVICE_TURN_ON}"}},
        },
    )
    await set_child_state(hass, CHILD_TV, MediaPlayerState.PLAYING)

    calls = async_mock_service(hass, MEDIA_PLAYER_DOMAIN, SERVICE_TURN_ON)

    await get_player(hass).async_turn_on()
    await hass.async_block_till_done()

    assert calls[0].data[ATTR_ENTITY_ID] == [CHILD_TV]


async def test_legacy_service_key_still_passes_data_through(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
) -> None:
    """A command stored under the legacy "service" key behaves the same."""
    await setup_player(
        **{
            CONF_CHILDREN: [CHILD_TV],
            CONF_COMMANDS: {
                SERVICE_VOLUME_SET: {
                    "service": f"{MEDIA_PLAYER_DOMAIN}.{SERVICE_VOLUME_SET}",
                    "target": {ATTR_ENTITY_ID: CHILD_SPEAKER},
                },
            },
        },
    )
    await set_child_state(hass, CHILD_TV, MediaPlayerState.PLAYING)

    calls = async_mock_service(hass, MEDIA_PLAYER_DOMAIN, SERVICE_VOLUME_SET)

    await get_player(hass).async_set_volume_level(0.4)
    await hass.async_block_till_done()

    assert calls[0].data[ATTR_MEDIA_VOLUME_LEVEL] == 0.4


async def test_templated_action_is_never_a_pass_through(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
) -> None:
    """A command whose action is a template gets no merged call data."""
    await setup_player(
        **{
            CONF_CHILDREN: [CHILD_TV],
            CONF_COMMANDS: {
                SERVICE_VOLUME_SET: {
                    "action": "{{ 'media_player.volume_set' }}",
                    "target": {ATTR_ENTITY_ID: CHILD_SPEAKER},
                },
            },
        },
    )
    await set_child_state(hass, CHILD_TV, MediaPlayerState.PLAYING)

    calls = async_mock_service(hass, MEDIA_PLAYER_DOMAIN, SERVICE_VOLUME_SET)

    await get_player(hass).async_set_volume_level(0.4)
    await hass.async_block_till_done()

    assert len(calls) == 1
    assert ATTR_MEDIA_VOLUME_LEVEL not in calls[0].data


async def test_seek_ignores_command_overrides(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
) -> None:
    """media_seek always goes to the active child."""
    await setup_player(
        **{
            CONF_CHILDREN: [CHILD_TV],
            CONF_COMMANDS: {SERVICE_MEDIA_SEEK: _command("script.turn_on", "script.seek")},
        },
    )
    await set_child_state(hass, CHILD_TV, MediaPlayerState.PLAYING)

    calls = async_mock_service(hass, MEDIA_PLAYER_DOMAIN, SERVICE_MEDIA_SEEK)
    script_calls = async_mock_service(hass, "script", SERVICE_TURN_ON)

    await get_player(hass).async_media_seek(30)
    await hass.async_block_till_done()

    assert script_calls == []
    assert calls[0].data[ATTR_ENTITY_ID] == CHILD_TV


async def test_toggle_uses_its_override(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
) -> None:
    """A toggle command is used instead of turning on or off."""
    await setup_player(
        **{
            CONF_CHILDREN: [CHILD_TV],
            CONF_COMMANDS: {SERVICE_TOGGLE: _command("script.turn_on", "script.toggle_everything")},
        },
    )
    await set_child_state(hass, CHILD_TV, MediaPlayerState.PLAYING)

    script_calls = async_mock_service(hass, "script", SERVICE_TURN_ON)

    await get_player(hass).async_toggle()
    await hass.async_block_till_done()

    assert len(script_calls) == 1
    assert script_calls[0].data[ATTR_ENTITY_ID] == ["script.toggle_everything"]


async def test_toggle_without_an_override_turns_on_or_off(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
) -> None:
    """Without a toggle command, toggling delegates to turn_on/turn_off."""
    await setup_player(**{CONF_CHILDREN: [CHILD_TV]})
    await set_child_state(hass, CHILD_TV, MediaPlayerState.PLAYING)

    turn_off_calls = async_mock_service(hass, MEDIA_PLAYER_DOMAIN, SERVICE_TURN_OFF)

    await get_player(hass).async_toggle()
    await hass.async_block_till_done()

    assert len(turn_off_calls) == 1
    assert turn_off_calls[0].data[ATTR_ENTITY_ID] == CHILD_TV


def _browse_media_entity(browsed: BrowseMedia | None = None) -> Mock:
    """Build a stand-in media player entity that can browse media.

    Args:
        browsed: The browse result the entity returns.

    Returns:
        A mock entity whose async_browse_media returns ``browsed``.

    """
    entity = Mock()
    entity.async_browse_media = AsyncMock(return_value=browsed)
    return entity


async def test_join_resolves_virtual_group_members(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
) -> None:
    """Joining maps other universal players onto their own active child."""
    await setup_player(
        **{
            CONF_CHILDREN: [CHILD_TV],
            CONF_COMMANDS: {"join": _command(f"{MEDIA_PLAYER_DOMAIN}.join", CHILD_TV)},
        },
    )
    await set_child_state(hass, CHILD_TV, MediaPlayerState.PLAYING)
    await set_child_state(
        hass,
        "media_player.kitchen_universal",
        MediaPlayerState.PLAYING,
        **{ATTR_ACTIVE_CHILD: CHILD_SPEAKER},
    )

    calls = async_mock_service(hass, MEDIA_PLAYER_DOMAIN, "join")

    await get_player(hass).async_join_players(
        ["media_player.kitchen_universal", "media_player.a_real_speaker"],
    )
    await hass.async_block_till_done()

    assert len(calls) == 1
    assert calls[0].data[ATTR_GROUP_MEMBERS] == [CHILD_SPEAKER, "media_player.a_real_speaker"]


async def test_group_members_are_mapped_back_to_virtual_players(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
) -> None:
    """The group the child reports is expressed with the virtual players."""
    await setup_player(**{CONF_CHILDREN: [CHILD_TV]})

    await set_child_state(
        hass,
        CHILD_TV,
        MediaPlayerState.PLAYING,
        **{ATTR_GROUP_MEMBERS: [CHILD_TV, CHILD_SPEAKER, "media_player.a_real_speaker"]},
    )
    await set_child_state(
        hass,
        "media_player.kitchen_universal",
        MediaPlayerState.PLAYING,
        **{ATTR_ACTIVE_CHILD: CHILD_SPEAKER},
    )

    assert get_player(hass).group_members == [
        PLAYER,
        "media_player.kitchen_universal",
        "media_player.a_real_speaker",
    ]


@pytest.mark.parametrize("members", [None, []])
async def test_group_members_without_a_group(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
    members: list[str] | None,
) -> None:
    """A child that reports no group is passed straight through."""
    await setup_player(**{CONF_CHILDREN: [CHILD_TV]})
    await set_child_state(
        hass,
        CHILD_TV,
        MediaPlayerState.PLAYING,
        **{ATTR_GROUP_MEMBERS: members},
    )

    assert get_player(hass).group_members == members


async def test_browse_media_uses_the_configured_entity(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
) -> None:
    """Browsing is delegated to the configured browse media entity."""
    await setup_player(
        **{CONF_CHILDREN: [CHILD_TV], CONF_BROWSE_MEDIA_ENTITY: CHILD_SPEAKER},
    )
    await set_child_state(hass, CHILD_TV, MediaPlayerState.PLAYING)

    browsed = BrowseMedia(
        media_class=MediaClass.DIRECTORY,
        media_content_id="library",
        media_content_type=MediaType.MUSIC,
        title="Library",
        can_play=False,
        can_expand=True,
    )
    target = _browse_media_entity(browsed)

    player = get_player(hass)
    component = hass.data[MEDIA_PLAYER_DOMAIN]
    with patch.object(component, "get_entity", return_value=target) as get_entity:
        result = await player.async_browse_media(MediaType.MUSIC, "library")

    assert result is browsed
    assert get_entity.call_args.args == (CHILD_SPEAKER,)
    assert target.async_browse_media.await_args.args == (MediaType.MUSIC, "library")


async def test_browse_media_falls_back_to_the_active_child(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
) -> None:
    """Without a configured entity, browsing goes to the active child."""
    await setup_player(**{CONF_CHILDREN: [CHILD_TV]})
    await set_child_state(hass, CHILD_TV, MediaPlayerState.PLAYING)

    target = _browse_media_entity()

    player = get_player(hass)
    component = hass.data[MEDIA_PLAYER_DOMAIN]
    with patch.object(component, "get_entity", return_value=target) as get_entity:
        await player.async_browse_media()

    assert get_entity.call_args.args == (CHILD_TV,)


async def test_browse_media_without_a_target(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
) -> None:
    """Browsing with nothing to browse raises rather than returning nothing."""
    await setup_player(**{CONF_CHILDREN: [CHILD_TV]})

    with pytest.raises(NotImplementedError):
        await get_player(hass).async_browse_media()


async def test_browse_media_with_an_unknown_target(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
) -> None:
    """A browse media entity that isn't loaded raises rather than crashing."""
    await setup_player(**{CONF_BROWSE_MEDIA_ENTITY: "media_player.not_loaded"})

    with pytest.raises(NotImplementedError):
        await get_player(hass).async_browse_media()


async def test_async_update_refreshes_the_active_child(
    hass: HomeAssistant,
    setup_player: SetupPlayer,
) -> None:
    """The manual update entry point re-resolves the active child."""
    await setup_player(**{CONF_CHILDREN: [CHILD_TV]})

    # Set the state without letting the player see the event.
    hass.states.async_set(CHILD_TV, MediaPlayerState.PLAYING, {})

    player = get_player(hass)
    await player.async_update()

    assert player.extra_state_attributes == {ATTR_ACTIVE_CHILD: CHILD_TV}


async def test_yaml_platform_setup_starts_an_import_flow(hass: HomeAssistant) -> None:
    """The deprecated YAML platform only hands its config to the import flow."""
    config = {CONF_NAME: "Imported player", CONF_CHILDREN: [CHILD_TV]}

    with patch.object(hass.config_entries.flow, "async_init") as async_init:
        await async_setup_platform(hass, config, None)
        await hass.async_block_till_done()

    assert async_init.call_args.args == (DOMAIN,)
    assert async_init.call_args.kwargs["context"] == {"source": SOURCE_IMPORT}
    assert async_init.call_args.kwargs["data"] == config
