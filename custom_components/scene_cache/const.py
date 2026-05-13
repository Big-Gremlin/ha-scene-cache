"""Constants for the Scene Cache integration."""
from __future__ import annotations

DOMAIN = "scene_cache"

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.scenes"

SCENE_DOMAIN = "scene"

CONF_FILTER_MODE = "filter_mode"
CONF_PATTERNS = "patterns"

FILTER_MODE_INCLUDE = "include"
FILTER_MODE_EXCLUDE = "exclude"
FILTER_MODES = [FILTER_MODE_INCLUDE, FILTER_MODE_EXCLUDE]

DEFAULT_FILTER_MODE = FILTER_MODE_EXCLUDE

SAVE_DELAY_SECONDS = 5

SERVICE_FORGET = "forget"
SERVICE_CLEAR = "clear"
SERVICE_LIST = "list"

ATTR_SCENE_ID = "scene_id"

# State attributes that should not be persisted as part of a scene replay payload,
# because they are presentational/runtime metadata rather than restorable state.
NON_REPLAYABLE_ATTRIBUTES = frozenset(
    {
        "friendly_name",
        "supported_features",
        "icon",
        "entity_picture",
        "assumed_state",
        "device_class",
        "unit_of_measurement",
        "attribution",
        "restored",
    }
)
