"""Tests: oil/impact/mapper.py"""
from __future__ import annotations

from oil.impact.mapper import load_impact_map, map_impact


class TestMapImpact:
    def test_known_service_checkout(self):
        impact_map = load_impact_map()
        assert map_impact("checkout", impact_map) == "revenue"

    def test_known_service_auth(self):
        impact_map = load_impact_map()
        assert map_impact("auth", impact_map) == "access"

    def test_known_service_payment(self):
        impact_map = load_impact_map()
        assert map_impact("payment", impact_map) == "transactions"

    def test_known_service_inventory(self):
        impact_map = load_impact_map()
        assert map_impact("inventory", impact_map) == "fulfillment"

    def test_unknown_service_returns_unknown(self):
        impact_map = load_impact_map()
        assert map_impact("nonexistent_service", impact_map) == "unknown"

    def test_empty_map_returns_unknown(self):
        assert map_impact("checkout", {}) == "unknown"

    def test_load_impact_map_returns_dict(self):
        impact_map = load_impact_map()
        assert isinstance(impact_map, dict)
        assert len(impact_map) > 0
