"""
OIL Incidents — Windowing Module (v0.2)

Incident batching from a raw event stream.

detect_triggers(events) -> list[Event]
  Identifies events that signal a real incident symptom:
  - business_kpi metric_kind with negative delta (drop)
  - error_rate metric_kind with positive delta (spike)
  - latency metric_kind with positive delta (spike)
  - event_type in {"error_rate","latency"} for v0 compat (when metric_kind is empty)

build_incident_batch(events, trigger, graph, window_before_min, window_after_min, hops)
  Selects events that are:
  1. Within the time window around the trigger event
  2. From services within N undirected BFS hops of the trigger service
  3. OR change events with related_deployment set (included regardless of service)
"""
from __future__ import annotations

from datetime import timedelta

from oil.graph.loader import bfs_distance
from oil.models.schemas import DependencyNode, Event

_TRIGGER_METRIC_KINDS = {"business_kpi", "error_rate", "latency"}
_TRIGGER_EVENT_TYPES = {"error_rate", "latency"}  # v0 compat
_TRIGGER_DELTA_THRESHOLDS = {
    # (metric_kind, direction): minimum |abs(delta)| to count as a trigger
    # 0.0 = any non-zero delta qualifies
    "business_kpi": 0.0,  # any drop
    "error_rate": 0.0,    # any spike
    "latency": 0.0,       # any spike
}


def _is_trigger(event: Event) -> bool:
    """Return True if this event qualifies as an incident trigger.

    Triggers:
    - business_kpi drop: metric_kind="business_kpi" AND delta < 0
    - error_rate spike: metric_kind="error_rate" AND delta > 0
    - latency spike:  metric_kind="latency" AND delta > 0
    - v0 compat fallback: event_type in {"error_rate","latency"} AND delta > 0
    """
    mk = event.metric_kind
    et = event.event_type
    d = event.delta

    if mk == "business_kpi" and d < 0:
        return True
    if mk in ("error_rate", "latency") and d > 0:
        return True
    # v0 compat
    if not mk and et in _TRIGGER_EVENT_TYPES and d > 0:
        return True
    return False


def detect_triggers(events: list[Event]) -> list[Event]:
    """Return the subset of events that qualify as incident triggers.

    Results are sorted by abs(delta) descending (largest signal first).
    """
    triggers = [e for e in events if _is_trigger(e)]
    return sorted(triggers, key=lambda e: abs(e.delta), reverse=True)


def _neighborhood_services(
    graph: dict[str, DependencyNode],
    origin_service: str,
    hops: int,
) -> set[str]:
    """Return all service names reachable from origin_service within *hops* on the undirected graph."""
    visited: set[str] = {origin_service}
    frontier: set[str] = {origin_service}

    for _ in range(hops):
        next_frontier: set[str] = set()
        for svc in frontier:
            node = graph.get(svc)
            if node is None:
                continue
            neighbors = set(node.upstream) | set(node.downstream)
            for neighbor in neighbors:
                if neighbor not in visited:
                    visited.add(neighbor)
                    next_frontier.add(neighbor)
        frontier = next_frontier
        if not frontier:
            break

    return visited


def _build_batch_for_hops(
    events: list[Event],
    trigger_event: Event,
    graph: dict[str, DependencyNode],
    window_start,
    window_end,
    hops: int,
) -> list[Event]:
    """Core batch builder for a given hop radius (internal helper)."""
    neighborhood = _neighborhood_services(graph, trigger_event.service, hops)
    batch: list[Event] = []
    for event in events:
        in_window = window_start <= event.timestamp <= window_end
        if not in_window:
            continue
        in_neighborhood = event.service in neighborhood
        is_change_event = (
            event.event_type == "change"
            and bool(event.related_deployment)
        )
        if in_neighborhood or is_change_event:
            batch.append(event)
    return batch


def build_incident_batch(
    events: list[Event],
    trigger_event: Event,
    graph: dict[str, DependencyNode],
    window_before_min: float = 10.0,
    window_after_min: float = 5.0,
    hops: int = 2,
) -> list[Event]:
    """Select events relevant to an incident defined by *trigger_event*.

    Inclusion criteria:
    1. Event timestamp is within [trigger_ts - window_before_min, trigger_ts + window_after_min]
    2. AND the event's service is within *hops* undirected BFS hops of trigger_event.service
    3. OR the event is a change event (event_type="change") with related_deployment set,
       within the time window (included regardless of service distance).

    Density guard (v0.3): if batch has fewer than 3 events with default hops, the hop
    radius is expanded by 1 (hops+1) and rebuilt once. Time window is not changed.

    Returns events sorted by timestamp ascending.
    """
    ref_ts = trigger_event.timestamp
    window_start = ref_ts - timedelta(minutes=window_before_min)
    window_end = ref_ts + timedelta(minutes=window_after_min)

    batch = _build_batch_for_hops(events, trigger_event, graph, window_start, window_end, hops)

    # v0.3 density guard: if sparse, expand hops by 1 once (deterministic)
    _DENSITY_MIN = 3
    _DENSITY_HOP_EXPANSION = 1
    if len(batch) < _DENSITY_MIN:
        expanded_batch = _build_batch_for_hops(
            events, trigger_event, graph, window_start, window_end, hops + _DENSITY_HOP_EXPANSION
        )
        if len(expanded_batch) > len(batch):
            batch = expanded_batch

    return sorted(batch, key=lambda e: e.timestamp)
