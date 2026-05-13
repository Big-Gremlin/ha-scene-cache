"""Helpers for building and normalising scene replay payloads."""
from __future__ import annotations

import json
from typing import Any

from .const import NON_REPLAYABLE_ATTRIBUTES


def _normalize_entity_state(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return _state_to_payload(value.get("state"), value)
    return {"state": value}


def _state_to_payload(state: Any, attributes: dict[str, Any] | None) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if state is not None:
        result["state"] = state
    for attr_key, attr_val in (attributes or {}).items():
        if attr_key == "state":
            continue
        if attr_key in NON_REPLAYABLE_ATTRIBUTES:
            continue
        if not _is_json_safe(attr_val):
            continue
        result[attr_key] = attr_val
    return result


def _is_json_safe(value: Any) -> bool:
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return False
    return True
