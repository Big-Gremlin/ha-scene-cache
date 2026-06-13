# Scene Cache

Home Assistant custom integration that persists dynamically created scenes across restarts.

Scenes created via `scene.create` are stored in memory only and lost on every HA restart.
`scene_cache` writes them to persistent storage (`.storage/scene_cache.scenes`) and
automatically calls `scene.create` for each cached scene on the next startup.

## Installation

### HACS (recommended)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Big-Gremlin&repository=ha-scene-cache&category=integration)

1. HACS → Integrations → ⋮ → _Custom repositories_
2. Add the repository URL, category _Integration_
3. Install _Scene Cache_ and restart Home Assistant

### Manual

Copy `custom_components/scene_cache/` into the `config/custom_components/` folder of
your Home Assistant instance and restart HA.

## Features

- Stores every dynamically created scene in persistent storage
- Restores scenes on HA startup
- Per-instance filter mode: **Include** (allowlist) or **Exclude** (denylist)
- Glob patterns, e.g. `scene.party_*`
- Services for manual cleanup: `scene_cache.forget`, `scene_cache.clear`, `scene_cache.list`

## Setup

_Settings_ → _Devices & Services_ → _Add integration_ → **Scene Cache**.

The integration can only be set up once. Use _Configure_ to adjust the filter mode and
patterns at any time.

### Filter modes

| Mode      | No patterns                 | With patterns                                              |
| --------- | --------------------------- | ---------------------------------------------------------- |
| `exclude` | All scenes cached (default) | All scenes cached except those matching a pattern          |
| `include` | Nothing cached              | Only scenes whose `entity_id` matches a pattern are cached |

Patterns are glob expressions matched against the full `entity_id` (including the
`scene.` prefix):

```
scene.party_*
scene.vacation
scene.tmp_?
```

## Services

### `scene_cache.forget`

Removes a single scene from the cache. The scene itself keeps running until the next
restart — it simply will not be restored afterwards.

```yaml
service: scene_cache.forget
data:
  scene_id: party_mode # with or without the "scene." prefix
```

### `scene_cache.clear`

Clears the entire cache.

```yaml
service: scene_cache.clear
```

### `scene_cache.list`

Returns the active cache — all dynamic scenes that will be restored on the next
startup (i.e. those that pass the current filter). Useful for inspecting the cache
from Developer Tools (_Actions_ tab) or from an automation via `response_variable`.

```yaml
service: scene_cache.list
response_variable: cache
# cache.scenes  → dict of scene_id → stored entity states
#                  scene_id is without the "scene." prefix
#                  e.g. { "party_mode": { "light.wohnzimmer": { "state": "on", "brightness": 128 } } }
# cache.count   → number of scenes in the active cache
```

## How it works

1. On setup the integration loads the persistent cache from `.storage/scene_cache.scenes`.
2. It listens for `call_service` events on `domain=scene, service=create`.
   Every such call is converted to a replayable payload and written to storage
   (debounced, 5 s) — regardless of the active filter.
3. On HA start (`homeassistant_started`) it calls `scene.create` for each cached scene
   that passes the filter and does not already exist.
4. On shutdown (`homeassistant_stop`) the cache is flushed one final time.

## Notes

- Only dynamic scenes are covered. Scenes defined in `scenes.yaml` are persisted by HA
  itself and are not affected by this integration.
- The filter controls which scenes are **restored**, not which are **stored**. All
  dynamic scenes are always written to storage. Changing the filter only affects what
  gets recreated on the next startup (or immediately, for scenes newly matched by the
  updated filter that don't yet exist in HA).
- Presentational attributes (`friendly_name`, `supported_features`, `icon`, etc.) are
  stripped during serialisation as they are not needed for replay.

## License

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

This project uses the MIT License, for more details see the [license document](LICENSE).

---

[![Buy Me A Coffee](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://buymeacoffee.com/biggremlin)
