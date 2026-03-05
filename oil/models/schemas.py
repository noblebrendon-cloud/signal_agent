"""
OIL v0.3 -- Core Data Models

Change events (event_type="change") carry:
  change_kind: deploy | config | flag | scale | outage
  change_id:   commit_sha | deployment_id | flag_key | etc.

IncidentHypothesis v0.3 additions:
  origin_service:     actual service name (used for BFS distance)
  origin_change_kind: change_kind when hypothesis is from a change event
  origin_change_id:   change_id when hypothesis is from a change event

When a change event is the basis for a hypothesis:
  suspected_origin = f"{service}:{change_kind}:{change_id}"
  origin_service   = service
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Event:
    """Unified telemetry event.

    Required fields: event_id, timestamp, service.
    All other fields default to safe empty values.
    delta is guaranteed to be a float (normalizer converts None to 0.0).
    Change events: event_type="change", change_kind, change_id.
    """

    event_id: str
    timestamp: datetime  # UTC, timezone-aware
    service: str
    metric_name: str = ""
    metric_value: float = 0.0
    delta: float = 0.0
    event_type: str = ""
    source: str = ""
    related_deployment: str = ""
    business_tag: str = ""
    metric_kind: str = ""  # inferred: latency | error_rate | saturation | business_kpi | ""
    change_kind: str = ""  # deploy | config | flag | scale | outage
    change_id: str = ""    # commit_sha | deployment_id | flag_key | etc.


@dataclass(frozen=True)
class DependencyNode:
    """A node in the service dependency graph."""

    service_name: str
    upstream: list[str] = field(default_factory=list)
    downstream: list[str] = field(default_factory=list)
    business_function: str = ""


@dataclass(frozen=True)
class IncidentHypothesis:
    """A scored root-cause candidate produced by the correlation engine.

    hypothesis_id is a stable hash of (suspected_origin, reference_ts_iso, reference_service).
    dependency_distance is the raw BFS hop count (not normalized). -1 = not in graph.
    time_proximity is abs(event_ts - reference_ts) in minutes.
    change_biased: True if +0.10 change_bias was applied.
    origin_service: actual service name (used for BFS and display).
    origin_change_kind/id: populated when hypothesis comes from a change event.
    """

    hypothesis_id: str
    suspected_origin: str    # service name OR "service:change_kind:change_id"
    confidence_score: float
    dependency_distance: int
    time_proximity: float
    impact_score: float
    change_biased: bool = False
    origin_service: str = ""       # actual service (for BFS, display, impact map)
    origin_change_kind: str = ""   # deploy | config | flag | scale | outage | ""
    origin_change_id: str = ""     # change_id or ""
