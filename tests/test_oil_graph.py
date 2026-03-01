"""Tests: oil/graph/loader.py — load_graph + bfs_distance"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from oil.graph.loader import bfs_distance, load_graph

_SAMPLE_GRAPH = Path(__file__).resolve().parents[1] / "oil" / "graph" / "sample_graph.json"


class TestLoadGraph:
    def test_load_sample_graph_node_count(self):
        graph = load_graph(_SAMPLE_GRAPH)
        assert len(graph) == 4
        assert "checkout" in graph
        assert "payment" in graph
        assert "auth" in graph
        assert "inventory" in graph

    def test_checkout_downstream(self):
        graph = load_graph(_SAMPLE_GRAPH)
        assert "payment" in graph["checkout"].downstream
        assert "inventory" in graph["checkout"].downstream

    def test_auth_upstream(self):
        graph = load_graph(_SAMPLE_GRAPH)
        assert "payment" in graph["auth"].upstream

    def test_business_function_loaded(self):
        graph = load_graph(_SAMPLE_GRAPH)
        assert graph["checkout"].business_function == "revenue"

    def test_missing_upstream_key_defaults_to_empty(self, tmp_path):
        data = {"svc_a": {"downstream": ["svc_b"], "business_function": "ops"}}
        p = tmp_path / "graph.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        graph = load_graph(p)
        assert graph["svc_a"].upstream == []

    def test_missing_downstream_key_defaults_to_empty(self, tmp_path):
        data = {"svc_a": {"upstream": ["svc_b"]}}
        p = tmp_path / "graph.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        graph = load_graph(p)
        assert graph["svc_a"].downstream == []


class TestBfsDistance:
    def test_same_node_is_zero(self):
        graph = load_graph(_SAMPLE_GRAPH)
        assert bfs_distance(graph, "checkout", "checkout") == 0

    def test_direct_neighbour_is_one_hop(self):
        graph = load_graph(_SAMPLE_GRAPH)
        assert bfs_distance(graph, "checkout", "payment") == 1

    def test_two_hops(self):
        # checkout → payment → auth
        graph = load_graph(_SAMPLE_GRAPH)
        assert bfs_distance(graph, "checkout", "auth") == 2

    def test_undirected_reverse_two_hops(self):
        # auth → payment → checkout (undirected, should still be 2)
        graph = load_graph(_SAMPLE_GRAPH)
        assert bfs_distance(graph, "auth", "checkout") == 2

    def test_unreachable_returns_999(self, tmp_path):
        data = {
            "svc_a": {"upstream": [], "downstream": []},
            "svc_b": {"upstream": [], "downstream": []},
        }
        p = tmp_path / "graph.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        graph = load_graph(p)
        assert bfs_distance(graph, "svc_a", "svc_b") == 999

    def test_start_not_in_graph_returns_999(self):
        graph = load_graph(_SAMPLE_GRAPH)
        assert bfs_distance(graph, "nonexistent", "checkout") == 999
