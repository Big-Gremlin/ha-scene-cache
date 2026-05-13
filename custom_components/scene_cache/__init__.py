"""Scene Cache - persist dynamic Home Assistant scenes across restarts."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN, SERVICE_CLEAR, SERVICE_FORGET, SERVICE_LIST, STORAGE_KEY, STORAGE_VERSION
from .coordinator import SceneCacheCoordinator, _async_register_services


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the integration (YAML not supported)."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Scene Cache from a config entry."""
    coordinator = SceneCacheCoordinator(hass, entry)
    await coordinator.async_initialize()
    hass.data[DOMAIN][entry.entry_id] = coordinator

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    _async_register_services(hass)
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete persisted cache when the integration is removed."""
    store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    await store.async_remove()


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Scene Cache config entry."""
    coordinator: SceneCacheCoordinator | None = hass.data[DOMAIN].pop(entry.entry_id, None)
    if coordinator is not None:
        await coordinator.async_shutdown()

    if not hass.data[DOMAIN]:
        for service in (SERVICE_FORGET, SERVICE_CLEAR, SERVICE_LIST):
            if hass.services.has_service(DOMAIN, service):
                hass.services.async_remove(DOMAIN, service)
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    coordinator: SceneCacheCoordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_apply_filter()
