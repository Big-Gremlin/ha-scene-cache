"""Unit tests for the include/exclude filter logic.

These tests are pure Python and do not require a running Home Assistant instance.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.scene_cache.coordinator import SceneCacheCoordinator
from custom_components.scene_cache.const import (
    FILTER_MODE_EXCLUDE,
    FILTER_MODE_INCLUDE,
)


def _coordinator(filter_mode: str, patterns: list[str]) -> SceneCacheCoordinator:
    hass = MagicMock()
    entry = MagicMock()
    entry.options = {"filter_mode": filter_mode, "patterns": patterns}
    return SceneCacheCoordinator(hass, entry)


class TestFilterModeInclude:
    def test_matching_pattern_is_cached(self):
        c = _coordinator(FILTER_MODE_INCLUDE, ["scene.party_*"])
        assert c.matches_filter("scene.party_lights") is True

    def test_non_matching_pattern_is_not_cached(self):
        c = _coordinator(FILTER_MODE_INCLUDE, ["scene.party_*"])
        assert c.matches_filter("scene.bedtime") is False

    def test_any_of_multiple_patterns_suffices(self):
        c = _coordinator(FILTER_MODE_INCLUDE, ["scene.party_*", "scene.movie"])
        assert c.matches_filter("scene.movie") is True
        assert c.matches_filter("scene.party_hard") is True
        assert c.matches_filter("scene.other") is False

    def test_exact_entity_id_pattern(self):
        c = _coordinator(FILTER_MODE_INCLUDE, ["scene.exact"])
        assert c.matches_filter("scene.exact") is True
        assert c.matches_filter("scene.exactx") is False

    def test_empty_patterns_caches_nothing(self):
        c = _coordinator(FILTER_MODE_INCLUDE, [])
        assert c.matches_filter("scene.any") is False

    def test_single_char_wildcard(self):
        c = _coordinator(FILTER_MODE_INCLUDE, ["scene.tmp_?"])
        assert c.matches_filter("scene.tmp_a") is True
        assert c.matches_filter("scene.tmp_ab") is False


class TestFilterModeExclude:
    def test_matching_pattern_is_not_cached(self):
        c = _coordinator(FILTER_MODE_EXCLUDE, ["scene.tmp_*"])
        assert c.matches_filter("scene.tmp_test") is False

    def test_non_matching_scene_is_cached(self):
        c = _coordinator(FILTER_MODE_EXCLUDE, ["scene.tmp_*"])
        assert c.matches_filter("scene.party") is True

    def test_empty_patterns_caches_everything(self):
        c = _coordinator(FILTER_MODE_EXCLUDE, [])
        assert c.matches_filter("scene.any") is True

    def test_multiple_exclude_patterns(self):
        c = _coordinator(FILTER_MODE_EXCLUDE, ["scene.tmp_*", "scene.test_*"])
        assert c.matches_filter("scene.tmp_foo") is False
        assert c.matches_filter("scene.test_bar") is False
        assert c.matches_filter("scene.party") is True
