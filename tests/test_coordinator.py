"""Integration tests for SceneCacheCoordinator.

Uses a real (test) HomeAssistant instance via pytest-homeassistant-custom-component.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import EVENT_CALL_SERVICE
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.scene_cache.const import (
    DOMAIN,
    FILTER_MODE_EXCLUDE,
    FILTER_MODE_INCLUDE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _entry_with_options(hass: HomeAssistant, filter_mode: str, patterns: list[str]):
    e = MockConfigEntry(
        domain=DOMAIN,
        options={"filter_mode": filter_mode, "patterns": patterns},
        unique_id=DOMAIN,
    )
    e.add_to_hass(hass)
    return e


async def _setup(hass: HomeAssistant, entry):
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return hass.data[DOMAIN][entry.entry_id]


async def _fire_scene_create(hass: HomeAssistant, scene_id: str, **service_data):
    hass.bus.async_fire(
        EVENT_CALL_SERVICE,
        {
            "domain": "scene",
            "service": "create",
            "service_data": {"scene_id": scene_id, **service_data},
        },
    )
    await hass.async_block_till_done()


# ---------------------------------------------------------------------------
# Caching behaviour
# ---------------------------------------------------------------------------

class TestCaching:
    async def test_scene_create_event_populates_cache(self, hass: HomeAssistant, entry):
        coordinator = await _setup(hass, entry)

        await _fire_scene_create(hass, "party", entities={"light.kitchen": "on"})

        assert "party" in coordinator._cached
        assert coordinator._cached["party"]["light.kitchen"]["state"] == "on"

    async def test_scene_create_with_attrs_persisted(self, hass: HomeAssistant, entry):
        coordinator = await _setup(hass, entry)

        await _fire_scene_create(
            hass, "party",
            entities={"light.kitchen": {"state": "on", "brightness": 200}},
        )

        assert coordinator._cached["party"]["light.kitchen"]["brightness"] == 200

    async def test_repeated_create_overwrites_cache(self, hass: HomeAssistant, entry):
        coordinator = await _setup(hass, entry)

        await _fire_scene_create(hass, "party", entities={"light.kitchen": "on"})
        await _fire_scene_create(hass, "party", entities={"light.kitchen": "off"})

        assert coordinator._cached["party"]["light.kitchen"]["state"] == "off"

    async def test_excluded_scene_is_not_cached(self, hass: HomeAssistant):
        e = _entry_with_options(hass, FILTER_MODE_EXCLUDE, ["scene.tmp_*"])
        coordinator = await _setup(hass, e)

        await _fire_scene_create(hass, "tmp_test", entities={"light.x": "off"})

        assert "tmp_test" not in coordinator._cached

    async def test_included_scene_is_cached(self, hass: HomeAssistant):
        e = _entry_with_options(hass, FILTER_MODE_INCLUDE, ["scene.party_*"])
        coordinator = await _setup(hass, e)

        await _fire_scene_create(hass, "party_lights", entities={"light.x": "on"})
        await _fire_scene_create(hass, "bedtime", entities={"light.y": "off"})

        assert "party_lights" in coordinator._cached
        assert "bedtime" not in coordinator._cached

    async def test_non_scene_service_call_ignored(self, hass: HomeAssistant, entry):
        coordinator = await _setup(hass, entry)

        hass.bus.async_fire(
            EVENT_CALL_SERVICE,
            {"domain": "light", "service": "turn_on", "service_data": {}},
        )
        await hass.async_block_till_done()

        assert coordinator._cached == {}

    async def test_scene_service_other_than_create_ignored(self, hass: HomeAssistant, entry):
        coordinator = await _setup(hass, entry)

        hass.bus.async_fire(
            EVENT_CALL_SERVICE,
            {"domain": "scene", "service": "apply", "service_data": {"entity_id": "scene.x"}},
        )
        await hass.async_block_till_done()

        assert coordinator._cached == {}

    async def test_create_without_scene_id_ignored(self, hass: HomeAssistant, entry):
        coordinator = await _setup(hass, entry)

        hass.bus.async_fire(
            EVENT_CALL_SERVICE,
            {"domain": "scene", "service": "create", "service_data": {"entities": {}}},
        )
        await hass.async_block_till_done()

        assert coordinator._cached == {}


# ---------------------------------------------------------------------------
# Restore behaviour
# ---------------------------------------------------------------------------

class TestRestore:
    async def test_cached_scenes_are_restored_on_setup(self, hass: HomeAssistant, entry):
        initial_cache = {
            "scenes": {"party": {"light.kitchen": {"state": "on"}}}
        }
        restore_calls = []

        async def fake_service_call(domain, service, data=None, blocking=False, **kwargs):
            restore_calls.append({"domain": domain, "service": service, "data": data})

        with patch("custom_components.scene_cache.Store") as MockStore:
            store_inst = MagicMock()
            store_inst.async_load = AsyncMock(return_value=initial_cache)
            store_inst.async_delay_save = MagicMock()
            store_inst.async_save = AsyncMock()
            MockStore.return_value = store_inst

            with patch.object(hass.services, "async_call", side_effect=fake_service_call):
                await hass.config_entries.async_setup(entry.entry_id)
                await hass.async_block_till_done()

        assert any(
            c["domain"] == "scene"
            and c["service"] == "create"
            and (c["data"] or {}).get("scene_id") == "party"
            for c in restore_calls
        )

    async def test_restore_skips_already_existing_scene(self, hass: HomeAssistant, entry):
        initial_cache = {
            "scenes": {"party": {"light.kitchen": {"state": "on"}}}
        }
        hass.states.async_set("scene.party", "scening")

        restore_calls = []

        async def fake_service_call(domain, service, data=None, blocking=False, **kwargs):
            restore_calls.append({"domain": domain, "service": service, "data": data})

        with patch("custom_components.scene_cache.Store") as MockStore:
            store_inst = MagicMock()
            store_inst.async_load = AsyncMock(return_value=initial_cache)
            store_inst.async_delay_save = MagicMock()
            store_inst.async_save = AsyncMock()
            MockStore.return_value = store_inst

            with patch.object(hass.services, "async_call", side_effect=fake_service_call):
                await hass.config_entries.async_setup(entry.entry_id)
                await hass.async_block_till_done()

        scene_create_calls = [
            c for c in restore_calls
            if c["domain"] == "scene"
            and c["service"] == "create"
            and (c["data"] or {}).get("scene_id") == "party"
        ]
        assert scene_create_calls == []

    async def test_restore_skips_scene_that_fails_filter(self, hass: HomeAssistant):
        e = _entry_with_options(hass, FILTER_MODE_EXCLUDE, ["scene.tmp_*"])
        initial_cache = {
            "scenes": {
                "tmp_foo": {"light.x": {"state": "on"}},
                "party": {"light.y": {"state": "off"}},
            }
        }
        restore_calls = []

        async def fake_service_call(domain, service, data=None, blocking=False, **kwargs):
            restore_calls.append({"domain": domain, "service": service, "data": data})

        with patch("custom_components.scene_cache.Store") as MockStore:
            store_inst = MagicMock()
            store_inst.async_load = AsyncMock(return_value=initial_cache)
            store_inst.async_delay_save = MagicMock()
            store_inst.async_save = AsyncMock()
            MockStore.return_value = store_inst

            with patch.object(hass.services, "async_call", side_effect=fake_service_call):
                await hass.config_entries.async_setup(e.entry_id)
                await hass.async_block_till_done()

        restored_ids = [
            (c["data"] or {}).get("scene_id")
            for c in restore_calls
            if c["domain"] == "scene" and c["service"] == "create"
        ]
        assert "tmp_foo" not in restored_ids
        assert "party" in restored_ids


# ---------------------------------------------------------------------------
# apply_filter
# ---------------------------------------------------------------------------

class TestApplyFilter:
    async def test_drops_entries_no_longer_matching(self, hass: HomeAssistant, entry):
        coordinator = await _setup(hass, entry)
        coordinator._cached = {
            "tmp_test": {"light.x": {"state": "on"}},
            "party": {"light.y": {"state": "off"}},
        }

        entry.options = {
            "filter_mode": FILTER_MODE_EXCLUDE,
            "patterns": ["scene.tmp_*"],
        }
        await coordinator.async_apply_filter()

        assert "tmp_test" not in coordinator._cached
        assert "party" in coordinator._cached

    async def test_no_change_when_all_match(self, hass: HomeAssistant, entry):
        coordinator = await _setup(hass, entry)
        coordinator._cached = {"party": {"light.x": {"state": "on"}}}
        original = dict(coordinator._cached)

        await coordinator.async_apply_filter()

        assert coordinator._cached == original


# ---------------------------------------------------------------------------
# Services (forget / clear)
# ---------------------------------------------------------------------------

class TestServices:
    async def test_forget_removes_scene_by_bare_id(self, hass: HomeAssistant, entry):
        coordinator = await _setup(hass, entry)
        coordinator._cached["party"] = {"light.x": {"state": "on"}}

        await hass.services.async_call(
            DOMAIN, "forget", {"scene_id": "party"}, blocking=True
        )

        assert "party" not in coordinator._cached

    async def test_forget_accepts_full_entity_id(self, hass: HomeAssistant, entry):
        coordinator = await _setup(hass, entry)
        coordinator._cached["movie"] = {"light.x": {"state": "on"}}

        await hass.services.async_call(
            DOMAIN, "forget", {"scene_id": "scene.movie"}, blocking=True
        )

        assert "movie" not in coordinator._cached

    async def test_forget_nonexistent_scene_is_noop(self, hass: HomeAssistant, entry):
        coordinator = await _setup(hass, entry)

        await hass.services.async_call(
            DOMAIN, "forget", {"scene_id": "ghost"}, blocking=True
        )

        assert coordinator._cached == {}

    async def test_clear_empties_cache(self, hass: HomeAssistant, entry):
        coordinator = await _setup(hass, entry)
        coordinator._cached = {"a": {}, "b": {}}

        await hass.services.async_call(DOMAIN, "clear", {}, blocking=True)

        assert coordinator._cached == {}

    async def test_clear_on_empty_cache_is_noop(self, hass: HomeAssistant, entry):
        coordinator = await _setup(hass, entry)

        await hass.services.async_call(DOMAIN, "clear", {}, blocking=True)

        assert coordinator._cached == {}

    async def test_list_returns_all_cached_scenes(self, hass: HomeAssistant, entry):
        coordinator = await _setup(hass, entry)
        await _fire_scene_create(hass, "morning", entities={"light.hall": "on"})
        await _fire_scene_create(hass, "evening", entities={"light.living": "off"})

        result = await hass.services.async_call(
            DOMAIN, "list", {}, blocking=True, return_response=True
        )

        assert result["count"] == 2
        assert "morning" in result["scenes"]
        assert "evening" in result["scenes"]

    async def test_services_removed_after_last_entry_unloaded(
        self, hass: HomeAssistant, entry
    ):
        await _setup(hass, entry)
        assert hass.services.has_service(DOMAIN, "forget")

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

        assert not hass.services.has_service(DOMAIN, "forget")
        assert not hass.services.has_service(DOMAIN, "clear")
        assert not hass.services.has_service(DOMAIN, "list")


# ---------------------------------------------------------------------------
# scene.delete handling
# ---------------------------------------------------------------------------

class TestSceneDelete:
    async def test_delete_removes_from_cached(self, hass: HomeAssistant, entry):
        coordinator = await _setup(hass, entry)
        await _fire_scene_create(hass, "party", entities={"light.x": "on"})
        assert "party" in coordinator._cached

        hass.bus.async_fire(
            EVENT_CALL_SERVICE,
            {
                "domain": "scene",
                "service": "delete",
                "service_data": {"entity_id": "scene.party"},
            },
        )
        await hass.async_block_till_done()

        assert "party" not in coordinator._cached

    async def test_delete_removes_from_all_captured(self, hass: HomeAssistant, entry):
        coordinator = await _setup(hass, entry)
        await _fire_scene_create(hass, "party", entities={"light.x": "on"})
        assert "party" in coordinator._all_captured

        hass.bus.async_fire(
            EVENT_CALL_SERVICE,
            {
                "domain": "scene",
                "service": "delete",
                "service_data": {"entity_id": "scene.party"},
            },
        )
        await hass.async_block_till_done()

        assert "party" not in coordinator._all_captured

    async def test_delete_nonexistent_scene_is_noop(self, hass: HomeAssistant, entry):
        coordinator = await _setup(hass, entry)

        hass.bus.async_fire(
            EVENT_CALL_SERVICE,
            {
                "domain": "scene",
                "service": "delete",
                "service_data": {"entity_id": "scene.ghost"},
            },
        )
        await hass.async_block_till_done()

        assert coordinator._cached == {}
        assert coordinator._all_captured == {}

    async def test_delete_multiple_entity_ids(self, hass: HomeAssistant, entry):
        coordinator = await _setup(hass, entry)
        await _fire_scene_create(hass, "a", entities={"light.x": "on"})
        await _fire_scene_create(hass, "b", entities={"light.y": "on"})
        await _fire_scene_create(hass, "c", entities={"light.z": "on"})

        hass.bus.async_fire(
            EVENT_CALL_SERVICE,
            {
                "domain": "scene",
                "service": "delete",
                "service_data": {"entity_id": ["scene.a", "scene.b"]},
            },
        )
        await hass.async_block_till_done()

        assert "a" not in coordinator._cached
        assert "b" not in coordinator._cached
        assert "c" in coordinator._cached


# ---------------------------------------------------------------------------
# _all_captured vs _cached distinction
# ---------------------------------------------------------------------------

class TestAllCaptured:
    async def test_excluded_scene_stored_in_all_captured_not_cached(
        self, hass: HomeAssistant
    ):
        """All scene.create calls populate _all_captured; only filter-matching ones go to _cached."""
        e = _entry_with_options(hass, FILTER_MODE_EXCLUDE, ["scene.tmp_*"])
        coordinator = await _setup(hass, e)

        await _fire_scene_create(hass, "tmp_test", entities={"light.x": "off"})

        assert "tmp_test" not in coordinator._cached
        assert "tmp_test" in coordinator._all_captured

    async def test_non_matching_include_scene_in_all_captured_only(
        self, hass: HomeAssistant
    ):
        e = _entry_with_options(hass, FILTER_MODE_INCLUDE, ["scene.party_*"])
        coordinator = await _setup(hass, e)

        await _fire_scene_create(hass, "bedtime", entities={"light.y": "off"})

        assert "bedtime" not in coordinator._cached
        assert "bedtime" in coordinator._all_captured

    async def test_matching_scene_in_both(self, hass: HomeAssistant):
        e = _entry_with_options(hass, FILTER_MODE_INCLUDE, ["scene.party_*"])
        coordinator = await _setup(hass, e)

        await _fire_scene_create(hass, "party_lights", entities={"light.z": "on"})

        assert "party_lights" in coordinator._cached
        assert "party_lights" in coordinator._all_captured

    async def test_apply_filter_recomputes_cached_from_all_captured(
        self, hass: HomeAssistant, entry
    ):
        """Scenes in _all_captured become available in _cached when filter widens."""
        coordinator = await _setup(hass, entry)
        # Seed _all_captured directly (simulates previously stored non-matching scenes).
        coordinator._all_captured = {
            "tmp_test": {"light.x": {"state": "on"}},
            "party": {"light.y": {"state": "off"}},
        }

        # Filter now excludes tmp_* → only party matches
        entry.options = {
            "filter_mode": FILTER_MODE_EXCLUDE,
            "patterns": ["scene.tmp_*"],
        }
        await coordinator.async_apply_filter()

        assert "tmp_test" not in coordinator._cached
        assert "party" in coordinator._cached
        # But both still in _all_captured
        assert "tmp_test" in coordinator._all_captured
