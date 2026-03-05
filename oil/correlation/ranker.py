"""
OIL Correlation -- Hypothesis Ranker (v0.3)

v0.3 additions over v0.2:

  [A] Eligibility filter (symptom vs. cause):
    Hypotheses where origin_service == reference_service are EXCLUDED
    UNLESS a change event exists for reference_service within 20m before reference_ts.
    Applied deterministically before sort.

  [B] Change-hypothesis granularity:
    If a change event (event_type="change") exists for a service within 20m before
    reference_ts, the hypothesis suspected_origin becomes:
      f"{service}:{change_kind}:{change_id}"
    Fields origin_service, origin_change_kind, origin_change_id are populated.
    BFS distance uses origin_service (not the compound key).
    hypothesis_id uses the compound suspected_origin for stability.

v0.2 scoring rules (preserved):
  temporal_score: decay window 5-30m, 1.0 / linear / 0.0
  distance_score: 0-hop=1.0, 1-hop=0.8, 2-hop=0.5, unknown=0.2, far=0.0
  magnitude_score: abs(delta) / max_abs_delta
  confidence = 0.45*temporal + 0.35*distance + 0.20*magnitude
  change_bias: +0.10 if change event within 20m (clamped to 1.0)
  confidence_cap: 0.7 if d=0 AND t>0.8 AND m>0.8, unless corroborated
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from oil.graph.loader import bfs_distance
from oil.models.schemas import DependencyNode, Event, IncidentHypothesis

_QUALIFYING_METRIC_KINDS = {"latency", "error_rate", "saturation", "business_kpi"}
_QUALIFYING_EVENT_TYPES = {"metric", "error_rate", "latency"}

_DISTANCE_SCORE_UNKNOWN = 0.2
_CONFIDENCE_CAP = 0.7
_CAP_TEMPORAL_THRESHOLD = 0.8
_CAP_MAGNITUDE_THRESHOLD = 0.8
_CHANGE_BIAS = 0.10
_CHANGE_BIAS_WINDOW_MIN = 20.0

_W_TEMPORAL = 0.45
_W_DISTANCE = 0.35
_W_MAGNITUDE = 0.20


def _temporal_score(event_ts: datetime, reference_ts: datetime) -> float:
    dt_min = abs((event_ts - reference_ts).total_seconds()) / 60.0
    if dt_min <= 5.0:
        return 1.0
    if dt_min >= 30.0:
        return 0.0
    return max(0.0, 1.0 - ((dt_min - 5.0) / 25.0))


def _distance_score_for_service(
    graph: dict[str, DependencyNode],
    reference_service: str,
    service: str,
) -> tuple[float, int]:
    """Return (distance_score, raw_hop_count). Uses origin_service for BFS."""
    if service not in graph:
        return _DISTANCE_SCORE_UNKNOWN, -1
    hops = bfs_distance(graph, reference_service, service)
    if hops == 0:
        return 1.0, 0
    if hops == 1:
        return 0.8, 1
    if hops == 2:
        return 0.5, 2
    return 0.0, hops


def _stable_hypothesis_id(
    suspected_origin: str,
    reference_ts: datetime,
    reference_service: str,
) -> str:
    payload = f"{suspected_origin}|{reference_ts.isoformat()}|{reference_service}"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _is_corroborated(
    events: list[Event],
    service: str,
    reference_ts: datetime,
    window_minutes: float = 10.0,
) -> bool:
    count = sum(
        1 for e in events
        if e.service == service
        and abs((e.timestamp - reference_ts).total_seconds()) / 60.0 <= window_minutes
    )
    return count >= 2


def _best_change_event(
    events: list[Event],
    service: str,
    reference_ts: datetime,
    window_minutes: float = _CHANGE_BIAS_WINDOW_MIN,
) -> Event | None:
    """Return the most recent change event for service within window_minutes before reference_ts.

    Returns None if no qualifying change event found.
    """
    candidates = [
        e for e in events
        if e.service == service
        and e.event_type == "change"
        and 0.0 <= (reference_ts - e.timestamp).total_seconds() / 60.0 <= window_minutes
    ]
    return max(candidates, key=lambda e: e.timestamp) if candidates else None


def _select_primary_impact_event(
    events: list[Event],
    reference_service: str,
) -> Event | None:
    """Rule 8: select the best representative event for primary technical impact."""
    if not events:
        return None
    candidates = [
        e for e in events
        if e.service == reference_service and e.metric_kind in _QUALIFYING_METRIC_KINDS
    ]
    if candidates:
        return max(candidates, key=lambda e: abs(e.delta))
    candidates = [
        e for e in events
        if e.service == reference_service and e.event_type in _QUALIFYING_EVENT_TYPES
    ]
    if candidates:
        return max(candidates, key=lambda e: abs(e.delta))
    return max(events, key=lambda e: abs(e.delta))


def select_reference(
    events: list[Event],
    reference_service: str,
) -> datetime:
    """Derive reference_ts from events automatically.

    Checks qualifying reference-service events first.
    Fallback: most recent event timestamp in the full batch.
    """
    ref_events = [e for e in events if e.service == reference_service]

    mk_candidates = [e for e in ref_events if e.metric_kind in _QUALIFYING_METRIC_KINDS]
    if mk_candidates:
        return max(mk_candidates, key=lambda e: abs(e.delta)).timestamp

    et_candidates = [e for e in ref_events if e.event_type in _QUALIFYING_EVENT_TYPES]
    if et_candidates:
        return max(et_candidates, key=lambda e: abs(e.delta)).timestamp

    return max(e.timestamp for e in events)


def rank_hypotheses(
    events: list[Event],
    graph: dict[str, DependencyNode],
    reference_ts: datetime,
    reference_service: str,
) -> list[IncidentHypothesis]:
    """Score and rank hypotheses for each unique service in events.

    v0.3 changes:
    - Change-origin granularity: suspected_origin becomes compound key when change event exists.
    - Eligibility filter: reference_service self-hypotheses excluded unless change_biased.
    - BFS distance uses origin_service (not compound suspected_origin).
    """
    if not events:
        return []

    max_abs_delta = max(abs(e.delta) for e in events)

    # Aggregate best metric event per service (max abs(delta))
    service_repr: dict[str, Event] = {}
    for event in events:
        svc = event.service
        if svc not in service_repr or abs(event.delta) > abs(service_repr[svc].delta):
            service_repr[svc] = event

    hypotheses: list[IncidentHypothesis] = []
    for svc, rep_event in service_repr.items():
        # Use origin_service for BFS (not compound key)
        d_score, hops = _distance_score_for_service(graph, reference_service, svc)

        # Temporal (from rep metric event)
        t_score = _temporal_score(rep_event.timestamp, reference_ts)

        # Magnitude
        if max_abs_delta == 0.0:
            m_score = 0.0
        else:
            m_score = abs(rep_event.delta) / max_abs_delta

        # Confidence (v0.2 weights)
        confidence = round(
            _W_TEMPORAL * t_score + _W_DISTANCE * d_score + _W_MAGNITUDE * m_score, 6
        )

        # Confidence cap guard
        if d_score == 0.0 and t_score > _CAP_TEMPORAL_THRESHOLD and m_score > _CAP_MAGNITUDE_THRESHOLD:
            if not _is_corroborated(events, svc, reference_ts):
                confidence = min(confidence, _CONFIDENCE_CAP)

        # Change-origin: find best change event within 20m (v0.2: bias; v0.3: granularity)
        change_ev = _best_change_event(events, svc, reference_ts)
        change_biased = change_ev is not None
        origin_change_kind = change_ev.change_kind if change_ev else ""
        origin_change_id = change_ev.change_id if change_ev else ""

        # Change bias: +0.10 confidence
        if change_biased:
            confidence = min(round(confidence + _CHANGE_BIAS, 6), 1.0)

        # Build compound suspected_origin for change hypotheses (v0.3)
        if change_biased:
            suspected_origin = f"{svc}:{origin_change_kind}:{origin_change_id}"
        else:
            suspected_origin = svc

        h_id = _stable_hypothesis_id(suspected_origin, reference_ts, reference_service)

        hypotheses.append(
            IncidentHypothesis(
                hypothesis_id=h_id,
                suspected_origin=suspected_origin,
                confidence_score=confidence,
                dependency_distance=hops,
                time_proximity=round(
                    abs((rep_event.timestamp - reference_ts).total_seconds()) / 60.0, 2
                ),
                impact_score=m_score,
                change_biased=change_biased,
                origin_service=svc,
                origin_change_kind=origin_change_kind,
                origin_change_id=origin_change_id,
            )
        )

    # v0.3 Eligibility filter: exclude self-reference unless change_biased
    # Deterministic: applied before sort
    hypotheses = [
        h for h in hypotheses
        if not (h.origin_service == reference_service and not h.change_biased)
    ]

    return sorted(hypotheses, key=lambda h: h.confidence_score, reverse=True)
