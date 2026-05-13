"""Unit tests for payload building helpers.

These tests are pure Python and do not require a running Home Assistant instance.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.scene_cache.coordinator import SceneCacheCoordinator
from custom_components.scene_cache.const import FILTER_MODE_EXCLUDE
from custom_components.scene_cache.payload import (
    _is_json_safe,
    _normalize_entity_state,
    _state_to_payload,
)


def _coordinator() -> SceneCacheCoordinator:
    hass = MagicMock()
    entry = MagicMock()
    entry.options = {"filter_mode": FILTER_MODE_EXCLUDE, "patterns": []}
    return SceneCacheCoordinator(hass, entry)


class TestIsJsonSafe:
    def test_primitives_are_safe(self):
        for value in ("hello", 42, 3.14, True, None):
            assert _is_json_safe(value) is True

    def test_nested_structure_is_safe(self):
        assert _is_json_safe({"a": [1, 2, {"b": "c"}]}) is True

    def test_arbitrary_object_is_not_safe(self):
        assert _is_json_safe(object()) is False

    def test_object_inside_list_is_not_safe(self):
        assert _is_json_safe([1, object()]) is False


class TestStateToPayload:
    def test_basic_on_state(self):
        assert _state_to_payload("on", {}) == {"state": "on"}

    def test_attributes_are_included(self):
        payload = _state_to_payload("on", {"brightness": 200, "color_temp": 4000})
        assert payload["brightness"] == 200
        assert payload["color_temp"] == 4000

    def test_friendly_name_is_stripped(self):
        payload = _state_to_payload("on", {"friendly_name": "Kitchen Light"})
        assert "friendly_name" not in payload

    def test_all_non_replayable_attrs_stripped(self):
        non_replayable = {
            "friendly_name": "X",
            "supported_features": 1,
            "icon": "mdi:lamp",
            "entity_picture": "/img.png",
            "assumed_state": True,
            "device_class": "light",
            "unit_of_measurement": "lx",
            "attribution": "data by X",
            "restored": True,
        }
        payload = _state_to_payload("on", non_replayable)
        for key in non_replayable:
            assert key not in payload

    def test_non_serializable_attribute_is_stripped(self):
        payload = _state_to_payload("on", {"bad_attr": object()})
        assert "bad_attr" not in payload

    def test_state_key_in_attributes_does_not_duplicate(self):
        payload = _state_to_payload("on", {"state": "off", "brightness": 100})
        assert payload["state"] == "on"
        assert list(payload.keys()).count("state") == 1

    def test_none_state_is_omitted(self):
        payload = _state_to_payload(None, {"brightness": 100})
        assert "state" not in payload


class TestNormalizeEntityState:
    def test_string_becomes_state_dict(self):
        assert _normalize_entity_state("on") == {"state": "on"}

    def test_dict_with_state_preserved(self):
        result = _normalize_entity_state({"state": "on", "brightness": 200})
        assert result["state"] == "on"
        assert result["brightness"] == 200

    def test_dict_without_state_allowed(self):
        result = _normalize_entity_state({"brightness": 200})
        assert result["brightness"] == 200
        assert "state" not in result


class TestBuildPayload:
    def test_entities_dict_with_string_state(self):
        c = _coordinator()
        payload = c._build_payload(
            {"scene_id": "test", "entities": {"light.kitchen": "on"}}
        )
        assert payload["light.kitchen"] == {"state": "on"}

    def test_entities_dict_with_full_state(self):
        c = _coordinator()
        payload = c._build_payload(
            {
                "scene_id": "test",
                "entities": {"light.kitchen": {"state": "on", "brightness": 200}},
            }
        )
        assert payload["light.kitchen"]["brightness"] == 200

    def test_snapshot_entities_reads_hass_state(self):
        c = _coordinator()
        mock_state = MagicMock()
        mock_state.state = "on"
        mock_state.attributes = {"brightness": 100}
        c.hass.states.get.return_value = mock_state

        payload = c._build_payload(
            {"scene_id": "test", "snapshot_entities": ["light.living"]}
        )

        assert payload["light.living"]["state"] == "on"
        assert payload["light.living"]["brightness"] == 100
        c.hass.states.get.assert_called_once_with("light.living")

    def test_missing_snapshot_entity_is_skipped(self):
        c = _coordinator()
        c.hass.states.get.return_value = None
        payload = c._build_payload(
            {"scene_id": "test", "snapshot_entities": ["light.ghost"]}
        )
        assert "light.ghost" not in payload

    def test_entities_and_snapshot_entities_combined(self):
        c = _coordinator()
        mock_state = MagicMock()
        mock_state.state = "off"
        mock_state.attributes = {}
        c.hass.states.get.return_value = mock_state

        payload = c._build_payload(
            {
                "scene_id": "test",
                "entities": {"light.kitchen": "on"},
                "snapshot_entities": ["light.living"],
            }
        )
        assert "light.kitchen" in payload
        assert "light.living" in payload

    def test_empty_service_data_returns_empty_payload(self):
        c = _coordinator()
        assert c._build_payload({"scene_id": "test"}) == {}

    def test_snapshot_entity_friendly_name_stripped(self):
        c = _coordinator()
        mock_state = MagicMock()
        mock_state.state = "on"
        mock_state.attributes = {"brightness": 80, "friendly_name": "Living Room"}
        c.hass.states.get.return_value = mock_state

        payload = c._build_payload(
            {"scene_id": "test", "snapshot_entities": ["light.living"]}
        )
        assert "friendly_name" not in payload["light.living"]
        assert "brightness" in payload["light.living"]
