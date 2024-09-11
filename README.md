# Custom universal media player for Home Assistant


[![Maintenair : bastgau](https://img.shields.io/badge/maintener-bastgau-orange?logo=github&logoColor=%23959da5&labelColor=%232d333a)](https://github.com/bastgau)
[![Made with Python](https://img.shields.io/badge/Made_with-Python-blue?style=flat&logo=python&logoColor=%23959da5&labelColor=%232d333a)](https://www.python.org/)
[![Made for Home Assistant](https://img.shields.io/badge/Made_for-Homeassistant-blue?style=flat&logo=homeassistant&logoColor=%23959da5&labelColor=%232d333a)](https://www.home-assistant.io/)
[![GitHub Release](https://img.shields.io/github/v/release/bastgau/ha-custom-universal-media-player?logo=github&logoColor=%23959da5&labelColor=%232d333a&color=%230e80c0)](https://github.com/bastgau/ha-custom-universal-media-player/releases)
[![HACS validation](https://github.com/bastgau/ha-custom-universal-media-player/actions/workflows/validate-for-hacs.yml/badge.svg)](https://github.com/bastgau/ha-custom-universal-media-player/actions/workflows/validate-for-hacs.yml)
[![HASSFEST validation](https://github.com/bastgau/ha-custom-universal-media-player/actions/workflows/validate-with-hassfest.yml/badge.svg)](https://github.com/bastgau/ha-custom-universal-media-player/actions/workflows/validate-with-hassfest.yml)

<p align="center" width="100%">
    <img src="https://brands.home-assistant.io/_/custom_universal_media_player/logo.png">
</p>

Original component : [Universal media player](https://www.home-assistant.io/integrations/universal/)

> A universal media player can combine multiple existing entities in Home Assistant into a single media player entity. This is used to create a single media player entity that can control an entire media center.

In the original [version](https://github.com/home-assistant/core/tree/dev/homeassistant/components/universal), the universal media player component cannot access to some child's attributes.

In the modified version (this version), these attributes are now accessible by the custom universal media player.

List of attributes added and now accessible:

- app_id
- app_name
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

The configuration has been unchanged. Please check the notice of the [universal media player](https://www.home-assistant.io/integrations/universal/#usage-examples).

## Example

The parent media player is a [Music Assistant](https://github.com/music-assistant/hass-music-assistant) media player.  
The child media player is a [Mini Google Home](https://www.home-assistant.io/integrations/cast). 

1. If the _Music Assistant media player_ is playing, the _custom universal media player_ will reflect its attributes except the attributes listed in attributes node.  
2. If the _Music Assistant media player_ is idle and _Google Home_ is playing, the _custom universal media player_ will change to reflect the active player attributes.

In this example, most actions are overridden by the child media player (_Google Home_). Only the specific _Music Assistant media player_ actions are *not* overridden.

```yaml
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

Enjoy!
