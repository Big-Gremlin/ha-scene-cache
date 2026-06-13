"""Config flow for Scene Cache."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_FILTER_MODE,
    CONF_PATTERNS,
    DEFAULT_FILTER_MODE,
    DOMAIN,
    FILTER_MODES,
)


class SceneCacheConfigFlow(ConfigFlow, domain=DOMAIN):
    """Initial configuration flow - single instance."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(title="Scene Cache", data={})
        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return SceneCacheOptionsFlow()


class SceneCacheOptionsFlow(OptionsFlow):
    """Options flow for changing filter mode and patterns."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            mode = user_input[CONF_FILTER_MODE]
            patterns = _coerce_patterns(user_input.get(CONF_PATTERNS))
            return self.async_create_entry(
                title="",
                data={CONF_FILTER_MODE: mode, CONF_PATTERNS: patterns},
            )

        current_mode = self.config_entry.options.get(CONF_FILTER_MODE, DEFAULT_FILTER_MODE)
        current_patterns = list(self.config_entry.options.get(CONF_PATTERNS, []))
        return self.async_show_form(
            step_id="init",
            data_schema=_build_schema(current_mode, current_patterns),
        )


def _build_schema(mode: str, patterns: list[str]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_FILTER_MODE, default=mode): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=FILTER_MODES,
                    translation_key="filter_mode",
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(CONF_PATTERNS, description={"suggested_value": patterns}): selector.TextSelector(
                selector.TextSelectorConfig(multiple=True)
            ),
        }
    )


def _coerce_patterns(raw: Any) -> list[str]:
    """Accept list or comma-separated string and return a clean list."""
    if raw is None:
        return []
    if isinstance(raw, str):
        items = [part.strip() for part in raw.split(",")]
    elif isinstance(raw, (list, tuple)):
        items = [str(item).strip() for item in raw]
    else:
        items = [str(raw).strip()]
    return [item for item in items if item]
