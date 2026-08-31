# Tests

## Layout

```
tests/
├── common.py, conftest.py, syrupy.py, ...   vendored Home Assistant core test helpers
├── testing_config/, test_util/              vendored Home Assistant core test fixtures
└── components/
    └── custom_universal_media_player/       the tests of this integration
```

The layout mirrors `home-assistant/core`, so a test written here reads exactly
like a test written for a built-in integration.

## The vendored core helpers

Home Assistant does not publish its test helpers (`MockConfigEntry`, the `hass`
fixture, `async_fire_time_changed`, ...) as a package: they only live in the
core repository, under <https://github.com/home-assistant/core/tree/dev/tests>.

They are therefore vendored into this repository, **verbatim**, from the core
tag matching the `homeassistant` pin in `requirements.txt`. The vendored files
carry a header saying where they come from, and `tests/HA_CORE_VERSION` records
the tag they were taken from.

Do not edit them by hand. After bumping the `homeassistant` pin, refresh them:

```bash
python3 scripts/fetch_ha_test_helpers
```

They are excluded from linting and formatting (`tests/ruff.toml`) so they stay
byte-for-byte comparable with upstream.

These files are part of Home Assistant, copyright the Home Assistant
authors, and are licensed under the Apache License 2.0:
<https://github.com/home-assistant/core/blob/dev/LICENSE.md>.

## Running the tests

```bash
scripts/setup   # once, installs requirements_test.txt
scripts/test
```

`scripts/test` forwards its arguments to pytest, so a single file or test works
as usual:

```bash
scripts/test tests/components/custom_universal_media_player/test_config_flow.py
scripts/test -k device_class
```

Coverage of `custom_components/custom_universal_media_player` is reported with:

```bash
scripts/test --cov --cov-report=term-missing
```

## Writing a test

`tests/components/custom_universal_media_player/conftest.py` holds the shared
pieces:

- `setup_player(**data)` creates and loads a config entry from partial entry
  data, and returns it.
- `get_player(hass)` returns the entity object, so a command can be sent
  without going through the `media_player` actions the tests mock to observe
  what the player forwards to its children.
- `set_child_state(hass, entity_id, state, **attributes)` publishes the state
  of a fake child. The player only refreshes from the state change events of
  the entities it depends on, so children have to be published *after* it is
  set up.
