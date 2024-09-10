# Custom universal media player

Original component : [Universal media player](https://www.home-assistant.io/integrations/universal/)

> A universal media player can combine multiple existing entities in Home Assistant into a single media player entity. This is used to create a single media player entity that can control an entire media center.

In the original [version](https://github.com/home-assistant/core/tree/dev/homeassistant/components/universal), the universal media player component cannot access to some child's attributes.

In the modified version (this version), these attributes are now accessible by the custom universal media player.

List of attributes :

- media_content_type
- media_duration
- media_image_url
- media_title
- media_artist
- media_album_name
- media_album_artist
- media_track
- media_series_title
- media_season
- media_episode
- media_channel
- media_playlist
- app_id
- app_name
- media_position
- media_position_updated_at

Enjoy!
