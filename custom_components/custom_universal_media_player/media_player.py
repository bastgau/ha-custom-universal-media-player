"""Combination of multiple media players for a custom universal controller."""

from __future__ import annotations

from copy import copy
from typing import TYPE_CHECKING, Any, override

import voluptuous as vol

from homeassistant.components.media_player import (
    DEVICE_CLASSES_SCHEMA,
    PLATFORM_SCHEMA as MEDIA_PLAYER_PLATFORM_SCHEMA,
    MediaPlayerEntity,
)
from homeassistant.components.media_player.const import (
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
    ATTR_MEDIA_SEEK_POSITION,
    ATTR_MEDIA_SERIES_TITLE,
    ATTR_MEDIA_SHUFFLE,
    ATTR_MEDIA_TITLE,
    ATTR_MEDIA_TRACK,
    ATTR_MEDIA_VOLUME_LEVEL,
    ATTR_MEDIA_VOLUME_MUTED,
    ATTR_SOUND_MODE,
    ATTR_SOUND_MODE_LIST,
    DOMAIN as MEDIA_PLAYER_DOMAIN,
    SERVICE_CLEAR_PLAYLIST,
    SERVICE_JOIN,
    SERVICE_PLAY_MEDIA,
    SERVICE_SELECT_SOUND_MODE,
    SERVICE_SELECT_SOURCE,
    SERVICE_UNJOIN,
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
    CONF_DEVICE_CLASS,
    CONF_NAME,
    CONF_STATE,
    CONF_STATE_TEMPLATE,
    CONF_UNIQUE_ID,
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
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import (
    TrackTemplate,
    TrackTemplateResult,
    async_track_state_change_event,
    async_track_template_result,
)
from homeassistant.helpers.service import async_call_from_config

from . import ATTR_ENTITY_PICTURE_LOCAL
from .const import (
    ATTR_ACTIVE_CHILD,
    CONF_ACTIVE_CHILD_TEMPLATE,
    CONF_ATTRS,
    CONF_BROWSE_MEDIA_ENTITY,
    CONF_CHILDREN,
    CONF_COMMANDS,
    DOMAIN,
)

if TYPE_CHECKING:
    from datetime import datetime

    from homeassistant.components.media_player.browse_media import BrowseMedia
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.helpers.entity_component import EntityComponent
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback, AddEntitiesCallback
    from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

ATTR_TO_PROPERTY = [
    ATTR_MEDIA_VOLUME_LEVEL,
    ATTR_MEDIA_VOLUME_MUTED,
    ATTR_MEDIA_CONTENT_ID,
    ATTR_MEDIA_CONTENT_TYPE,
    ATTR_MEDIA_DURATION,
    ATTR_MEDIA_POSITION,
    ATTR_MEDIA_POSITION_UPDATED_AT,
    ATTR_MEDIA_TITLE,
    ATTR_MEDIA_ARTIST,
    ATTR_MEDIA_ALBUM_NAME,
    ATTR_MEDIA_ALBUM_ARTIST,
    ATTR_MEDIA_TRACK,
    ATTR_MEDIA_SERIES_TITLE,
    ATTR_MEDIA_SEASON,
    ATTR_MEDIA_EPISODE,
    ATTR_MEDIA_CHANNEL,
    ATTR_MEDIA_PLAYLIST,
    ATTR_APP_ID,
    ATTR_APP_NAME,
    ATTR_INPUT_SOURCE,
    ATTR_SOUND_MODE,
    ATTR_MEDIA_SHUFFLE,
    ATTR_MEDIA_REPEAT,
]


STATES_ORDER = [
    STATE_UNKNOWN,
    STATE_UNAVAILABLE,
    MediaPlayerState.OFF,
    MediaPlayerState.IDLE,
    # Not using MediaPlayerState.STANDBY to avoid deprecation warning
    "standby",
    MediaPlayerState.ON,
    MediaPlayerState.PAUSED,
    MediaPlayerState.BUFFERING,
    MediaPlayerState.PLAYING,
]
STATES_ORDER_LOOKUP = {state: idx for idx, state in enumerate(STATES_ORDER)}
STATES_ORDER_IDLE = STATES_ORDER_LOOKUP[MediaPlayerState.IDLE]

ATTRS_SCHEMA: Any = cv.schema_with_slug_keys(cv.string)  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]  # pylint: disable=invalid-name
CMD_SCHEMA: Any = cv.schema_with_slug_keys(cv.SERVICE_SCHEMA)  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType] # pylint: disable=invalid-name

PLATFORM_SCHEMA = MEDIA_PLAYER_PLATFORM_SCHEMA.extend(  # pyright: ignore[reportUnknownMemberType]
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Optional(CONF_CHILDREN, default=[]): cv.entity_ids,  # pyright: ignore[reportUnknownMemberType]
        vol.Optional(CONF_COMMANDS, default={}): CMD_SCHEMA,
        vol.Optional(CONF_ATTRS, default={}): vol.Or(cv.ensure_list(ATTRS_SCHEMA), ATTRS_SCHEMA),
        vol.Optional(CONF_BROWSE_MEDIA_ENTITY): cv.string,
        vol.Optional(CONF_UNIQUE_ID): cv.string,
        vol.Optional(CONF_DEVICE_CLASS): DEVICE_CLASSES_SCHEMA,
        vol.Optional(CONF_ACTIVE_CHILD_TEMPLATE): cv.template,
        vol.Optional(CONF_STATE_TEMPLATE): cv.template,
    },
    extra=vol.REMOVE_EXTRA,
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,  # noqa: ARG001
    discovery_info: DiscoveryInfoType | None = None,  # pylint: disable=unused-argument  # noqa: ARG001
) -> None:
    """Import the YAML platform configuration into a config entry.

    This legacy entry point no longer creates entities directly. It only
    triggers a config flow import so existing YAML installs are migrated
    to a config entry (deprecated path, kept during the migration window).

    Args:
        hass: The Home Assistant instance.
        config: The platform configuration.
        async_add_entities: Unused; entities are added via async_setup_entry.
        discovery_info: Optional discovery information.

    """
    hass.async_create_task(
        hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_IMPORT}, data=config),
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the custom universal media player from a config entry.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry to set up.
        async_add_entities: Callback to register new entities.

    """
    config: dict[str, Any] = dict(entry.data)

    for key in (CONF_ACTIVE_CHILD_TEMPLATE, CONF_STATE_TEMPLATE):
        if isinstance(config.get(key), str):
            config[key] = cv.template(config[key])

    async_add_entities([CustomUniversalMediaPlayer(hass, config)])


class CustomUniversalMediaPlayer(MediaPlayerEntity):  # pylint: disable=too-many-public-methods,too-many-instance-attributes
    """Representation of a custom universal media player."""

    _attr_should_poll = False

    def __init__(
        self,
        hass: HomeAssistant,
        config: dict[str, Any],
    ) -> None:
        """Initialize the Custom universal media device.

        Args:
            hass: The Home Assistant instance.
            config: The platform configuration dictionary.

        """
        self.hass = hass
        self._attr_name = config.get(CONF_NAME)
        self._children = config.get(CONF_CHILDREN, [])
        self._active_child_template = config.get(CONF_ACTIVE_CHILD_TEMPLATE)
        self._active_child_template_result = None
        self._cmds = config.get(CONF_COMMANDS, {})
        self._attrs: dict[str, Any] = {}
        for key, val in config.get(CONF_ATTRS, {}).items():
            attr: list[str | None] = list(map(str.strip, val.split("|", 1)))
            if len(attr) == 1:
                attr.append(None)
            self._attrs[key] = attr
        self._child_state = None
        self._state_template_result = None
        self._state_template = config.get(CONF_STATE_TEMPLATE)
        self._attr_device_class = config.get(CONF_DEVICE_CLASS)
        self._attr_unique_id = config.get(CONF_UNIQUE_ID)
        self._browse_media_entity = config.get(CONF_BROWSE_MEDIA_ENTITY)

    @override
    async def async_added_to_hass(self) -> None:
        """Subscribe to children and template state changes."""

        @callback
        def _async_on_dependency_update(
            event: Event[EventStateChangedData],
        ) -> None:
            """Update ha state when dependencies update.

            Args:
                event: The state change event that triggered this callback.

            """
            self.async_set_context(event.context)
            self._async_update()
            self.async_write_ha_state()

        @callback
        def _async_on_template_update(
            event: Event[EventStateChangedData] | None,
            updates: list[TrackTemplateResult],
        ) -> None:
            """Update state when template state changes.

            Args:
                event: The state change event that triggered this callback, or None on init.
                updates: List of template results that have changed.

            """
            for data in updates:
                template = data.template
                result = data.result

                if template == self._state_template:
                    self._state_template_result = result if isinstance(result, str) else None
                if template == self._active_child_template:
                    self._active_child_template_result = result if isinstance(result, str) else None

            if event:
                self.async_set_context(event.context)

            self._async_update()
            self.async_write_ha_state()

        track_templates: list[TrackTemplate] = []
        if self._state_template:
            track_templates.append(TrackTemplate(self._state_template, None))
        if self._active_child_template:
            track_templates.append(TrackTemplate(self._active_child_template, None))

        if track_templates:
            result = async_track_template_result(
                self.hass,
                track_templates,
                _async_on_template_update,
            )
            self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, callback(lambda _: result.async_refresh()))

            self.async_on_remove(result.async_remove)

        depend: Any = copy(self._children)
        for entity in self._attrs.values():
            depend.append(entity[0])

        self.async_on_remove(async_track_state_change_event(self.hass, list(set(depend)), _async_on_dependency_update))

    def _entity_lkp(self, entity_id: str, state_attr: str | None = None) -> Any:
        """Look up an entity state or attribute value.

        Supports multiple entity IDs separated by '-'. Iterates through each
        and returns the first non-None value found.

        Args:
            entity_id: A single entity ID or multiple IDs joined by '-'.
            state_attr: Optional attribute name to retrieve instead of the state.

        Returns:
            The state string or attribute value of the first matching entity,
            or None if no match is found.

        """

        entities_id = entity_id.split("-")

        for current_entity_id in entities_id:
            if (state_obj := self.hass.states.get(current_entity_id)) is None:
                continue

            if state_attr:
                value = state_obj.attributes.get(state_attr)

                if value is not None:
                    return value

                continue

            return state_obj.state

        return None

    def _override_or_child_attr(self, attr_name: str) -> Any:
        """Return either the override or the active child for attr_name.

        If an attribute override is defined in the configuration for the given
        attribute name, the overridden entity value is returned. Otherwise, the
        attribute is retrieved from the active child entity.

        Args:
            attr_name: The name of the attribute to retrieve.

        Returns:
            The attribute value from the override entity or from the active child,
            or None if neither is available.

        """
        if attr_name in self._attrs:
            return self._entity_lkp(self._attrs[attr_name][0], self._attrs[attr_name][1])

        return self._child_attr(attr_name)

    def _child_attr(self, attr_name: str) -> Any:
        """Return the active child's attributes.

        Args:
            attr_name: The name of the attribute to retrieve from the active child.

        Returns:
            The attribute value from the active child entity, or None if there
            is no active child.

        """
        active_child = self._child_state
        return active_child.attributes.get(attr_name) if active_child else None

    async def _async_call_service(
        self,
        service_name: str,
        service_data: dict[str, Any] | None = None,
        allow_override: bool = False,
    ) -> None:
        """Call either a specified or active child's service.

        If allow_override is True and a command override is defined for the
        given service, the override is called instead of delegating to the
        active child. The call's own data (e.g. media_content_id for
        play_media, volume_level for volume_set) is merged into the
        override's data so it reaches the target service even if the
        override doesn't reference it via a Jinja2 template - an explicit
        key in the override's own data still takes priority. Likewise, if
        the override doesn't define its own target, it defaults to the
        active child, same as a non-overridden command would.

        Args:
            service_name: The name of the media player service to call.
            service_data: Optional dictionary of service call parameters.
            allow_override: Whether to check for a command override before
                falling back to the active child.

        """
        if service_data is None:
            service_data = {}

        if allow_override and service_name in self._cmds:
            override = dict(self._cmds[service_name])
            override["data"] = {**service_data, **override.get("data", {})}

            if "target" not in override and (active_child := self._child_state) is not None:
                override["target"] = {ATTR_ENTITY_ID: active_child.entity_id}

            await async_call_from_config(
                self.hass,
                override,
                variables=service_data,
                blocking=True,
                validate_config=False,
            )
            return

        if (active_child := self._child_state) is None:
            # No child to call service on
            return

        service_data[ATTR_ENTITY_ID] = active_child.entity_id

        await self.hass.services.async_call(
            MEDIA_PLAYER_DOMAIN,
            service_name,
            service_data,
            blocking=True,
            context=self._context,
        )

    @property
    def master_state(self) -> Any:
        """Return the master state for entity or None.

        Returns:
            The result of the state template if defined, the state from the
            configured state attribute entity if present, or None otherwise.

        """
        if self._state_template is not None:
            return self._state_template_result
        if CONF_STATE in self._attrs:
            master_state = self._entity_lkp(self._attrs[CONF_STATE][0], self._attrs[CONF_STATE][1])
            return master_state or MediaPlayerState.OFF

        return None

    @property
    @override
    def assumed_state(self) -> bool | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return True if unable to access real state of the entity.

        Returns:
            The assumed state value from the active child, or None if no child is active.

        """
        return self._child_attr(ATTR_ASSUMED_STATE)

    @property
    @override
    def state(self) -> MediaPlayerState | str | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return the current state of media player.

        Off if master state is off, else status of first active child,
        else master state or off.

        Returns:
            The current MediaPlayerState, or None if undetermined.

        """
        master_state = self.master_state  # avoid multiple lookups
        if (master_state == MediaPlayerState.OFF) or (self._state_template is not None):
            return master_state

        if active_child := self._child_state:
            return active_child.state

        return master_state or MediaPlayerState.OFF

    @property
    @override
    def volume_level(self) -> float | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Volume level of entity specified in attributes or active child.

        Returns:
            The volume level as a float between 0 and 1, or None if unavailable
            or not parseable.

        """
        try:
            return float(self._override_or_child_attr(ATTR_MEDIA_VOLUME_LEVEL))
        except (TypeError, ValueError):
            return None

    @property
    @override
    def is_volume_muted(self) -> bool:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Boolean if volume is muted.

        Returns:
            True if the volume is muted, False otherwise.

        """
        return self._override_or_child_attr(ATTR_MEDIA_VOLUME_MUTED) in [True, STATE_ON]

    @property
    @override
    def media_content_id(self) -> str | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return the content ID of current playing media.

        Returns:
            The media content ID string, or None if unavailable.

        """
        return self._child_attr(ATTR_MEDIA_CONTENT_ID)

    @property
    @override
    def media_content_type(self) -> str | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return the content type of current playing media.

        Returns:
            The media content type string, or None if unavailable.

        """
        return self._override_or_child_attr(ATTR_MEDIA_CONTENT_TYPE)

    @property
    @override
    def media_duration(self) -> float | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return the duration of current playing media in seconds.

        Returns:
            The media duration as a number, or None if unavailable.

        """
        return self._override_or_child_attr(ATTR_MEDIA_DURATION)

    @property
    @override
    def media_image_url(self) -> str | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Image url of current playing media.

        Returns:
            The URL string of the media image, or None if unavailable.

        """
        return self._override_or_child_attr(ATTR_ENTITY_PICTURE)

    @property
    @override
    def entity_picture(self) -> str | None:
        """Return image of the media playing.

        The custom universal media player doesn't use the parent class logic, since
        the url is coming from child entity pictures which have already been
        sent through the API proxy.

        Returns:
            The URL string of the entity picture, or None if unavailable.

        """
        return self.media_image_url

    @property
    @override
    def media_title(self) -> str | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Title of current playing media.

        Returns:
            The media title string, or None if unavailable.

        """
        return self._override_or_child_attr(ATTR_MEDIA_TITLE)

    @property
    @override
    def media_artist(self) -> str | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Artist of current playing media (Music track only).

        Returns:
            The artist name string, or None if unavailable.

        """
        return self._override_or_child_attr(ATTR_MEDIA_ARTIST)

    @property
    @override
    def media_album_name(self) -> str | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Album name of current playing media (Music track only).

        Returns:
            The album name string, or None if unavailable.

        """
        return self._override_or_child_attr(ATTR_MEDIA_ALBUM_NAME)

    @property
    @override
    def media_album_artist(self) -> str | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Album artist of current playing media (Music track only).

        Returns:
            The album artist name string, or None if unavailable.

        """
        return self._override_or_child_attr(ATTR_MEDIA_ALBUM_ARTIST)

    @property
    @override
    def media_track(self) -> str | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Track number of current playing media (Music track only).

        Returns:
            The track number, or None if unavailable.

        """
        return self._override_or_child_attr(ATTR_MEDIA_TRACK)

    @property
    @override
    def media_series_title(self) -> str | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return the title of the series of current playing media (TV).

        Returns:
            The series title string, or None if unavailable.

        """
        return self._override_or_child_attr(ATTR_MEDIA_SERIES_TITLE)

    @property
    @override
    def media_season(self) -> str | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Season of current playing media (TV Show only).

        Returns:
            The season identifier, or None if unavailable.

        """
        return self._override_or_child_attr(ATTR_MEDIA_SEASON)

    @property
    @override
    def media_episode(self) -> str | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Episode of current playing media (TV Show only).

        Returns:
            The episode identifier, or None if unavailable.

        """
        return self._override_or_child_attr(ATTR_MEDIA_EPISODE)

    @property
    @override
    def media_channel(self) -> str | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Channel currently playing.

        Returns:
            The channel name string, or None if unavailable.

        """
        return self._override_or_child_attr(ATTR_MEDIA_CHANNEL)

    @property
    @override
    def media_playlist(self) -> str | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Title of Playlist currently playing.

        Returns:
            The playlist title string, or None if unavailable.

        """
        return self._override_or_child_attr(ATTR_MEDIA_PLAYLIST)

    @property
    @override
    def app_id(self) -> str | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """ID of the current running app.

        Returns:
            The application ID string, or None if unavailable.

        """
        return self._override_or_child_attr(ATTR_APP_ID)

    @property
    @override
    def app_name(self) -> str | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Name of the current running app.

        Returns:
            The application name string, or None if unavailable.

        """
        return self._override_or_child_attr(ATTR_APP_NAME)

    @property
    @override
    def sound_mode(self) -> str | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return the current sound mode of the device.

        Returns:
            The current sound mode string, or None if unavailable.

        """
        return self._override_or_child_attr(ATTR_SOUND_MODE)

    @property
    @override
    def sound_mode_list(self) -> list[str] | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """List of available sound modes.

        Returns:
            A list of sound mode strings, or None if unavailable.

        """
        return self._override_or_child_attr(ATTR_SOUND_MODE_LIST)

    @property
    @override
    def source(self) -> str | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return the current input source of the device.

        Returns:
            The current input source string, or None if unavailable.

        """
        return self._override_or_child_attr(ATTR_INPUT_SOURCE)

    @property
    @override
    def source_list(self) -> list[str] | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """List of available input sources.

        Returns:
            A list of input source strings, or None if unavailable.

        """
        return self._override_or_child_attr(ATTR_INPUT_SOURCE_LIST)

    @property
    @override
    def repeat(self) -> RepeatMode | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Indicate if repeating is enabled.

        Returns:
            The current repeat mode value, or None if unavailable.

        """
        return self._override_or_child_attr(ATTR_MEDIA_REPEAT)

    @property
    @override
    def shuffle(self) -> bool | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Boolean if shuffling is enabled.

        Returns:
            True if shuffle is enabled, False if disabled, or None if unavailable.

        """
        return self._override_or_child_attr(ATTR_MEDIA_SHUFFLE)

    @property
    @override
    def supported_features(self) -> MediaPlayerEntityFeature:  # pyright: ignore[reportIncompatibleVariableOverride] # pylint: disable=too-many-branches
        """Flag media player features that are supported.

        Returns:
            A MediaPlayerEntityFeature bitmask representing all supported features,
            combining child entity capabilities with any configured command overrides.

        """
        flags: MediaPlayerEntityFeature = self._child_attr(ATTR_SUPPORTED_FEATURES) or MediaPlayerEntityFeature(0)
        flags &= ~(MediaPlayerEntityFeature.GROUPING | MediaPlayerEntityFeature.BROWSE_MEDIA)

        if SERVICE_JOIN in self._cmds:
            flags |= MediaPlayerEntityFeature.GROUPING

        if SERVICE_TURN_ON in self._cmds:
            flags |= MediaPlayerEntityFeature.TURN_ON
        if SERVICE_TURN_OFF in self._cmds:
            flags |= MediaPlayerEntityFeature.TURN_OFF

        if SERVICE_MEDIA_PLAY_PAUSE in self._cmds:
            flags |= MediaPlayerEntityFeature.PLAY | MediaPlayerEntityFeature.PAUSE
        else:
            if SERVICE_MEDIA_PLAY in self._cmds:
                flags |= MediaPlayerEntityFeature.PLAY
            if SERVICE_MEDIA_PAUSE in self._cmds:
                flags |= MediaPlayerEntityFeature.PAUSE

        if SERVICE_MEDIA_STOP in self._cmds:
            flags |= MediaPlayerEntityFeature.STOP

        if SERVICE_MEDIA_NEXT_TRACK in self._cmds:
            flags |= MediaPlayerEntityFeature.NEXT_TRACK
        if SERVICE_MEDIA_PREVIOUS_TRACK in self._cmds:
            flags |= MediaPlayerEntityFeature.PREVIOUS_TRACK

        if any(cmd in self._cmds for cmd in (SERVICE_VOLUME_UP, SERVICE_VOLUME_DOWN)):
            flags |= MediaPlayerEntityFeature.VOLUME_STEP
        if SERVICE_VOLUME_SET in self._cmds:
            flags |= MediaPlayerEntityFeature.VOLUME_SET

        if SERVICE_VOLUME_MUTE in self._cmds and ATTR_MEDIA_VOLUME_MUTED in self._attrs:
            flags |= MediaPlayerEntityFeature.VOLUME_MUTE

        if SERVICE_SELECT_SOURCE in self._cmds and ATTR_INPUT_SOURCE_LIST in self._attrs:
            flags |= MediaPlayerEntityFeature.SELECT_SOURCE

        if SERVICE_PLAY_MEDIA in self._cmds:
            flags |= MediaPlayerEntityFeature.PLAY_MEDIA

        if self._browse_media_entity:
            flags |= MediaPlayerEntityFeature.BROWSE_MEDIA

        if SERVICE_CLEAR_PLAYLIST in self._cmds:
            flags |= MediaPlayerEntityFeature.CLEAR_PLAYLIST

        if SERVICE_SHUFFLE_SET in self._cmds and ATTR_MEDIA_SHUFFLE in self._attrs:
            flags |= MediaPlayerEntityFeature.SHUFFLE_SET

        if SERVICE_REPEAT_SET in self._cmds and ATTR_MEDIA_REPEAT in self._attrs:
            flags |= MediaPlayerEntityFeature.REPEAT_SET

        if SERVICE_SELECT_SOUND_MODE in self._cmds and ATTR_SOUND_MODE_LIST in self._attrs:
            flags |= MediaPlayerEntityFeature.SELECT_SOUND_MODE

        return flags

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any]:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return device specific state attributes.

        Returns:
            A dictionary containing the active child entity ID under the
            ATTR_ACTIVE_CHILD key, or an empty dictionary if no child is active.

        """
        active_child = self._child_state
        return {ATTR_ACTIVE_CHILD: active_child.entity_id} if active_child else {}

    @property
    @override
    def media_position(self) -> float | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Position of current playing media in seconds.

        Returns:
            The current media position as a number, or None if unavailable.

        """
        return self._override_or_child_attr(ATTR_MEDIA_POSITION)

    @property
    @override
    def media_position_updated_at(self) -> datetime | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """When was the position of the current playing media valid.

        Returns:
            A datetime representing when the media position was last updated,
            or None if unavailable.

        """
        return self._override_or_child_attr(ATTR_MEDIA_POSITION_UPDATED_AT)

    @property
    def state_attributes(self) -> dict[str, Any]:  # pyright: ignore[reportIncompatibleMethodOverride] # pylint: disable=overridden-final-method
        """Return the state attributes.

        Returns:
            A dictionary of state attributes for the media player. Returns an
            empty dictionary when the player is off. Includes all standard media
            player attributes and the local entity picture if applicable.

        """
        state_attr: dict[str, Any] = {}

        if self.support_grouping:
            state_attr[ATTR_GROUP_MEMBERS] = self.group_members

        if self.state == MediaPlayerState.OFF:
            return state_attr

        for attr in ATTR_TO_PROPERTY:
            if (value := getattr(self, attr)) is not None:
                state_attr[attr] = value

        # Use local image proxy if the URL is not HTTPS, as HA runs over HTTPS
        if ATTR_ENTITY_PICTURE_LOCAL not in state_attr or "https:" not in state_attr[ATTR_ENTITY_PICTURE_LOCAL]:
            state_attr[ATTR_ENTITY_PICTURE_LOCAL] = self.media_image_local

        return state_attr

    @override
    async def async_turn_on(self) -> None:
        """Turn the media player on."""
        await self._async_call_service(SERVICE_TURN_ON, allow_override=True)

    @override
    async def async_turn_off(self) -> None:
        """Turn the media player off."""
        await self._async_call_service(SERVICE_TURN_OFF, allow_override=True)

    @override
    async def async_mute_volume(self, mute: bool) -> None:
        """Mute the volume.

        Args:
            mute: True to mute, False to unmute.

        """
        data = {ATTR_MEDIA_VOLUME_MUTED: mute}
        await self._async_call_service(SERVICE_VOLUME_MUTE, data, allow_override=True)

    @override
    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level, range 0..1.

        Args:
            volume: The desired volume level as a float between 0 and 1.

        """
        data = {ATTR_MEDIA_VOLUME_LEVEL: volume}
        await self._async_call_service(SERVICE_VOLUME_SET, data, allow_override=True)

    @override
    async def async_media_play(self) -> None:
        """Send play command."""
        await self._async_call_service(SERVICE_MEDIA_PLAY, allow_override=True)

    @override
    async def async_media_pause(self) -> None:
        """Send pause command."""
        await self._async_call_service(SERVICE_MEDIA_PAUSE, allow_override=True)

    @override
    async def async_media_stop(self) -> None:
        """Send stop command."""
        await self._async_call_service(SERVICE_MEDIA_STOP, allow_override=True)

    @override
    async def async_media_previous_track(self) -> None:
        """Send previous track command."""
        await self._async_call_service(SERVICE_MEDIA_PREVIOUS_TRACK, allow_override=True)

    @override
    async def async_media_next_track(self) -> None:
        """Send next track command."""
        await self._async_call_service(SERVICE_MEDIA_NEXT_TRACK, allow_override=True)

    @override
    async def async_media_seek(self, position: float) -> None:
        """Send seek command.

        Args:
            position: The target position in seconds to seek to.

        """
        data = {ATTR_MEDIA_SEEK_POSITION: position}
        await self._async_call_service(SERVICE_MEDIA_SEEK, data)

    @override
    async def async_play_media(self, media_type: MediaType | str, media_id: str, **kwargs: Any) -> None:
        """Play a piece of media.

        Args:
            media_type: The type of media to play (e.g. music, video).
            media_id: The ID or URL of the media to play.
            **kwargs: Additional optional parameters passed to the service.

        """
        data = {ATTR_MEDIA_CONTENT_TYPE: media_type, ATTR_MEDIA_CONTENT_ID: media_id}
        await self._async_call_service(SERVICE_PLAY_MEDIA, data, allow_override=True)

    @override
    async def async_volume_up(self) -> None:
        """Turn volume up for media player."""
        await self._async_call_service(SERVICE_VOLUME_UP, allow_override=True)

    @override
    async def async_volume_down(self) -> None:
        """Turn volume down for media player."""
        await self._async_call_service(SERVICE_VOLUME_DOWN, allow_override=True)

    @override
    async def async_media_play_pause(self) -> None:
        """Play or pause the media player."""
        await self._async_call_service(SERVICE_MEDIA_PLAY_PAUSE, allow_override=True)

    @override
    async def async_select_sound_mode(self, sound_mode: str) -> None:
        """Select sound mode.

        Args:
            sound_mode: The sound mode to select.

        """
        data = {ATTR_SOUND_MODE: sound_mode}
        await self._async_call_service(SERVICE_SELECT_SOUND_MODE, data, allow_override=True)

    @override
    async def async_select_source(self, source: str) -> None:
        """Set the input source.

        Args:
            source: The input source to select.

        """
        data = {ATTR_INPUT_SOURCE: source}
        await self._async_call_service(SERVICE_SELECT_SOURCE, data, allow_override=True)

    @override
    async def async_clear_playlist(self) -> None:
        """Clear player playlist."""
        await self._async_call_service(SERVICE_CLEAR_PLAYLIST, allow_override=True)

    @override
    async def async_join_players(self, group_members: list[str]) -> None:
        """Join the active child with other players.

        group_members may reference other custom_universal_media_player
        entities rather than real ones (they're what the join dialog lists
        for this player). The underlying platform (Sonos, Cast, etc.) only
        knows its own real entities, so each virtual member is resolved to
        its own active child before the service call.

        Args:
            group_members: The entity IDs of the players to join.

        """
        resolved_members = [self._resolve_real_entity_id(entity_id) for entity_id in group_members]
        data = {ATTR_GROUP_MEMBERS: resolved_members}
        await self._async_call_service(SERVICE_JOIN, data, allow_override=True)

    def _resolve_real_entity_id(self, entity_id: str) -> str:
        """Resolve a group member to a real (non-virtual) entity ID.

        Args:
            entity_id: The entity ID to resolve, possibly another
                custom_universal_media_player entity.

        Returns:
            The entity's own active_child entity ID if it is another
            custom_universal_media_player instance, otherwise the entity ID
            unchanged.

        """
        state = self.hass.states.get(entity_id)
        if state is None:
            return entity_id

        return state.attributes.get(ATTR_ACTIVE_CHILD, entity_id)

    @property
    @override
    def group_members(self) -> list[str] | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """List of members which are currently grouped together.

        The active child's own group_members are real entity IDs (e.g. a
        Sonos speaker). Each is mapped back to the custom_universal_media_player
        entity that currently has it as its active child, if any, so the
        join dialog and the group count badge reflect the virtual entities
        the user actually configured - falling back to the real entity ID
        when no matching virtual entity is found.

        Returns:
            The list of group member entity IDs, or None if the active
            child doesn't report any.

        """
        real_members = self._child_attr(ATTR_GROUP_MEMBERS)
        if not real_members:
            return real_members

        real_to_virtual = {
            state.attributes[ATTR_ACTIVE_CHILD]: state.entity_id
            for state in self.hass.states.async_all(MEDIA_PLAYER_DOMAIN)
            if ATTR_ACTIVE_CHILD in state.attributes
        }

        return [real_to_virtual.get(entity_id, entity_id) for entity_id in real_members]

    @override
    async def async_unjoin_player(self) -> None:
        """Remove the active child from its current group."""
        await self._async_call_service(SERVICE_UNJOIN, allow_override=True)

    @override
    async def async_set_shuffle(self, shuffle: bool) -> None:
        """Enable/disable shuffling.

        Args:
            shuffle: True to enable shuffle, False to disable.

        """
        data = {ATTR_MEDIA_SHUFFLE: shuffle}
        await self._async_call_service(SERVICE_SHUFFLE_SET, data, allow_override=True)

    @override
    async def async_set_repeat(self, repeat: RepeatMode) -> None:
        """Set repeat mode.

        Args:
            repeat: The repeat mode to set.

        """
        data = {ATTR_MEDIA_REPEAT: repeat}
        await self._async_call_service(SERVICE_REPEAT_SET, data, allow_override=True)

    @override
    async def async_toggle(self) -> None:
        """Toggle the power on the media player."""
        if SERVICE_TOGGLE in self._cmds:
            await self._async_call_service(SERVICE_TOGGLE, allow_override=True)
        else:
            # Delegate to turn_on or turn_off by default
            await super().async_toggle()

    @override
    async def async_browse_media(
        self,
        media_content_type: MediaType | str | None = None,
        media_content_id: str | None = None,
    ) -> BrowseMedia:
        """Return a BrowseMedia instance.

        Delegates to the configured browse media entity if set, or falls back
        to the active child entity.

        Args:
            media_content_type: Optional media content type to browse.
            media_content_id: Optional media content ID to browse from.

        Returns:
            A BrowseMedia instance from the target entity.

        Raises:
            NotImplementedError: If no valid target entity is found.

        """
        entity_id = self._browse_media_entity
        if not entity_id and self._child_state:
            entity_id = self._child_state.entity_id
        component: EntityComponent[MediaPlayerEntity] = self.hass.data[MEDIA_PLAYER_DOMAIN]
        if entity_id and (entity := component.get_entity(entity_id)):
            return await entity.async_browse_media(media_content_type, media_content_id)
        raise NotImplementedError

    @callback
    def _async_update(self) -> None:
        """Update state in HA.

        Resolves the active child entity by selecting the child with the highest
        priority state. If an active child template result is available, it is
        used directly. Otherwise, iterates over configured children and picks the
        one with the most active state according to STATES_ORDER_LOOKUP.

        """
        if self._active_child_template_result:
            self._child_state = self.hass.states.get(self._active_child_template_result)
            return
        self._child_state = None
        for child_name in self._children:
            if (child_state := self.hass.states.get(child_name)) and (
                child_state_order := STATES_ORDER_LOOKUP.get(child_state.state, 0)
            ) >= STATES_ORDER_IDLE:
                if self._child_state:
                    if child_state_order > STATES_ORDER_LOOKUP.get(self._child_state.state, 0):
                        self._child_state = child_state
                else:
                    self._child_state = child_state

    async def async_update(self) -> None:
        """Manual update from API."""
        self._async_update()
