"""Config flow for the custom universal media player component."""

from __future__ import annotations

from collections import Counter
import json
import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol
import yaml

from homeassistant.components.media_player import (
    DOMAIN as MEDIA_PLAYER_DOMAIN,  # pyright: ignore[reportPrivateImportUsage]
    MediaPlayerDeviceClass,
)
from homeassistant.components.media_player.const import (
    SERVICE_CLEAR_PLAYLIST,
    SERVICE_JOIN,
    SERVICE_PLAY_MEDIA,
    SERVICE_SELECT_SOUND_MODE,
    SERVICE_SELECT_SOURCE,
    SERVICE_UNJOIN,
    MediaPlayerEntityFeature,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_SUPPORTED_FEATURES,
    CONF_DEVICE_CLASS,
    CONF_NAME,
    CONF_STATE_TEMPLATE,
    CONF_UNIQUE_ID,
    SERVICE_MEDIA_NEXT_TRACK,
    SERVICE_MEDIA_PAUSE,
    SERVICE_MEDIA_PLAY,
    SERVICE_MEDIA_PLAY_PAUSE,
    SERVICE_MEDIA_PREVIOUS_TRACK,
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
)
from homeassistant.data_entry_flow import SectionConfig, section
from homeassistant.exceptions import TemplateError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.issue_registry import IssueSeverity, async_create_issue
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TemplateSelector,
    TextSelector,
    TextSelectorConfig,
)
from homeassistant.util import slugify
from homeassistant.util.uuid import random_uuid_hex

from .const import (
    CONF_ACTIVE_CHILD_TEMPLATE,
    CONF_ATTRS,
    CONF_BROWSE_MEDIA_ENTITY,
    CONF_CHILDREN,
    CONF_COMMANDS,
    CONF_DEVICE_CLASS_NONE,
    DOMAIN,
)
from .media_player import ATTRS_SCHEMA, CMD_SCHEMA

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)

COMMAND_CATEGORIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("power", (SERVICE_TURN_ON, SERVICE_TURN_OFF, SERVICE_TOGGLE)),
    (
        "playback",
        (
            SERVICE_MEDIA_PLAY,
            SERVICE_MEDIA_PAUSE,
            SERVICE_MEDIA_PLAY_PAUSE,
            SERVICE_MEDIA_STOP,
            SERVICE_PLAY_MEDIA,
            SERVICE_CLEAR_PLAYLIST,
            SERVICE_SHUFFLE_SET,
            SERVICE_REPEAT_SET,
        ),
    ),
    ("navigation", (SERVICE_MEDIA_NEXT_TRACK, SERVICE_MEDIA_PREVIOUS_TRACK)),
    ("volume", (SERVICE_VOLUME_UP, SERVICE_VOLUME_DOWN, SERVICE_VOLUME_SET, SERVICE_VOLUME_MUTE)),
    ("source", (SERVICE_SELECT_SOURCE, SERVICE_SELECT_SOUND_MODE)),
    ("grouping", (SERVICE_JOIN, SERVICE_UNJOIN)),
)

KNOWN_COMMAND_KEYS: tuple[str, ...] = tuple(key for _category, keys in COMMAND_CATEGORIES for key in keys)

ACTION_REQUIRED_FEATURE: dict[str, MediaPlayerEntityFeature] = {
    SERVICE_TURN_ON: MediaPlayerEntityFeature.TURN_ON,
    SERVICE_TURN_OFF: MediaPlayerEntityFeature.TURN_OFF,
    SERVICE_TOGGLE: MediaPlayerEntityFeature.TURN_ON | MediaPlayerEntityFeature.TURN_OFF,
    SERVICE_MEDIA_PLAY: MediaPlayerEntityFeature.PLAY,
    SERVICE_MEDIA_PAUSE: MediaPlayerEntityFeature.PAUSE,
    SERVICE_MEDIA_PLAY_PAUSE: MediaPlayerEntityFeature.PLAY | MediaPlayerEntityFeature.PAUSE,
    SERVICE_MEDIA_STOP: MediaPlayerEntityFeature.STOP,
    SERVICE_PLAY_MEDIA: MediaPlayerEntityFeature.PLAY_MEDIA,
    SERVICE_CLEAR_PLAYLIST: MediaPlayerEntityFeature.CLEAR_PLAYLIST,
    SERVICE_SHUFFLE_SET: MediaPlayerEntityFeature.SHUFFLE_SET,
    SERVICE_REPEAT_SET: MediaPlayerEntityFeature.REPEAT_SET,
    SERVICE_MEDIA_NEXT_TRACK: MediaPlayerEntityFeature.NEXT_TRACK,
    SERVICE_MEDIA_PREVIOUS_TRACK: MediaPlayerEntityFeature.PREVIOUS_TRACK,
    SERVICE_VOLUME_UP: MediaPlayerEntityFeature.VOLUME_STEP,
    SERVICE_VOLUME_DOWN: MediaPlayerEntityFeature.VOLUME_STEP,
    SERVICE_VOLUME_SET: MediaPlayerEntityFeature.VOLUME_SET,
    SERVICE_VOLUME_MUTE: MediaPlayerEntityFeature.VOLUME_MUTE,
    SERVICE_SELECT_SOURCE: MediaPlayerEntityFeature.SELECT_SOURCE,
    SERVICE_SELECT_SOUND_MODE: MediaPlayerEntityFeature.SELECT_SOUND_MODE,
    SERVICE_JOIN: MediaPlayerEntityFeature.GROUPING,
    SERVICE_UNJOIN: MediaPlayerEntityFeature.GROUPING,
}

DEVICE_CLASS_LABELS: dict[str, str] = {
    CONF_DEVICE_CLASS_NONE: "None",
    "tv": "TV",
    "speaker": "Speaker",
    "receiver": "Receiver",
    "projector": "Projector",
}

DEVICE_CLASS_OPTIONS: tuple[str, ...] = tuple(
    sorted(
        (CONF_DEVICE_CLASS_NONE, *(device_class.value for device_class in MediaPlayerDeviceClass)),
        key=lambda value: DEVICE_CLASS_LABELS[value],
    ),
)

ACTION_OPTIONS: tuple[str, ...] = tuple(sorted(f"{MEDIA_PLAYER_DOMAIN}.{key}" for key in KNOWN_COMMAND_KEYS))


def _entity_field(key: str, *, error: bool = False) -> str:
    """Build the schema field name for a command's target entity.

    Args:
        key: The command key (e.g. "turn_on").
        error: Whether to use the field name whose label carries a warning
            marker, shown when the command is incomplete.

    Returns:
        The corresponding form field name.

    """
    return f"{key}__entity_error" if error else f"{key}__entity"


def _action_field(key: str) -> str:
    """Build the schema field name for a command's action.

    Args:
        key: The command key (e.g. "turn_on").

    Returns:
        The corresponding form field name.

    """
    return f"{key}__action"


def _category_section(category: str) -> str:
    """Build the section name for a command category.

    Args:
        category: The category name (e.g. "power").

    Returns:
        The corresponding form section name.

    """
    return f"category_{category}"


def _extract_entity_id(command: dict[str, Any]) -> str | None:
    """Extract a single target entity_id from a command, if there is exactly one.

    Args:
        command: The command dict (action/target/data).

    Returns:
        The single target entity_id, or None if there is none or more than one.

    """
    entity_id = command.get("target", {}).get("entity_id")

    if isinstance(entity_id, list):
        return entity_id[0] if len(entity_id) == 1 else None

    return entity_id or None


def _format_problems(problems: list[str]) -> str:
    """Format a list of validation problems as a bullet list for a step description.

    Args:
        problems: The problem descriptions to list, if any.

    Returns:
        A markdown bullet list prefixed with a blank line, ready to be
        appended after a step's base description text, or an empty string
        if there are no problems.

    """
    if not problems:
        return ""

    bullet_list = "\n".join(f"- {problem}" for problem in problems)
    return f"\n\nInvalid configuration:\n{bullet_list}"


def _is_simple_command(command: dict[str, Any] | None) -> bool:
    """Check whether a command reduces to a plain entity + action pick.

    Args:
        command: The command dict (action/target/data), or None.

    Returns:
        True if the command only has an action and a single target entity_id,
        with no extra data.

    """
    if not command:
        return True

    if set(command) - {"action", "target"}:
        return False

    target = command.get("target", {})
    if set(target) - {"entity_id"}:
        return False

    return _extract_entity_id(command) is not None


class CustomUniversalMediaPlayerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the custom universal media player."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow state."""
        self._data: dict[str, Any] = {}
        self._title: str = ""
        self._reconfigure_entry: ConfigEntry | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the first step: name and children selection.

        Args:
            user_input: The submitted form data, or None on first display.

        Returns:
            The next step's flow result.

        """
        errors: dict[str, str] = {}

        if user_input is not None:
            unique_id = random_uuid_hex()
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            self._title = user_input[CONF_NAME]
            self._data[CONF_NAME] = user_input[CONF_NAME]
            self._data[CONF_CHILDREN] = user_input[CONF_CHILDREN]
            self._data[CONF_UNIQUE_ID] = unique_id

            return await self.async_step_device_class()

        schema = vol.Schema(
            {
                vol.Required(CONF_CHILDREN, default=[]): EntitySelector(
                    EntitySelectorConfig(domain=MEDIA_PLAYER_DOMAIN, multiple=True, reorder=True),
                ),
                vol.Required(CONF_NAME): TextSelector(),
            },
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_device_class(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the device class confirmation step.

        Args:
            user_input: The submitted form data, or None on first display.

        Returns:
            The next step's flow result.

        """
        if user_input is not None:
            device_class = user_input[CONF_DEVICE_CLASS]
            self._data[CONF_DEVICE_CLASS] = None if device_class == CONF_DEVICE_CLASS_NONE else device_class
            return await self.async_step_config_menu()

        suggested = self._suggest_device_class()
        current = self._data.get(CONF_DEVICE_CLASS) or CONF_DEVICE_CLASS_NONE

        schema = vol.Schema(
            {
                vol.Optional(CONF_DEVICE_CLASS, default=current): SelectSelector(
                    SelectSelectorConfig(
                        options=list(DEVICE_CLASS_OPTIONS),
                        translation_key="device_class",
                        mode=SelectSelectorMode.DROPDOWN,
                    ),
                ),
            },
        )

        return self.async_show_form(
            step_id="device_class",
            data_schema=schema,
            description_placeholders={"suggested_device_class": DEVICE_CLASS_LABELS[suggested]},
        )

    def _suggest_device_class(self) -> str:
        """Suggest a device class based on the selected children's current state.

        Returns:
            The most common device class among the children, or the "none"
            sentinel if none is found.

        """
        child_classes = [
            device_class
            for entity_id in self._data.get(CONF_CHILDREN, [])
            if (state := self.hass.states.get(entity_id)) is not None
            and (device_class := state.attributes.get(ATTR_DEVICE_CLASS))
        ]

        if not child_classes:
            return CONF_DEVICE_CLASS_NONE

        return Counter(child_classes).most_common(1)[0][0]

    async def async_step_config_menu(self, _user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Offer to configure commands via pickers, raw YAML, or skip to attributes.

        Args:
            _user_input: Unused; menu selection is handled via dedicated steps.

        Returns:
            A menu flow result with "guided", "custom" and "attributes" options.

        """
        guided_label = "Configure commands - Guided"
        if not self._data.get(CONF_CHILDREN) or not self._children_have_any_capability() or self._has_custom_commands():
            guided_label += " (⚠️)"

        return self.async_show_menu(
            step_id="config_menu",
            menu_options={
                "config_children": "Edit children",
                "config_device_class": "Edit device class",
                "config_guided": guided_label,
                "config_custom": "Configure commands - Custom (YAML)",
                "config_attributes": "Configure attributes - Custom (YAML)",
                "config_advanced": "Advanced configuration",
                "config_save": "Finalize configuration",
            },
        )

    async def async_step_config_device_class(self, _user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show the device class step, reachable from the config menu.

        Args:
            _user_input: Unused.

        Returns:
            The device class step's flow result.

        """
        return await self.async_step_device_class()

    def _has_custom_commands(self) -> bool:
        """Check whether any current command is not a plain entity+action pick.

        Returns:
            True if at least one command would be lost by the guided picker.

        """
        existing_commands: dict[str, Any] = self._data.get(CONF_COMMANDS, {})
        return any(not _is_simple_command(command) for command in existing_commands.values())

    async def async_step_config_guided(self, _user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show the entity/action picker step.

        Guided configuration requires at least one child to be selected, and
        that at least one of them supports a known command; if not, an
        explicit warning screen is shown instead of an empty picker. If
        custom commands would be lost, asks for confirmation first.

        Args:
            _user_input: Unused.

        Returns:
            A warning screen, the confirmation menu, or the entity/action
            picker step's flow result.

        """
        if not self._data.get(CONF_CHILDREN) or not self._children_have_any_capability():
            return await self.async_step_config_guided_no_children()

        if self._has_custom_commands():
            return await self.async_step_config_guided_confirm()

        return await self.async_step_config_commands()

    def _available_features(self) -> MediaPlayerEntityFeature:
        """Compute the union of supported_features across the selected children.

        Returns:
            The bitwise OR of all children's supported_features, 0 if none
            are currently available.

        """
        available_features = MediaPlayerEntityFeature(0)

        for entity_id in self._data.get(CONF_CHILDREN, []):
            state = self.hass.states.get(entity_id)
            if state is not None:
                available_features |= MediaPlayerEntityFeature(state.attributes.get(ATTR_SUPPORTED_FEATURES, 0))

        return available_features

    def _children_have_any_capability(self) -> bool:
        """Check whether any selected child supports at least one known command.

        Returns:
            True if at least one child's supported_features overlaps with
            at least one of the known commands' required feature.

        """
        available_features = self._available_features()

        return any(bool(available_features & required) for required in ACTION_REQUIRED_FEATURE.values())

    async def async_step_config_guided_no_children(
        self,
        _user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Warn that guided configuration requires at least one capable child.

        Args:
            _user_input: Unused; menu selection is handled via dedicated steps.

        Returns:
            A menu flow result with "edit children" and "back" options.

        """
        return self.async_show_menu(
            step_id="config_guided_no_children",
            menu_options={
                "config_children": "Edit children",
                "config_menu": "Go back",
            },
        )

    async def async_step_config_children(self, _user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show the children step, reachable from the config menu.

        Args:
            _user_input: Unused.

        Returns:
            The children step's flow result.

        """
        return await self.async_step_children()

    async def async_step_children(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Edit the selected children.

        Args:
            user_input: The submitted form data, or None on first display.

        Returns:
            The device class step's flow result.

        """
        if user_input is not None:
            self._data[CONF_CHILDREN] = user_input[CONF_CHILDREN]
            return await self.async_step_config_device_class()

        schema = vol.Schema(
            {
                vol.Required(CONF_CHILDREN, default=self._data.get(CONF_CHILDREN, [])): EntitySelector(
                    EntitySelectorConfig(domain=MEDIA_PLAYER_DOMAIN, multiple=True, reorder=True),
                ),
            },
        )

        return self.async_show_form(step_id="children", data_schema=schema)

    async def async_step_config_advanced(self, _user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show the advanced settings step, reachable from the config menu.

        Args:
            _user_input: Unused.

        Returns:
            The advanced settings step's flow result.

        """
        return await self.async_step_advanced()

    async def async_step_advanced(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Edit advanced settings.

        Args:
            user_input: The submitted form data, or None on first display.

        Returns:
            The config menu's flow result.

        """
        errors: dict[str, str] = {}

        if user_input is not None:
            active_child_template = user_input.get(CONF_ACTIVE_CHILD_TEMPLATE) or None
            state_template = user_input.get(CONF_STATE_TEMPLATE) or None

            if active_child_template and not self._active_child_template_result_is_valid(active_child_template):
                errors[CONF_ACTIVE_CHILD_TEMPLATE] = "invalid_active_child_template_result"
            if state_template and not self._template_result_is_valid(state_template):
                errors[CONF_STATE_TEMPLATE] = "invalid_template_result"

            if not errors:
                self._data[CONF_BROWSE_MEDIA_ENTITY] = user_input.get(CONF_BROWSE_MEDIA_ENTITY) or None
                self._data[CONF_ACTIVE_CHILD_TEMPLATE] = active_child_template
                self._data[CONF_STATE_TEMPLATE] = state_template
                return await self.async_step_config_menu()

        schema = vol.Schema(
            {
                vol.Optional(CONF_BROWSE_MEDIA_ENTITY): EntitySelector(
                    EntitySelectorConfig(
                        domain=MEDIA_PLAYER_DOMAIN,
                        filter=[{"supported_features": ["media_player.MediaPlayerEntityFeature.BROWSE_MEDIA"]}],
                    ),
                ),
                vol.Optional(CONF_ACTIVE_CHILD_TEMPLATE): TemplateSelector(),
                vol.Optional(CONF_STATE_TEMPLATE): TemplateSelector(),
            },
        )
        suggested_values = (
            user_input
            if errors
            else {
                CONF_BROWSE_MEDIA_ENTITY: self._data.get(CONF_BROWSE_MEDIA_ENTITY),
                CONF_ACTIVE_CHILD_TEMPLATE: self._data.get(CONF_ACTIVE_CHILD_TEMPLATE),
                CONF_STATE_TEMPLATE: self._data.get(CONF_STATE_TEMPLATE),
            }
        )

        return self.async_show_form(
            step_id="advanced",
            data_schema=self.add_suggested_values_to_schema(schema, suggested_values),
            errors=errors,
        )

    def _template_result_is_valid(self, raw_template: str) -> bool:
        """Check that a template renders to a plain string, as required at runtime.

        Both active_child_template and state_template are rendered and used
        directly (as an entity_id lookup or a state value, respectively) -
        a template that renders to a non-string (e.g. a bare boolean
        expression like "{{ is_state(...) }}") would crash or produce a
        nonsensical state at runtime instead of failing here. A template
        that fails to render at all (e.g. a typo referencing an undefined
        Jinja2 variable) is also invalid - referencing an entity that isn't
        loaded yet is not an error case here, since the correct way to do
        so (`states('media_player.x')`) always renders to a string.

        Args:
            raw_template: The template source to render and check.

        Returns:
            True if the template renders to a string, False if it fails to
            render or renders to a non-string value.

        """
        try:
            result = cv.template(raw_template).async_render(parse_result=True)
        except TemplateError:
            return False

        return isinstance(result, str)

    def _active_child_template_result_is_valid(self, raw_template: str) -> bool:
        """Check that active_child_template renders to an existing media_player entity_id.

        Args:
            raw_template: The template source to render and check.

        Returns:
            True if the template renders to a string that is empty, or the
            entity_id of an existing media_player entity, False otherwise
            (including if the template fails to render).

        """
        if not self._template_result_is_valid(raw_template):
            return False

        result = cv.template(raw_template).async_render(parse_result=True)
        if not result:
            return True

        state = self.hass.states.get(result)
        return state is not None and state.domain == MEDIA_PLAYER_DOMAIN

    async def async_step_config_guided_confirm(self, _user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Warn that guided configuration may lose custom command rules.

        Args:
            _user_input: Unused; menu selection is handled via dedicated steps.

        Returns:
            A menu flow result with "continue" and "back" options.

        """
        return self.async_show_menu(
            step_id="config_guided_confirm",
            menu_options={
                "config_guided_proceed": "I understand, continue and lose some data",
                "config_menu": "Go back",
            },
        )

    async def async_step_config_guided_proceed(self, _user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Proceed to the entity/action picker step after confirmation.

        Args:
            _user_input: Unused.

        Returns:
            The entity/action picker step's flow result.

        """
        return await self.async_step_config_commands()

    async def async_step_config_custom(self, _user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show the raw YAML commands step.

        Args:
            _user_input: Unused.

        Returns:
            The YAML commands step's flow result.

        """
        return await self.async_step_config_commands_custom()

    async def async_step_config_attributes(self, _user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Skip straight to the attributes step, keeping commands as-is.

        Args:
            _user_input: Unused.

        Returns:
            The attributes step's flow result.

        """
        return await self.async_step_config_attributes_custom()

    async def async_step_config_save(self, _user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Save the entry directly from the menu, keeping attributes as-is.

        Args:
            _user_input: Unused.

        Returns:
            The final flow result, creating or updating the config entry.

        """
        self._data.setdefault(CONF_ATTRS, {})
        self._data.setdefault(CONF_COMMANDS, {})
        return self._finalize()

    async def async_step_config_commands(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the entity/action picker step.

        Submitting this screen replaces all commands with what is picked
        here. Any existing command that cannot be represented as a plain
        entity+action pick (e.g. it has extra data or multiple targets) and
        is not re-entered here is discarded.

        Args:
            user_input: The submitted form data, or None on first display.

        Returns:
            The next step's flow result.

        """
        errors: dict[str, str] = {}
        incomplete_keys: set[str] = set()

        if user_input is not None:
            picked: dict[str, Any] = {}
            incomplete_by_section: dict[str, list[str]] = {}

            for category, keys in COMMAND_CATEGORIES:
                section_data = user_input.get(_category_section(category), {})

                for key in keys:
                    entity_id = section_data.get(_entity_field(key)) or section_data.get(
                        _entity_field(key, error=True),
                    )
                    action = section_data.get(_action_field(key))

                    if not entity_id and not action:
                        continue

                    if not entity_id or not action:
                        incomplete_by_section.setdefault(_category_section(category), []).append(key)
                        continue

                    picked[key] = {"action": action, "target": {"entity_id": entity_id}}

            if incomplete_by_section:
                for section_name, section_keys in incomplete_by_section.items():
                    errors[section_name] = "incomplete_command"
                    incomplete_keys.update(section_keys)
            else:
                self._data[CONF_COMMANDS] = picked
                return await self.async_step_config_menu()

        schema, suggested_values = self._commands_schema(user_input if errors else None, incomplete_keys)

        return self.async_show_form(
            step_id="config_commands",
            data_schema=self.add_suggested_values_to_schema(schema, suggested_values),
            errors=errors,
        )

    def _commands_schema(
        self,
        user_input: dict[str, Any] | None = None,
        incomplete_keys: set[str] | None = None,
    ) -> tuple[vol.Schema, dict[str, Any]]:
        """Build the entity/action picker schema, grouped by category.

        Each category is a collapsible section (collapsed by default), and
        all commands are always shown so a command can be redirected to any
        action regardless of what the children natively support. Existing
        commands are pre-filled where possible, but submitting this screen
        replaces all commands with what is picked here - a command left
        blank has no suggestion and is not carried over.

        The entity field has no schema default: it's pre-filled via a
        suggested_value instead, so clearing it in the UI is respected on
        submission instead of silently falling back to the old value.

        Args:
            user_input: The previously submitted (invalid) form data, if any,
                so the form can be redisplayed with what the user typed
                instead of reverting to the previously saved commands.
            incomplete_keys: Command keys whose entity field should carry a
                warning marker in its label, because only one of entity/action
                was filled in on the last submission.

        Returns:
            A tuple of the voluptuous schema for the actions form, and the
            suggested values to overlay on it (keyed by section name).

        """
        children = self._data.get(CONF_CHILDREN, [])
        existing_commands: dict[str, Any] = self._data.get(CONF_COMMANDS, {})
        incomplete_keys = incomplete_keys or set()
        schema_dict: dict[Any, Any] = {}
        suggested_values: dict[str, Any] = {}

        entity_selector_config: EntitySelectorConfig = {"domain": MEDIA_PLAYER_DOMAIN}
        if children:
            entity_selector_config["include_entities"] = children

        available_features = self._available_features()

        for category, keys in COMMAND_CATEGORIES:
            category_schema: dict[Any, Any] = {}
            category_suggested: dict[str, Any] = {}
            resubmitted = user_input.get(_category_section(category), {}) if user_input else None

            for key in keys:
                has_error = key in incomplete_keys
                entity_field = _entity_field(key, error=has_error)

                if resubmitted is not None:
                    suggested_entity = resubmitted.get(_entity_field(key)) or resubmitted.get(
                        _entity_field(key, error=True),
                    )
                    suggested_action = resubmitted.get(_action_field(key))
                else:
                    existing = existing_commands.get(key)
                    suggested_entity = _extract_entity_id(existing) if existing else None
                    if suggested_entity not in children:
                        suggested_entity = None

                    suggested_action = None
                    if suggested_entity:
                        suggested_action = (existing.get("action") if existing else None) or (
                            f"{MEDIA_PLAYER_DOMAIN}.{key}"
                        )

                if suggested_entity:
                    category_suggested[entity_field] = suggested_entity
                if suggested_action:
                    category_suggested[_action_field(key)] = suggested_action

                action_options = {
                    action
                    for action in ACTION_OPTIONS
                    if bool(available_features & ACTION_REQUIRED_FEATURE.get(action.split(".", 1)[1], 0))
                }
                if suggested_action:
                    action_options.add(suggested_action)

                category_schema[vol.Optional(entity_field)] = EntitySelector(entity_selector_config)
                category_schema[vol.Optional(_action_field(key))] = SelectSelector(
                    SelectSelectorConfig(options=sorted(action_options), mode=SelectSelectorMode.DROPDOWN),
                )

            if category_schema:
                section_name = _category_section(category)
                schema_dict[vol.Optional(section_name)] = section(
                    vol.Schema(category_schema),
                    SectionConfig({"collapsed": True}),
                )
                if category_suggested:
                    suggested_values[section_name] = category_suggested

        return vol.Schema(schema_dict), suggested_values

    async def async_step_config_commands_custom(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the YAML review step, the source of truth for commands.

        Args:
            user_input: The submitted form data, or None on first display.

        Returns:
            The next step's flow result (the config menu, to continue to
            attributes or revise the commands further).

        """
        errors: dict[str, str] = {}
        problems: list[str] = []

        if user_input is not None:
            raw_yaml = user_input.get(CONF_COMMANDS, "")

            if not raw_yaml:
                self._data[CONF_COMMANDS] = {}
                return await self.async_step_config_menu()

            try:
                parsed = yaml.safe_load(raw_yaml)
            except yaml.YAMLError:
                errors["base"] = "invalid_yaml"
            else:
                try:
                    validated = CMD_SCHEMA(parsed)
                except vol.Invalid:
                    errors["base"] = "invalid_action"
                else:
                    unknown_keys = self._find_unknown_command_keys(validated)
                    if unknown_keys:
                        problems.append(f"unknown command(s): {', '.join(sorted(unknown_keys))}")

                    unknown_entities = self._find_unknown_entities(validated)
                    if unknown_entities:
                        problems.append(f"unknown entity/entities: {', '.join(sorted(unknown_entities))}")

                    unknown_actions = self._find_unknown_actions(validated)
                    if unknown_actions:
                        problems.append(f"unknown action(s): {', '.join(sorted(unknown_actions))}")

                    if problems:
                        errors["base"] = "invalid_commands"
                    else:
                        self._data[CONF_COMMANDS] = validated

            if not errors:
                return await self.async_step_config_menu()

        description_placeholders = {"problems": _format_problems(problems)}
        schema, preview_yaml = self._commands_review_schema(user_input if errors else None)

        return self.async_show_form(
            step_id="config_commands_custom",
            data_schema=self.add_suggested_values_to_schema(schema, {CONF_COMMANDS: preview_yaml}),
            errors=errors,
            description_placeholders=description_placeholders,
        )

    @staticmethod
    def _find_unknown_command_keys(commands: dict[str, Any]) -> set[str]:
        """Find command keys that don't match a known command.

        Args:
            commands: The command key to command dict mapping.

        Returns:
            The set of keys that are not one of the known commands (e.g. a
            typo like "media_next_trackk"), which would otherwise silently
            have no effect.

        """
        return set(commands) - set(KNOWN_COMMAND_KEYS)

    def _find_unknown_entities(self, commands: dict[str, Any]) -> set[str]:
        """Find target entity_ids referenced in commands that don't exist.

        Args:
            commands: The command key to command dict mapping.

        Returns:
            The set of entity_ids referenced in a target that have no
            matching state in Home Assistant.

        """
        unknown: set[str] = set()

        for command in commands.values():
            entity_id = command.get("target", {}).get("entity_id")
            entity_ids = entity_id if isinstance(entity_id, list) else [entity_id] if entity_id else []

            for candidate in entity_ids:
                if not candidate or self.hass.states.get(candidate) is None:
                    unknown.add(candidate or "(empty)")

        return unknown

    def _find_unknown_actions(self, commands: dict[str, Any]) -> set[str]:
        """Find actions referenced in commands that don't match a registered service.

        Args:
            commands: The command key to command dict mapping.

        Returns:
            The set of "domain.service" actions that have no matching
            registered Home Assistant service.

        """
        unknown: set[str] = set()

        for command in commands.values():
            action = command.get("action")
            if not action or "." not in action:
                continue

            domain, _, service = action.partition(".")
            if not self.hass.services.has_service(domain, service):
                unknown.add(action)

        return unknown

    def _commands_review_schema(self, user_input: dict[str, Any] | None = None) -> tuple[vol.Schema, str]:
        """Build the review step schema, a single YAML textarea for all commands.

        The field has no schema default: it's pre-filled via a suggested_value
        instead, so clearing the textarea and submitting it empty is respected
        instead of the frontend silently reverting to the previous value.

        Args:
            user_input: The previously submitted (invalid) form data, if any,
                so the form can be redisplayed with what the user typed
                instead of reverting to the previously saved commands.

        Returns:
            A tuple of the voluptuous schema for the review form, and the
            suggested value to overlay on it.

        """
        if user_input is not None:
            preview_yaml = user_input.get(CONF_COMMANDS, "")
        else:
            existing_commands: dict[str, Any] = self._data.get(CONF_COMMANDS, {})
            preview_yaml = (
                yaml.safe_dump(json.loads(json.dumps(existing_commands)), sort_keys=False) if existing_commands else ""
            )

        schema = vol.Schema({vol.Optional(CONF_COMMANDS): TextSelector(TextSelectorConfig(multiline=True))})
        return schema, preview_yaml

    async def async_step_config_attributes_custom(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the raw YAML attribute overrides step.

        Args:
            user_input: The submitted form data, or None on first display.

        Returns:
            The config menu's flow result.

        """
        errors: dict[str, str] = {}
        problems: list[str] = []

        if user_input is not None:
            raw = user_input.get(CONF_ATTRS, "")
            parsed_attrs: dict[str, Any] = {}

            if raw:
                try:
                    parsed_attrs = ATTRS_SCHEMA(yaml.safe_load(raw))
                except (yaml.YAMLError, vol.Invalid):
                    errors["base"] = "invalid_yaml"
                else:
                    unknown_entities = self._find_unknown_attribute_entities(parsed_attrs)
                    if unknown_entities:
                        problems.append(f"unknown entity/entities: {', '.join(sorted(unknown_entities))}")

                    if problems:
                        errors["base"] = "invalid_commands"
                    else:
                        unknown_attrs = self._find_unknown_attribute_names(parsed_attrs)
                        if unknown_attrs:
                            _LOGGER.warning(
                                "Attributes not currently present on their referenced entity "
                                "(may be normal depending on state): %s",
                                ", ".join(sorted(unknown_attrs)),
                            )

            if not errors:
                self._data[CONF_ATTRS] = parsed_attrs
                return await self.async_step_config_menu()

        if errors:
            preview_yaml = user_input.get(CONF_ATTRS, "") if user_input else ""
        else:
            existing_attrs: dict[str, Any] = self._data.get(CONF_ATTRS, {})
            preview_yaml = (
                yaml.safe_dump(json.loads(json.dumps(existing_attrs)), sort_keys=False) if existing_attrs else ""
            )

        description_placeholders = {"problems": _format_problems(problems)}

        schema = vol.Schema({vol.Optional(CONF_ATTRS): TextSelector(TextSelectorConfig(multiline=True))})

        return self.async_show_form(
            step_id="config_attributes_custom",
            data_schema=self.add_suggested_values_to_schema(schema, {CONF_ATTRS: preview_yaml}),
            errors=errors,
            description_placeholders=description_placeholders,
        )

    @staticmethod
    def _parse_attribute_value(value: str) -> tuple[list[str], str | None]:
        """Split an attribute override value into its entity_ids and attribute name.

        Args:
            value: The raw value, e.g. "media_player.a-media_player.b|volume_level"
                or just "media_player.a" (state lookup, no attribute).

        Returns:
            A tuple of the list of referenced entity_ids and the optional
            attribute name.

        """
        entity_part, _, attr_part = value.partition("|")
        entity_ids = [entity_id.strip() for entity_id in entity_part.split("-") if entity_id.strip()]
        return entity_ids, attr_part.strip() or None

    def _find_unknown_attribute_entities(self, attrs: dict[str, Any]) -> set[str]:
        """Find entity_ids referenced in attribute overrides that don't exist.

        Args:
            attrs: The attribute name to "entity_id|attribute" mapping.

        Returns:
            The set of entity_ids that have no matching state in Home
            Assistant.

        """
        unknown: set[str] = set()

        for value in attrs.values():
            entity_ids, _attr_name = self._parse_attribute_value(value)
            for entity_id in entity_ids:
                if self.hass.states.get(entity_id) is None:
                    unknown.add(entity_id)

        return unknown

    def _find_unknown_attribute_names(self, attrs: dict[str, Any]) -> set[str]:
        """Find attribute names not currently present on their referenced entity.

        This is informational only: an entity may legitimately not expose an
        attribute in its current state (e.g. volume_level while off), so this
        does not block saving - it only helps catch obvious typos.

        Args:
            attrs: The attribute name to "entity_id|attribute" mapping.

        Returns:
            A set of "entity_id|attribute" strings for attributes not found
            on any of their referenced entities' current state.

        """
        missing: set[str] = set()

        for value in attrs.values():
            entity_ids, attr_name = self._parse_attribute_value(value)
            if attr_name is None:
                continue

            found = any(
                (state := self.hass.states.get(entity_id)) is not None and attr_name in state.attributes
                for entity_id in entity_ids
            )
            if not found:
                missing.add(value)

        return missing

    def _finalize(self) -> ConfigFlowResult:
        """Create or update the config entry with the accumulated data.

        Returns:
            The final flow result.

        """
        if self._reconfigure_entry is not None:
            return self.async_update_reload_and_abort(self._reconfigure_entry, data=self._data)

        return self.async_create_entry(title=self._title, data=self._data)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:  # pylint: disable=unused-argument
        """Handle a reconfigure request, going straight to the config menu.

        Args:
            user_input: Unused; reconfigure always re-enters at the config menu.

        Returns:
            The config menu's flow result.

        """
        entry = self._get_reconfigure_entry()
        self._reconfigure_entry = entry
        self._data = dict(entry.data)
        self._title = entry.title

        return await self.async_step_config_menu()

    async def async_step_import(self, import_data: dict[str, Any]) -> ConfigFlowResult:
        """Import an existing YAML platform configuration.

        Args:
            import_data: The PLATFORM_SCHEMA-validated YAML configuration.

        Returns:
            The resulting flow result, creating a config entry or aborting
            if one is already configured for this unique ID.

        """
        unique_id = import_data.get(CONF_UNIQUE_ID) or slugify(import_data[CONF_NAME])
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()

        active_child_template = import_data.get(CONF_ACTIVE_CHILD_TEMPLATE)
        state_template = import_data.get(CONF_STATE_TEMPLATE)

        data: dict[str, Any] = {
            CONF_NAME: import_data[CONF_NAME],
            CONF_CHILDREN: import_data.get(CONF_CHILDREN, []),
            CONF_COMMANDS: import_data.get(CONF_COMMANDS, {}),
            CONF_ATTRS: import_data.get(CONF_ATTRS, {}),
            CONF_BROWSE_MEDIA_ENTITY: import_data.get(CONF_BROWSE_MEDIA_ENTITY),
            CONF_UNIQUE_ID: unique_id,
            CONF_DEVICE_CLASS: import_data.get(CONF_DEVICE_CLASS),
            CONF_ACTIVE_CHILD_TEMPLATE: str(active_child_template) if active_child_template else None,
            CONF_STATE_TEMPLATE: str(state_template) if state_template else None,
        }

        async_create_issue(
            self.hass,
            DOMAIN,
            f"deprecated_yaml_{import_data[CONF_NAME]}",
            breaks_in_ha_version=None,
            is_fixable=False,
            issue_domain=DOMAIN,
            severity=IssueSeverity.WARNING,
            translation_key="deprecated_yaml",
            translation_placeholders={"integration_title": "Custom universal media player"},
        )

        return self.async_create_entry(title=data[CONF_NAME], data=data)
