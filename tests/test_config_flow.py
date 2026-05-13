"""Tests for the config flow and options flow."""
from __future__ import annotations

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.scene_cache.const import (
    DOMAIN,
    FILTER_MODE_EXCLUDE,
    FILTER_MODE_INCLUDE,
)


# ---------------------------------------------------------------------------
# Config flow
# ---------------------------------------------------------------------------

class TestConfigFlow:
    async def test_shows_user_form(self, hass: HomeAssistant):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "user"

    async def test_creates_entry_on_submit(self, hass: HomeAssistant):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={}
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["title"] == "Scene Cache"

    async def test_entry_data_is_empty_on_create(self, hass: HomeAssistant):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={}
        )
        assert result["data"] == {}

    async def test_aborts_when_already_configured(self, hass: HomeAssistant):
        existing = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN)
        existing.add_to_hass(hass)

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "already_configured"


# ---------------------------------------------------------------------------
# Options flow
# ---------------------------------------------------------------------------

class TestOptionsFlow:
    async def _create_and_setup(self, hass: HomeAssistant):
        entry = MockConfigEntry(
            domain=DOMAIN,
            options={"filter_mode": FILTER_MODE_EXCLUDE, "patterns": []},
            unique_id=DOMAIN,
        )
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        return entry

    async def test_shows_init_form(self, hass: HomeAssistant):
        entry = await self._create_and_setup(hass)
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "init"

    async def test_saves_exclude_mode_with_list_patterns(self, hass: HomeAssistant):
        entry = await self._create_and_setup(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                "filter_mode": FILTER_MODE_EXCLUDE,
                "patterns": ["scene.tmp_*", "scene.test_*"],
            },
        )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert entry.options["filter_mode"] == FILTER_MODE_EXCLUDE
        assert entry.options["patterns"] == ["scene.tmp_*", "scene.test_*"]

    async def test_saves_include_mode_with_string_patterns(self, hass: HomeAssistant):
        """Patterns provided as comma-separated string (fallback path) are split."""
        entry = await self._create_and_setup(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                "filter_mode": FILTER_MODE_INCLUDE,
                "patterns": "scene.party_*, scene.movie",
            },
        )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert "scene.party_*" in entry.options["patterns"]
        assert "scene.movie" in entry.options["patterns"]

    async def test_saves_exclude_mode_without_patterns(self, hass: HomeAssistant):
        entry = MockConfigEntry(
            domain=DOMAIN,
            options={"filter_mode": FILTER_MODE_EXCLUDE, "patterns": ["scene.tmp_*"]},
            unique_id=DOMAIN,
        )
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={"filter_mode": FILTER_MODE_EXCLUDE, "patterns": []},
        )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert entry.options["filter_mode"] == FILTER_MODE_EXCLUDE
        assert entry.options["patterns"] == []

    async def test_options_update_triggers_apply_filter(self, hass: HomeAssistant):
        """Changing options via the flow should call async_apply_filter on the coordinator."""
        entry = await self._create_and_setup(hass)
        coordinator = hass.data[DOMAIN][entry.entry_id]
        coordinator._cached = {
            "tmp_scene": {"light.x": {"state": "on"}},
            "party": {"light.y": {"state": "off"}},
        }

        result = await hass.config_entries.options.async_init(entry.entry_id)
        await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                "filter_mode": FILTER_MODE_EXCLUDE,
                "patterns": ["scene.tmp_*"],
            },
        )
        await hass.async_block_till_done()

        assert "tmp_scene" not in coordinator._cached
        assert "party" in coordinator._cached
