"""
OIL Graph — Dependency Graph Loader + BFS Distance

load_graph: reads JSON → dict[str, DependencyNode]
bfs_distance: undirected BFS hop count between two services
"""
from __future__ import annotations

import json
from collections import deque
from pathlib import Path

from oil.models.schemas import DependencyNode


def load_graph(path: Path) -> dict[str, DependencyNode]:
    """Load a dependency graph from a JSON file.

    JSON format:
    {
      "service_name": {
        "upstream": [...],      # optional, defaults to []
        "downstream": [...],    # optional, defaults to []
        "business_function": "" # optional, defaults to ""
      }
    }

    Missing keys are filled with safe defaults — no exception raised.
    """
    raw: dict = json.loads(path.read_text(encoding="utf-8"))
    graph: dict[str, DependencyNode] = {}
    for name, spec in raw.items():
        if not isinstance(spec, dict):
            spec = {}
        graph[name] = DependencyNode(
            service_name=name,
            upstream=list(spec.get("upstream") or []),
            downstream=list(spec.get("downstream") or []),
            business_function=str(spec.get("business_function") or ""),
        )
    return graph


def _build_undirected_adjacency(
    graph: dict[str, DependencyNode],
) -> dict[str, set[str]]:
    """Build an undirected adjacency map from the directed graph.

    Merges upstream and downstream edges symmetrically so BFS treats
    the graph as undirected. This gives proximity-based distance regardless
    of flow direction.
    """
    adj: dict[str, set[str]] = {name: set() for name in graph}
    for name, node in graph.items():
        for neighbour in node.upstream + node.downstream:
            adj[name].add(neighbour)
            if neighbour not in adj:
                adj[neighbour] = set()
            adj[neighbour].add(name)
    return adj


def bfs_distance(
    graph: dict[str, DependencyNode],
    start: str,
    target: str,
) -> int:
    """Return the undirected BFS hop count from *start* to *target*.

    Returns 0 if start == target.
    Returns 999 if target is unreachable (not in graph or disconnected).
    """
    if start == target:
        return 0
    adj = _build_undirected_adjacency(graph)
    if start not in adj:
        return 999

    visited: set[str] = {start}
    queue: deque[tuple[str, int]] = deque([(start, 0)])
    while queue:
        node, dist = queue.popleft()
        for neighbour in adj.get(node, set()):
            if neighbour == target:
                return dist + 1
            if neighbour not in visited:
                visited.add(neighbour)
                queue.append((neighbour, dist + 1))
    return 999
