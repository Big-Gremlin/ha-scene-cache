"""SceneCacheCoordinator and service registration."""
from __future__ import annotations

import logging
from fnmatch import fnmatchcase
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EVENT_CALL_SERVICE,
    EVENT_HOMEASSISTANT_STARTED,
    EVENT_HOMEASSISTANT_STOP,
)
from homeassistant.core import CoreState, Event, HomeAssistant, ServiceCall, SupportsResponse, callback
from homeassistant.helpers.storage import Store

from .const import (
    ATTR_SCENE_ID,
    CONF_FILTER_MODE,
    CONF_PATTERNS,
    DOMAIN,
    FILTER_MODE_EXCLUDE,
    FILTER_MODE_INCLUDE,
    SAVE_DELAY_SECONDS,
    SCENE_DOMAIN,
    SERVICE_CLEAR,
    SERVICE_FORGET,
    SERVICE_LIST,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .payload import _normalize_entity_state, _state_to_payload

_LOGGER = logging.getLogger(__name__)

_SERVICE_CREATE = "create"
_SERVICE_DELETE = "delete"


class SceneCacheCoordinator:
    """Tracks dynamic scenes and persists them across restarts."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._all_captured: dict[str, dict[str, Any]] = {}
        self._cached: dict[str, dict[str, Any]] = {}
        self._unsub_listeners: list = []

    @property
    def cached_scenes(self) -> dict[str, dict]:
        return dict(self._cached)

    @property
    def filter_mode(self) -> str:
        return self.entry.options.get(CONF_FILTER_MODE, FILTER_MODE_EXCLUDE)

    @property
    def patterns(self) -> list[str]:
        return list(self.entry.options.get(CONF_PATTERNS, []))

    def matches_filter(self, entity_id: str) -> bool:
        """Return True if the given scene entity_id passes the configured filter."""
        mode = self.filter_mode
        patterns = self.patterns
        if not patterns:
            return mode == FILTER_MODE_EXCLUDE
        matched = any(fnmatchcase(entity_id, pattern) for pattern in patterns)
        if mode == FILTER_MODE_INCLUDE:
            return matched
        if mode == FILTER_MODE_EXCLUDE:
            return not matched
        return True

    async def async_initialize(self) -> None:
        """Load persisted state, register listeners, schedule restore."""
        data = await self._store.async_load() or {}
        self._all_captured = dict(data.get("scenes") or {})
        self._cached = {
            s: p for s, p in self._all_captured.items()
            if self.matches_filter(f"{SCENE_DOMAIN}.{s}")
        }

        if self.hass.state == CoreState.running:
            await self._async_restore()
        else:
            self._unsub_listeners.append(
                self.hass.bus.async_listen_once(
                    EVENT_HOMEASSISTANT_STARTED, self._async_handle_started
                )
            )

        self._unsub_listeners.append(
            self.hass.bus.async_listen(EVENT_CALL_SERVICE, self._async_handle_service_call)
        )
        self._unsub_listeners.append(
            self.hass.bus.async_listen(EVENT_HOMEASSISTANT_STOP, self._async_handle_stop)
        )

    async def async_shutdown(self) -> None:
        """Unsubscribe listeners and flush state."""
        for unsub in self._unsub_listeners:
            unsub()
        self._unsub_listeners.clear()
        await self._store.async_save({"scenes": self._all_captured})

    async def async_apply_filter(self) -> None:
        """Recompute the active cache from all captured scenes and restore newly matching scenes."""
        self._cached = {
            s: p for s, p in self._all_captured.items()
            if self.matches_filter(f"{SCENE_DOMAIN}.{s}")
        }
        await self._async_restore()

    @callback
    def _schedule_save(self) -> None:
        self._store.async_delay_save(lambda: {"scenes": self._all_captured}, SAVE_DELAY_SECONDS)

    async def _async_handle_started(self, _event: Event) -> None:
        await self._async_restore()

    async def _async_restore(self) -> None:
        """Recreate cached scenes that pass the filter and don't already exist."""
        for scene_id, entities in list(self._cached.items()):
            entity_id = f"{SCENE_DOMAIN}.{scene_id}"
            if not self.matches_filter(entity_id):
                continue
            if self.hass.states.get(entity_id) is not None:
                continue
            if not entities:
                continue
            try:
                await self.hass.services.async_call(
                    SCENE_DOMAIN,
                    _SERVICE_CREATE,
                    {ATTR_SCENE_ID: scene_id, "entities": entities},
                    blocking=True,
                )
                _LOGGER.debug("Restored cached scene %s", entity_id)
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Failed to restore cached scene %s", entity_id)

    @callback
    def _async_handle_service_call(self, event: Event) -> None:
        """Capture scene.create and scene.delete calls to keep the cache in sync."""
        data = event.data
        if data.get("domain") != SCENE_DOMAIN:
            return

        service = data.get("service")
        service_data: dict[str, Any] = data.get("service_data") or {}

        if service == _SERVICE_CREATE:
            scene_id = service_data.get(ATTR_SCENE_ID)
            if not scene_id:
                return
            payload = self._build_payload(service_data)
            if not payload:
                return
            self._all_captured[scene_id] = payload
            self._schedule_save()
            if self.matches_filter(f"{SCENE_DOMAIN}.{scene_id}"):
                self._cached[scene_id] = payload

        elif service == _SERVICE_DELETE:
            raw = service_data.get("entity_id")
            if not raw:
                return
            entity_ids = raw if isinstance(raw, list) else [raw]
            changed = False
            for eid in entity_ids:
                key = eid.removeprefix(f"{SCENE_DOMAIN}.")
                if key in self._all_captured:
                    self._all_captured.pop(key)
                    self._cached.pop(key, None)
                    changed = True
            if changed:
                self._schedule_save()

    def _build_payload(self, service_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """Build a replay payload from a scene.create service_data."""
        payload: dict[str, dict[str, Any]] = {}

        entities = service_data.get("entities") or {}
        if isinstance(entities, dict):
            for ent_id, value in entities.items():
                payload[ent_id] = _normalize_entity_state(value)

        for ent_id in service_data.get("snapshot_entities") or []:
            state = self.hass.states.get(ent_id)
            if state is None:
                continue
            payload[ent_id] = _state_to_payload(state.state, state.attributes)

        return payload

    async def _async_handle_stop(self, _event: Event) -> None:
        """Flush state on shutdown."""
        await self._store.async_save({"scenes": self._cached})

    async def async_forget(self, scene_id: str) -> None:
        """Remove a scene from the cache."""
        key = scene_id.split(".", 1)[1] if scene_id.startswith(f"{SCENE_DOMAIN}.") else scene_id
        if key in self._all_captured:
            self._all_captured.pop(key)
            self._cached.pop(key, None)
            self._schedule_save()

    async def async_clear(self) -> None:
        """Drop the entire cache."""
        if not self._all_captured:
            return
        self._all_captured.clear()
        self._cached.clear()
        await self._store.async_save({"scenes": self._all_captured})


@callback
def _async_register_services(hass: HomeAssistant) -> None:
    """Register integration-level services (idempotent)."""
    if hass.services.has_service(DOMAIN, SERVICE_FORGET):
        return

    async def _handle_forget(call: ServiceCall) -> None:
        scene_id = call.data.get(ATTR_SCENE_ID)
        if not scene_id:
            return
        for coordinator in list(hass.data.get(DOMAIN, {}).values()):
            await coordinator.async_forget(scene_id)

    async def _handle_clear(_call: ServiceCall) -> None:
        for coordinator in list(hass.data.get(DOMAIN, {}).values()):
            await coordinator.async_clear()

    async def _handle_list(_call: ServiceCall) -> dict:
        scenes: dict = {}
        for coordinator in hass.data.get(DOMAIN, {}).values():
            scenes.update(coordinator.cached_scenes)
        return {"scenes": scenes, "count": len(scenes)}

    hass.services.async_register(DOMAIN, SERVICE_FORGET, _handle_forget)
    hass.services.async_register(DOMAIN, SERVICE_CLEAR, _handle_clear)
    hass.services.async_register(
        DOMAIN, SERVICE_LIST, _handle_list, supports_response=SupportsResponse.ONLY
    )
