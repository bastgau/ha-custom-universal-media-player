"""Tests for the custom universal media player config flow."""

from typing import Any

from custom_components.custom_universal_media_player.config_flow import (
    CustomUniversalMediaPlayerConfigFlow,
    _action_field,
    _category_section,
    _detemplatize,
    _entity_field,
    _extract_entity_id,
    _format_problems,
    _is_simple_command,
)
from custom_components.custom_universal_media_player.const import (
    CONF_ACTIVE_CHILD_TEMPLATE,
    CONF_ATTRS,
    CONF_BROWSE_MEDIA_ENTITY,
    CONF_CHILDREN,
    CONF_COMMANDS,
    CONF_DEVICE_CLASS_NONE,
    DOMAIN,
)
import pytest

from homeassistant.components.media_player import (
    ATTR_INPUT_SOURCE_LIST,
    ATTR_MEDIA_VOLUME_MUTED,
    DOMAIN as MEDIA_PLAYER_DOMAIN,
    MediaPlayerDeviceClass,
    MediaPlayerEntityFeature,
)
from homeassistant.config_entries import SOURCE_IMPORT, SOURCE_USER
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_SUPPORTED_FEATURES,
    CONF_DEVICE_CLASS,
    CONF_NAME,
    CONF_STATE_TEMPLATE,
    CONF_UNIQUE_ID,
    SERVICE_TURN_ON,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import config_validation as cv, issue_registry as ir

from .conftest import CHILD_SPEAKER, CHILD_TV, build_config_entry

ALL_FEATURES = (
    MediaPlayerEntityFeature.TURN_ON
    | MediaPlayerEntityFeature.TURN_OFF
    | MediaPlayerEntityFeature.PLAY
    | MediaPlayerEntityFeature.PAUSE
    | MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.SELECT_SOURCE
)


@pytest.fixture(autouse=True)
async def _setup_environment(
    hass: HomeAssistant,
    enable_custom_integrations: None,  # noqa: ARG001
    media_player_component: None,  # noqa: ARG001
) -> None:
    """Make the integration loadable and register the media_player actions.

    Args:
        hass: The Home Assistant instance.
        enable_custom_integrations: Enables loading from custom_components.
        media_player_component: Registers the media_player actions.

    """
    hass.states.async_set(
        CHILD_TV,
        "off",
        {
            ATTR_SUPPORTED_FEATURES: ALL_FEATURES,
            ATTR_DEVICE_CLASS: MediaPlayerDeviceClass.TV,
        },
    )
    hass.states.async_set(
        CHILD_SPEAKER,
        "off",
        {
            ATTR_SUPPORTED_FEATURES: ALL_FEATURES,
            ATTR_DEVICE_CLASS: MediaPlayerDeviceClass.SPEAKER,
        },
    )


async def start_flow(hass: HomeAssistant, children: list[str] | None = None) -> str:
    """Walk the first two steps and stop on the configuration menu.

    Args:
        hass: The Home Assistant instance.
        children: The children to select, defaulting to both fake players.

    Returns:
        The flow id, sitting on the configuration menu.

    """
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Test player", CONF_CHILDREN: [CHILD_TV, CHILD_SPEAKER] if children is None else children},
    )
    assert result["step_id"] == "device_class"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_DEVICE_CLASS: CONF_DEVICE_CLASS_NONE},
    )
    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "config_menu"

    return result["flow_id"]


async def choose(hass: HomeAssistant, flow_id: str, step: str) -> dict[str, Any]:
    """Pick an option in a menu.

    Args:
        hass: The Home Assistant instance.
        flow_id: The running flow.
        step: The menu option to select.

    Returns:
        The resulting flow result.

    """
    return await hass.config_entries.flow.async_configure(flow_id, {"next_step_id": step})


async def test_user_flow_creates_an_entry(hass: HomeAssistant) -> None:
    """The shortest path through the flow creates a usable entry."""
    flow_id = await start_flow(hass)

    result = await choose(hass, flow_id, "config_save")

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Test player"
    unique_id = result["data"][CONF_UNIQUE_ID]
    assert len(unique_id) == 32
    assert result["data"] == {
        CONF_NAME: "Test player",
        CONF_CHILDREN: [CHILD_TV, CHILD_SPEAKER],
        CONF_UNIQUE_ID: unique_id,
        CONF_DEVICE_CLASS: None,
        CONF_ATTRS: {},
        CONF_COMMANDS: {},
    }

    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1
    assert entries[0].unique_id == unique_id


async def test_device_class_is_suggested_from_the_children(hass: HomeAssistant) -> None:
    """The most common device class among the children is suggested."""
    hass.states.async_set(
        "media_player.second_tv",
        "off",
        {ATTR_DEVICE_CLASS: MediaPlayerDeviceClass.TV},
    )

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Test player", CONF_CHILDREN: [CHILD_TV, "media_player.second_tv", CHILD_SPEAKER]},
    )

    assert result["description_placeholders"] == {"suggested_device_class": "TV"}


async def test_device_class_suggestion_without_children(hass: HomeAssistant) -> None:
    """With nothing to go on, no device class is suggested."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Test player", CONF_CHILDREN: []},
    )

    assert result["description_placeholders"] == {"suggested_device_class": "None"}


async def test_device_class_is_stored(hass: HomeAssistant) -> None:
    """A picked device class ends up in the entry data."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Test player", CONF_CHILDREN: [CHILD_TV]},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_DEVICE_CLASS: MediaPlayerDeviceClass.TV},
    )
    result = await choose(hass, result["flow_id"], "config_save")

    assert result["data"][CONF_DEVICE_CLASS] == MediaPlayerDeviceClass.TV


async def test_children_can_be_edited_from_the_menu(hass: HomeAssistant) -> None:
    """Editing the children goes back through the device class step."""
    flow_id = await start_flow(hass)

    result = await choose(hass, flow_id, "config_children")
    assert result["step_id"] == "children"

    result = await hass.config_entries.flow.async_configure(
        flow_id,
        {CONF_CHILDREN: [CHILD_SPEAKER]},
    )
    assert result["step_id"] == "device_class"

    result = await hass.config_entries.flow.async_configure(
        flow_id,
        {CONF_DEVICE_CLASS: CONF_DEVICE_CLASS_NONE},
    )
    result = await choose(hass, flow_id, "config_save")

    assert result["data"][CONF_CHILDREN] == [CHILD_SPEAKER]


async def test_device_class_can_be_edited_from_the_menu(hass: HomeAssistant) -> None:
    """The device class step is reachable again from the menu."""
    flow_id = await start_flow(hass)

    result = await choose(hass, flow_id, "config_device_class")

    assert result["step_id"] == "device_class"


async def test_guided_configuration_stores_the_picked_commands(hass: HomeAssistant) -> None:
    """The entity/action picker turns picks into commands."""
    flow_id = await start_flow(hass)

    result = await choose(hass, flow_id, "config_guided")
    assert result["step_id"] == "config_commands"

    result = await hass.config_entries.flow.async_configure(
        flow_id,
        {
            _category_section("power"): {
                _entity_field(SERVICE_TURN_ON): CHILD_TV,
                _action_field(SERVICE_TURN_ON): f"{MEDIA_PLAYER_DOMAIN}.{SERVICE_TURN_ON}",
            },
        },
    )
    assert result["type"] is FlowResultType.MENU

    result = await choose(hass, flow_id, "config_save")

    assert result["data"][CONF_COMMANDS] == {
        SERVICE_TURN_ON: {
            "action": f"{MEDIA_PLAYER_DOMAIN}.{SERVICE_TURN_ON}",
            "target": {"entity_id": CHILD_TV},
        },
    }


async def test_guided_configuration_rejects_a_half_filled_command(hass: HomeAssistant) -> None:
    """Picking an entity without an action is reported as incomplete."""
    flow_id = await start_flow(hass)
    await choose(hass, flow_id, "config_guided")

    result = await hass.config_entries.flow.async_configure(
        flow_id,
        {_category_section("power"): {_entity_field(SERVICE_TURN_ON): CHILD_TV}},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {_category_section("power"): "incomplete_command"}

    # The entity field is re-rendered with the marker asking for an action.
    fields = {str(key) for key in result["data_schema"].schema}
    assert _category_section("power") in fields


async def test_guided_configuration_needs_a_capable_child(hass: HomeAssistant) -> None:
    """Without a usable child the picker is replaced by a warning menu."""
    flow_id = await start_flow(hass, children=[])

    result = await choose(hass, flow_id, "config_guided")

    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "config_guided_no_children"

    result = await choose(hass, flow_id, "config_menu")
    assert result["step_id"] == "config_menu"


async def test_guided_configuration_needs_a_child_with_features(hass: HomeAssistant) -> None:
    """A child that supports nothing is as good as no child at all."""
    hass.states.async_set("media_player.dumb", "off", {ATTR_SUPPORTED_FEATURES: 0})

    flow_id = await start_flow(hass, children=["media_player.dumb"])

    result = await choose(hass, flow_id, "config_guided")

    assert result["step_id"] == "config_guided_no_children"


async def test_guided_configuration_warns_before_losing_custom_commands(
    hass: HomeAssistant,
) -> None:
    """A command the picker cannot express asks for confirmation first."""
    flow_id = await start_flow(hass)

    await choose(hass, flow_id, "config_custom")
    # Two target entities cannot be expressed by the guided picker.
    result = await hass.config_entries.flow.async_configure(
        flow_id,
        {
            CONF_COMMANDS: (
                "turn_on:\n"
                f"  action: {MEDIA_PLAYER_DOMAIN}.turn_on\n"
                "  target:\n"
                "    entity_id:\n"
                f"      - {CHILD_TV}\n"
                f"      - {CHILD_SPEAKER}\n"
            ),
        },
    )
    assert result["type"] is FlowResultType.MENU

    result = await choose(hass, flow_id, "config_guided")
    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "config_guided_confirm"

    result = await choose(hass, flow_id, "config_guided_proceed")
    assert result["step_id"] == "config_commands"


async def test_custom_yaml_commands_are_stored(hass: HomeAssistant) -> None:
    """A valid YAML command block is validated and stored."""
    flow_id = await start_flow(hass)

    result = await choose(hass, flow_id, "config_custom")
    assert result["step_id"] == "config_commands_custom"

    result = await hass.config_entries.flow.async_configure(
        flow_id,
        {
            CONF_COMMANDS: (
                f"turn_on:\n  action: {MEDIA_PLAYER_DOMAIN}.turn_on\n  target:\n    entity_id: {CHILD_TV}\n"
            ),
        },
    )
    assert result["type"] is FlowResultType.MENU

    result = await choose(hass, flow_id, "config_save")

    assert result["data"][CONF_COMMANDS] == {
        SERVICE_TURN_ON: {
            "action": f"{MEDIA_PLAYER_DOMAIN}.turn_on",
            # cv.SERVICE_SCHEMA normalises a single target to a list.
            "target": {"entity_id": [CHILD_TV]},
        },
    }


async def test_custom_yaml_commands_keep_templates_as_strings(hass: HomeAssistant) -> None:
    """Templates are stored as their source, since a Template is not JSON."""
    flow_id = await start_flow(hass)
    await choose(hass, flow_id, "config_custom")

    await hass.config_entries.flow.async_configure(
        flow_id,
        {
            CONF_COMMANDS: (
                "volume_set:\n"
                f"  action: {MEDIA_PLAYER_DOMAIN}.volume_set\n"
                "  target:\n"
                f"    entity_id: {CHILD_TV}\n"
                "  data:\n"
                '    volume_level: "{{ volume_level }}"\n'
            ),
        },
    )
    result = await choose(hass, flow_id, "config_save")

    assert result["data"][CONF_COMMANDS]["volume_set"]["data"] == {
        "volume_level": "{{ volume_level }}",
    }


async def test_custom_yaml_commands_can_be_cleared(hass: HomeAssistant) -> None:
    """Submitting an empty textarea removes every command."""
    flow_id = await start_flow(hass)
    await choose(hass, flow_id, "config_custom")
    await hass.config_entries.flow.async_configure(
        flow_id,
        {CONF_COMMANDS: f"turn_on:\n  action: {MEDIA_PLAYER_DOMAIN}.turn_on\n  target:\n    entity_id: {CHILD_TV}\n"},
    )

    await choose(hass, flow_id, "config_custom")
    result = await hass.config_entries.flow.async_configure(flow_id, {CONF_COMMANDS: ""})
    assert result["type"] is FlowResultType.MENU

    result = await choose(hass, flow_id, "config_save")
    assert result["data"][CONF_COMMANDS] == {}


@pytest.mark.parametrize(
    ("raw_yaml", "error", "problem"),
    [
        ("turn_on: [", "invalid_yaml", None),
        ("turn_on: not-a-command", "invalid_action", None),
        (
            f"turn_onn:\n  action: {MEDIA_PLAYER_DOMAIN}.turn_on\n  target:\n    entity_id: {CHILD_TV}\n",
            "invalid_commands",
            "unknown command(s): turn_onn",
        ),
        (
            f"turn_on:\n  action: {MEDIA_PLAYER_DOMAIN}.turn_on\n  target:\n    entity_id: media_player.nope\n",
            "invalid_commands",
            "unknown entity/entities: media_player.nope",
        ),
        (
            f"turn_on:\n  action: script.not_registered\n  target:\n    entity_id: {CHILD_TV}\n",
            "invalid_commands",
            "unknown action(s): script.not_registered",
        ),
    ],
)
async def test_custom_yaml_commands_are_rejected(
    hass: HomeAssistant,
    raw_yaml: str,
    error: str,
    problem: str | None,
) -> None:
    """Broken YAML, unknown keys, entities and actions are all caught."""
    flow_id = await start_flow(hass)
    await choose(hass, flow_id, "config_custom")

    result = await hass.config_entries.flow.async_configure(flow_id, {CONF_COMMANDS: raw_yaml})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}
    if problem is not None:
        assert problem in result["description_placeholders"]["problems"]


async def test_attributes_yaml_is_stored(hass: HomeAssistant) -> None:
    """A valid attribute override block is validated and stored."""
    flow_id = await start_flow(hass)

    result = await choose(hass, flow_id, "config_attributes")
    assert result["step_id"] == "config_attributes_custom"

    result = await hass.config_entries.flow.async_configure(
        flow_id,
        {CONF_ATTRS: f"{ATTR_INPUT_SOURCE_LIST}: {CHILD_TV}|{ATTR_INPUT_SOURCE_LIST}\n"},
    )
    assert result["type"] is FlowResultType.MENU

    result = await choose(hass, flow_id, "config_save")

    assert result["data"][CONF_ATTRS] == {
        ATTR_INPUT_SOURCE_LIST: f"{CHILD_TV}|{ATTR_INPUT_SOURCE_LIST}",
    }


async def test_attributes_yaml_can_be_cleared(hass: HomeAssistant) -> None:
    """An empty attributes textarea stores no override."""
    flow_id = await start_flow(hass)
    await choose(hass, flow_id, "config_attributes")

    result = await hass.config_entries.flow.async_configure(flow_id, {CONF_ATTRS: ""})
    assert result["type"] is FlowResultType.MENU

    result = await choose(hass, flow_id, "config_save")
    assert result["data"][CONF_ATTRS] == {}


async def test_attributes_yaml_rejects_invalid_yaml(hass: HomeAssistant) -> None:
    """Attributes that don't parse are reported on the form."""
    flow_id = await start_flow(hass)
    await choose(hass, flow_id, "config_attributes")

    result = await hass.config_entries.flow.async_configure(flow_id, {CONF_ATTRS: "source_list: ["})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_yaml"}


async def test_attributes_yaml_rejects_unknown_entities(hass: HomeAssistant) -> None:
    """An override pointing at a missing entity is reported."""
    flow_id = await start_flow(hass)
    await choose(hass, flow_id, "config_attributes")

    result = await hass.config_entries.flow.async_configure(
        flow_id,
        {CONF_ATTRS: "source_list: media_player.nope|source_list\n"},
    )

    assert result["errors"] == {"base": "invalid_commands"}
    assert "media_player.nope" in result["description_placeholders"]["problems"]


async def test_attributes_yaml_only_warns_about_unknown_attributes(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An attribute missing from the current state is a warning, not an error."""
    flow_id = await start_flow(hass)
    await choose(hass, flow_id, "config_attributes")

    result = await hass.config_entries.flow.async_configure(
        flow_id,
        {CONF_ATTRS: f"{ATTR_MEDIA_VOLUME_MUTED}: {CHILD_TV}|{ATTR_MEDIA_VOLUME_MUTED}\n"},
    )

    assert result["type"] is FlowResultType.MENU
    assert "Attributes not currently present" in caplog.text


async def test_advanced_settings_are_stored(hass: HomeAssistant) -> None:
    """Templates and the browse media entity survive to the entry data."""
    flow_id = await start_flow(hass)

    result = await choose(hass, flow_id, "config_advanced")
    assert result["step_id"] == "advanced"

    result = await hass.config_entries.flow.async_configure(
        flow_id,
        {
            CONF_BROWSE_MEDIA_ENTITY: CHILD_SPEAKER,
            CONF_ACTIVE_CHILD_TEMPLATE: f"{{{{ '{CHILD_TV}' }}}}",
            CONF_STATE_TEMPLATE: "{{ 'playing' }}",
        },
    )
    assert result["type"] is FlowResultType.MENU

    result = await choose(hass, flow_id, "config_save")

    assert result["data"][CONF_BROWSE_MEDIA_ENTITY] == CHILD_SPEAKER
    assert result["data"][CONF_ACTIVE_CHILD_TEMPLATE] == f"{{{{ '{CHILD_TV}' }}}}"
    assert result["data"][CONF_STATE_TEMPLATE] == "{{ 'playing' }}"


async def test_advanced_settings_can_be_left_empty(hass: HomeAssistant) -> None:
    """Submitting the advanced step untouched stores nothing."""
    flow_id = await start_flow(hass)
    await choose(hass, flow_id, "config_advanced")

    result = await hass.config_entries.flow.async_configure(flow_id, {})
    assert result["type"] is FlowResultType.MENU

    result = await choose(hass, flow_id, "config_save")

    assert result["data"][CONF_BROWSE_MEDIA_ENTITY] is None
    assert result["data"][CONF_ACTIVE_CHILD_TEMPLATE] is None
    assert result["data"][CONF_STATE_TEMPLATE] is None


@pytest.mark.parametrize(
    "raw_template",
    [
        "{{ 1 == 1 }}",  # renders to a boolean
        "{{ undefined_variable.attribute }}",  # fails to render
    ],
)
async def test_state_template_must_render_to_a_string(
    hass: HomeAssistant,
    raw_template: str,
) -> None:
    """A state template that isn't a string would break at runtime."""
    flow_id = await start_flow(hass)
    await choose(hass, flow_id, "config_advanced")

    result = await hass.config_entries.flow.async_configure(
        flow_id,
        {CONF_STATE_TEMPLATE: raw_template},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_STATE_TEMPLATE: "invalid_template_result"}


@pytest.mark.parametrize(
    "raw_template",
    [
        "{{ 'media_player.nope' }}",  # no such entity
        "{{ 'switch.amplifier' }}",  # not a media player
        "{{ 1 == 1 }}",  # not even a string
    ],
)
async def test_active_child_template_must_name_a_media_player(
    hass: HomeAssistant,
    raw_template: str,
) -> None:
    """The active child template has to resolve to a real media player."""
    hass.states.async_set("switch.amplifier", "on")

    flow_id = await start_flow(hass)
    await choose(hass, flow_id, "config_advanced")

    result = await hass.config_entries.flow.async_configure(
        flow_id,
        {CONF_ACTIVE_CHILD_TEMPLATE: raw_template},
    )

    assert result["errors"] == {CONF_ACTIVE_CHILD_TEMPLATE: "invalid_active_child_template_result"}


async def test_active_child_template_may_render_to_nothing(hass: HomeAssistant) -> None:
    """An empty result is allowed: no child is active right now."""
    flow_id = await start_flow(hass)
    await choose(hass, flow_id, "config_advanced")

    result = await hass.config_entries.flow.async_configure(
        flow_id,
        {CONF_ACTIVE_CHILD_TEMPLATE: "{{ '' }}"},
    )

    assert result["type"] is FlowResultType.MENU


async def test_reconfigure_updates_the_entry(hass: HomeAssistant) -> None:
    """Reconfiguring starts on the menu and updates the existing entry."""
    entry = build_config_entry(**{CONF_CHILDREN: [CHILD_TV]})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "config_menu"

    result = await choose(hass, result["flow_id"], "config_children")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CHILDREN: [CHILD_TV, CHILD_SPEAKER]},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_DEVICE_CLASS: MediaPlayerDeviceClass.SPEAKER},
    )
    result = await choose(hass, result["flow_id"], "config_save")
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_CHILDREN] == [CHILD_TV, CHILD_SPEAKER]
    assert entry.data[CONF_DEVICE_CLASS] == MediaPlayerDeviceClass.SPEAKER
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_import_creates_an_entry_and_a_repair_issue(
    hass: HomeAssistant,
    issue_registry: ir.IssueRegistry,
) -> None:
    """Importing a YAML config creates the entry and warns about deprecation."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_IMPORT},
        data={
            CONF_NAME: "Imported player",
            CONF_CHILDREN: [CHILD_TV],
            CONF_COMMANDS: {
                SERVICE_TURN_ON: {
                    "action": f"{MEDIA_PLAYER_DOMAIN}.turn_on",
                    "data": {"volume_level": cv.template("{{ 0.5 }}")},
                },
            },
            CONF_ATTRS: {ATTR_INPUT_SOURCE_LIST: f"{CHILD_TV}|{ATTR_INPUT_SOURCE_LIST}"},
            CONF_ACTIVE_CHILD_TEMPLATE: cv.template(f"{{{{ '{CHILD_TV}' }}}}"),
            CONF_STATE_TEMPLATE: cv.template("{{ 'playing' }}"),
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Imported player"
    assert result["data"][CONF_UNIQUE_ID] == "imported_player"
    assert result["data"][CONF_ACTIVE_CHILD_TEMPLATE] == f"{{{{ '{CHILD_TV}' }}}}"
    assert result["data"][CONF_STATE_TEMPLATE] == "{{ 'playing' }}"
    # Templates cannot be serialized into the entry, they are stored raw.
    assert result["data"][CONF_COMMANDS][SERVICE_TURN_ON]["data"] == {"volume_level": "{{ 0.5 }}"}

    assert issue_registry.async_get_issue(DOMAIN, "deprecated_yaml_Imported player") is not None


async def test_import_keeps_the_configured_unique_id(hass: HomeAssistant) -> None:
    """An explicit unique id in the YAML config is honoured."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_IMPORT},
        data={CONF_NAME: "Imported player", CONF_UNIQUE_ID: "my-own-id"},
    )

    assert result["data"][CONF_UNIQUE_ID] == "my-own-id"
    assert result["data"][CONF_CHILDREN] == []


async def test_import_is_only_done_once(hass: HomeAssistant) -> None:
    """Importing the same YAML config twice aborts the second time."""
    data = {CONF_NAME: "Imported player"}

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_IMPORT},
        data=dict(data),
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_IMPORT},
        data=dict(data),
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ({"target": {"entity_id": CHILD_TV}}, CHILD_TV),
        ({"target": {"entity_id": [CHILD_TV]}}, CHILD_TV),
        ({"target": {"entity_id": [CHILD_TV, CHILD_SPEAKER]}}, None),
        ({"target": {"entity_id": []}}, None),
        ({"target": {}}, None),
        ({}, None),
    ],
)
def test_extract_entity_id(command: dict[str, Any], expected: str | None) -> None:
    """A command only yields a target entity when it has exactly one."""
    assert _extract_entity_id(command) == expected


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        (None, True),
        ({}, True),
        ({"action": "media_player.turn_on", "target": {"entity_id": CHILD_TV}}, True),
        ({"action": "media_player.turn_on", "target": {"entity_id": [CHILD_TV]}}, True),
        ({"action": "media_player.turn_on"}, False),
        ({"action": "media_player.turn_on", "target": {"entity_id": [CHILD_TV, CHILD_SPEAKER]}}, False),
        ({"action": "x.y", "target": {"entity_id": CHILD_TV}, "data": {"a": 1}}, False),
        ({"action": "x.y", "target": {"entity_id": CHILD_TV, "area_id": "kitchen"}}, False),
    ],
)
def test_is_simple_command(command: dict[str, Any] | None, expected: bool) -> None:
    """Only a plain action plus single entity target is a simple command."""
    assert _is_simple_command(command) is expected


def test_detemplatize_walks_the_whole_command() -> None:
    """Every Template in a command is replaced by its source string."""
    command = {
        "action": cv.template("{{ 'media_player.turn_on' }}"),
        "data": {"values": [cv.template("{{ 1 }}"), "plain", 2]},
    }

    assert _detemplatize(command) == {
        "action": "{{ 'media_player.turn_on' }}",
        "data": {"values": ["{{ 1 }}", "plain", 2]},
    }


def test_format_problems() -> None:
    """Problems are rendered as a bullet list, and nothing when there are none."""
    assert _format_problems([]) == ""
    assert _format_problems(["first", "second"]) == "\n\nInvalid configuration:\n- first\n- second"


def test_field_name_helpers() -> None:
    """The form field names are derived from the command key."""
    assert _entity_field(SERVICE_TURN_ON) == "turn_on__entity"
    assert _entity_field(SERVICE_TURN_ON, error=True) == "turn_on__entity_error"
    assert _action_field(SERVICE_TURN_ON) == "turn_on__action"
    assert _category_section("power") == "category_power"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (CHILD_TV, ([CHILD_TV], None)),
        (f"{CHILD_TV}|volume_level", ([CHILD_TV], "volume_level")),
        (f" {CHILD_TV} - {CHILD_SPEAKER} | volume_level ", ([CHILD_TV, CHILD_SPEAKER], "volume_level")),
        (f"{CHILD_TV}|", ([CHILD_TV], None)),
        ("", ([], None)),
    ],
)
def test_parse_attribute_value(value: str, expected: tuple[list[str], str | None]) -> None:
    """An attribute override splits into its entities and attribute name."""
    assert CustomUniversalMediaPlayerConfigFlow._parse_attribute_value(value) == expected


async def test_find_unknown_entities_reports_an_empty_target(hass: HomeAssistant) -> None:
    """A target holding a blank entity id is reported as "(empty)"."""
    flow = CustomUniversalMediaPlayerConfigFlow()
    flow.hass = hass

    unknown = flow._find_unknown_entities({SERVICE_TURN_ON: {"target": {"entity_id": ["", CHILD_TV]}}})

    assert unknown == {"(empty)"}


async def test_find_unknown_actions_ignores_a_bare_action(hass: HomeAssistant) -> None:
    """An action without a domain is left to the schema validation."""
    flow = CustomUniversalMediaPlayerConfigFlow()
    flow.hass = hass

    assert flow._find_unknown_actions({SERVICE_TURN_ON: {"action": "turn_on"}}) == set()
    assert flow._find_unknown_actions({SERVICE_TURN_ON: {}}) == set()


def test_find_unknown_command_keys() -> None:
    """Keys that are not known commands are reported."""
    unknown = CustomUniversalMediaPlayerConfigFlow._find_unknown_command_keys(
        {SERVICE_TURN_ON: {}, "turn_onn": {}},
    )

    assert unknown == {"turn_onn"}


def _section_suggestions(result: dict[str, Any], category: str) -> dict[str, Any]:
    """Read back the values suggested for a category of the guided picker.

    Args:
        result: The flow result holding the picker's schema.
        category: The command category to read.

    Returns:
        The suggested value of every field of that category's section.

    """
    for key, value in result["data_schema"].schema.items():
        if str(key) != _category_section(category):
            continue
        return {
            str(field): field.description["suggested_value"]
            for field in value.schema.schema
            if field.description and "suggested_value" in field.description
        }
    pytest.fail(f"No section for category {category}")


async def test_guided_picker_is_prefilled_from_the_existing_commands(
    hass: HomeAssistant,
) -> None:
    """Re-entering the picker shows what is already configured."""
    flow_id = await start_flow(hass)
    await choose(hass, flow_id, "config_guided")
    await hass.config_entries.flow.async_configure(
        flow_id,
        {
            _category_section("power"): {
                _entity_field(SERVICE_TURN_ON): CHILD_TV,
                _action_field(SERVICE_TURN_ON): f"{MEDIA_PLAYER_DOMAIN}.{SERVICE_TURN_ON}",
            },
        },
    )

    result = await choose(hass, flow_id, "config_guided")

    assert _section_suggestions(result, "power") == {
        _entity_field(SERVICE_TURN_ON): CHILD_TV,
        _action_field(SERVICE_TURN_ON): f"{MEDIA_PLAYER_DOMAIN}.{SERVICE_TURN_ON}",
    }


async def test_guided_picker_keeps_an_action_the_children_do_not_support(
    hass: HomeAssistant,
) -> None:
    """A configured action stays selectable even outside the offered ones."""
    flow_id = await start_flow(hass)
    await choose(hass, flow_id, "config_custom")

    # None of the children advertises GROUPING, so join is not offered.
    await hass.config_entries.flow.async_configure(
        flow_id,
        {
            CONF_COMMANDS: (f"join:\n  action: {MEDIA_PLAYER_DOMAIN}.join\n  target:\n    entity_id: {CHILD_TV}\n"),
        },
    )

    result = await choose(hass, flow_id, "config_guided")

    assert _section_suggestions(result, "grouping") == {
        _entity_field("join"): CHILD_TV,
        _action_field("join"): f"{MEDIA_PLAYER_DOMAIN}.join",
    }


async def test_guided_picker_drops_a_command_targeting_a_dropped_child(
    hass: HomeAssistant,
) -> None:
    """A command aimed at an entity that is no longer a child is not suggested."""
    flow_id = await start_flow(hass, children=[CHILD_TV])
    await choose(hass, flow_id, "config_custom")
    await hass.config_entries.flow.async_configure(
        flow_id,
        {
            CONF_COMMANDS: (
                f"turn_on:\n  action: {MEDIA_PLAYER_DOMAIN}.turn_on\n  target:\n    entity_id: {CHILD_SPEAKER}\n"
            ),
        },
    )

    result = await choose(hass, flow_id, "config_guided")

    assert _section_suggestions(result, "power") == {}


async def test_attribute_override_without_an_attribute_name_is_not_checked(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An override reading a plain state has no attribute name to look for."""
    flow_id = await start_flow(hass)
    await choose(hass, flow_id, "config_attributes")

    result = await hass.config_entries.flow.async_configure(
        flow_id,
        {CONF_ATTRS: f"state: {CHILD_TV}\n"},
    )

    assert result["type"] is FlowResultType.MENU
    assert "Attributes not currently present" not in caplog.text
