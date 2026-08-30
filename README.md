# Custom universal media player for Home Assistant


[![Maintainer : bastgau](https://img.shields.io/badge/maintainer-bastgau-orange?logo=github&logoColor=%23959da5&labelColor=%232d333a)](https://github.com/bastgau)
[![Made with Python](https://img.shields.io/badge/Made_with-Python-blue?style=flat&logo=python&logoColor=%23959da5&labelColor=%232d333a)](https://www.python.org/)
[![Made for Home Assistant](https://img.shields.io/badge/Made_for-Homeassistant-blue?style=flat&logo=homeassistant&logoColor=%23959da5&labelColor=%232d333a)](https://www.home-assistant.io/)
[![GitHub Release](https://img.shields.io/github/v/release/bastgau/ha-custom-universal-media-player?logo=github&logoColor=%23959da5&labelColor=%232d333a&color=%230e80c0)](https://github.com/bastgau/ha-custom-universal-media-player/releases)
[![HACS validation](https://github.com/bastgau/ha-custom-universal-media-player/actions/workflows/validate-for-hacs.yml/badge.svg)](https://github.com/bastgau/ha-custom-universal-media-player/actions/workflows/validate-for-hacs.yml)
[![HASSFEST validation](https://github.com/bastgau/ha-custom-universal-media-player/actions/workflows/validate-with-hassfest.yml/badge.svg)](https://github.com/bastgau/ha-custom-universal-media-player/actions/workflows/validate-with-hassfest.yml)

<p align="center" width="100%">
    <img src="https://brands.home-assistant.io/_/custom_universal_media_player/logo.png">
</p>

> [!IMPORTANT]
> Starting from this version, this integration requires **Home Assistant 2026.7.0 or newer**. If you are running an older version of Home Assistant, please stay on a previous release of this integration.

Original component : [Universal media player](https://www.home-assistant.io/integrations/universal/)

> A universal media player can combine multiple existing entities in Home Assistant into a single media player entity. This is used to create a single media player entity that can control an entire media center.

In the original [version](https://github.com/home-assistant/core/tree/dev/homeassistant/components/universal), the universal media player component cannot access some of the child's attributes.

In the modified version (this version), these attributes are now accessible by the custom universal media player.

List of attributes added and now accessible:

- app_id
- app_name
- group_members
- media_album_artist
- media_album_name
- media_artist
- media_channel
- media_content_type
- media_duration
- media_episode
- media_image_url
- media_playlist
- media_position
- media_position_updated_at
- media_season
- media_series_title
- media_title
- media_track

## Installation

### Installation via HACS

1. Add this repository as a custom repository to HACS:

[![Add Repository](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=bastgau&repository=ha-custom-universal-media-player&category=Integration)

2. Use HACS to install the integration.
3. Restart Home Assistant.
4. Set up the integration using the UI:

[![Add Integration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=custom_universal_media_player)


### Manual Installation

1. Download the integration files from the GitHub repository.
2. Place the integration folder in the custom_components directory of Home Assistant.
3. Restart Home Assistant.
4. Set up the integration using the UI:

[![Add Integration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=custom_universal_media_player)


## Configuration

The integration is configured through the Home Assistant UI (config flow), no YAML required. After adding the integration:

1. **Name and children**: give the entity a name and pick the child `media_player` entities to combine.
2. **Device class**: confirm or change the suggested device class (based on the children's own device class), or set it to `None`.
3. **Configuration menu**, from which you can:
   - **Edit children** or **Edit device class** at any time.
   - **Configure commands - Guided**: pick, per command (power, playback, navigation, volume, source, grouping), which child entity and action it should call.
   - **Configure commands - Custom (YAML)**: review or write the raw command mapping as YAML, for cases the guided picker can't express (e.g. multiple target entities, extra service data).
   - **Configure attributes - Custom (YAML)**: override attributes by pointing them at a child entity's state or attribute (`entity_id|attribute`).
   - **Advanced configuration**: set an optional `browse_media` entity, an `active_child_template`, and a `state_template`.
   - **Finalize configuration** to save.

Existing YAML-based setups (`media_player: - platform: custom_universal_media_player`) are still imported automatically into a config entry, with a repair issue flagged to migrate away from YAML. Please check the notice of the [universal media player](https://www.home-assistant.io/integrations/universal/#usage-examples) for the underlying attribute/command semantics.

For as long as the YAML block is there it stays the source of truth: it is re-read on every restart and the config entry it created is updated to match, so an edit to the YAML takes effect. The flip side is that changes made to an imported entry through the UI are overwritten at the next restart - remove the YAML block first if you want to configure it from the UI.

Only `state_template`, `active_child_template` and the `data`/`target`/`action` of a command accept a template - same as the upstream [universal media player](https://www.home-assistant.io/integrations/universal/) this integration forks. `browse_media_entity` and the values under `attributes` are read as entity ids (`media_player.child`, `media_player.child|volume_level`, or several children joined by `-`); a Jinja2 block there is rejected at startup, or ignored with a warning in the log for an entry imported by an earlier version. `browse_media_entity` is checked more strictly here than upstream, so that the YAML asks for exactly what the UI's entity picker already enforces.

## Example

The parent media player is a [Music Assistant](https://github.com/music-assistant/hass-music-assistant) media player.  
The child media player is a [Mini Google Home](https://www.home-assistant.io/integrations/cast). 

1. If the _Music Assistant media player_ is playing, the _custom universal media player_ will reflect its attributes except the attributes listed in attributes node.  
2. If the _Music Assistant media player_ is idle and _Google Home_ is playing, the _custom universal media player_ will change to reflect the active player attributes.

In this example, most actions are overridden by the child media player (_Google Home_). Only the specific _Music Assistant media player_ actions are *not* overridden.

```yaml
media_player:
  - platform: custom_universal_media_player
    name: "Google Home Bureau"
    unique_id: custom_media_player_bureau
    device_class: speaker
    children:
      - media_player.mass_bureau
      - media_player.google_home_bureau
    commands:
      media_play:
        action: media_player.media_play
        target:
          entity_id: media_player.mass_bureau
      media_play_pause:
        action: media_player.media_play_pause
        target:
          entity_id: media_player.google_home_bureau
      turn_on:
        action: media_player.turn_on
        target:
          entity_id: media_player.google_home_bureau
      turn_off:
        action: media_player.turn_off
        target:
          entity_id: media_player.google_home_bureau
      volume_up:
        action: media_player.volume_up
        target:
          entity_id: media_player.google_home_bureau
      volume_down:
        action: media_player.volume_down
        target:
          entity_id: media_player.google_home_bureau
      media_pause:
        action: media_player.media_pause
        target:
          entity_id: media_player.google_home_bureau
      media_previous_track:
        action: media_player.media_previous_track
        target:
          entity_id: media_player.mass_bureau
      media_next_track:
        action: media_player.media_next_track
        target:
          entity_id: media_player.mass_bureau
    attributes:
      entity_picture: media_player.google_home_bureau|entity_picture
      is_volume_muted: media_player.google_home_bureau|is_volume_muted
      media_album_artist: media_player.google_home_bureau|media_album_artist
      media_album_name: media_player.google_home_bureau|media_album_name
      media_artist: media_player.google_home_bureau|media_artist
      media_image_url: media_player.google_home_bureau|entity_picture
      media_title: media_player.google_home_bureau|media_title
      source_list: media_player.google_home_bureau|source_list
      source: media_player.google_home_bureau|source
      state: media_player.google_home_bureau
      volume_level: media_player.google_home_bureau|volume_level
```

## Passing values to commands

Some commands carry a value: `volume_set` gets a volume, `select_source` gets a source name, `play_media` gets a media id. How that value reaches your command depends on what the command targets.

### Targeting the same `media_player` action

When a command calls `media_player.<the same command>`, the value is forwarded for you. This is what the guided configuration writes, and why the commands in the example above need no `data`:

```yaml
volume_set:
  action: media_player.volume_set
  target:
    entity_id: media_player.google_home_bureau
```

### Targeting anything else

When a command calls another action (`number.set_value`, `input_select.select_option`, `script.*`, ...), that action has its own fields and would reject the media player's ones. Read the value from a Jinja2 variable instead, and put it in the field the action actually expects:

```yaml
volume_set:
  action: number.set_value
  target:
    entity_id: number.rx_v685_volume
  data:
    value: "{{ volume_level }}"       # not volume_level: ...
select_source:
  action: input_select.select_option
  target:
    entity_id: input_select.media_activity
  data:
    option: "{{ source }}"            # not source: ...
```

The variables available are the ones the command itself carries:

| Command | Variables |
| --- | --- |
| `volume_set` | `volume_level` (float, `0`-`1`) |
| `volume_mute` | `is_volume_muted` (boolean) |
| `select_source` | `source` |
| `select_sound_mode` | `sound_mode` |
| `play_media` | `media_content_type`, `media_content_id` |
| `shuffle_set` | `shuffle` (boolean) |
| `repeat_set` | `repeat` (`off`, `all`, `one`) |
| `join` | `group_members` (list of entity IDs) |

Every other command (`turn_on`, `media_play`, `volume_up`, `unjoin`, ...) carries no value, so its `data` only needs whatever the target action requires. Templates are free to read the rest of Home Assistant too, which is how a stepped volume is built without any variable:

```yaml
volume_up:
  action: number.set_value
  target:
    entity_id: number.rx_v685_volume
  data:
    value: "{{ states('number.rx_v685_volume') | float(0) + 0.01 }}"
```

Note that `volume_level` is expected in the `0`-`1` range on both sides. If the entity behind it uses another scale (a receiver's dB value, a `0`-`100` percentage), convert it in the template, and convert it back in the matching `attributes` entry.

## Contributing

Found a bug or have a feature request? Please open an [issue](https://github.com/bastgau/ha-custom-universal-media-player/issues) on GitHub.

## License

This project is licensed under the [MIT License](LICENSE).
