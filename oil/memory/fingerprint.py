"""
OIL Memory -- Deterministic Incident Fingerprint (v0.4)

generate_fingerprint(report, hypotheses) -> str

Fingerprint components (7):
  1. reference_service     -- affected service ("checkout")
  2. origin_service        -- root-cause service ("payment")
  3. origin_change_kind    -- "deploy" | "config" | "" etc.
  4. primary_metric_kind   -- "latency" | "error_rate" | "business_kpi" | ""
  5. hop_distance_class    -- "0" | "1" | "2" | "far" | "unknown"
  6. temporal_class        -- "0-5m" | "5-15m" | "15-30m" | "30m+"
  7. impact_direction      -- "increase" | "decrease"

Canonical string: "|".join(components_in_order)
Returns 16-char sha256 hex prefix.

Stability guarantee: same component values always yield the same fingerprint.
All components are lowercased before hashing.
"""
from __future__ import annotations

import hashlib

from oil.models.schemas import IncidentHypothesis


def _hop_distance_class(hops: int) -> str:
    if hops == -1:
        return "unknown"
    if hops == 0:
        return "0"
    if hops == 1:
        return "1"
    if hops == 2:
        return "2"
    return "far"


def _temporal_class(time_proximity_min: float) -> str:
    if time_proximity_min <= 5.0:
        return "0-5m"
    if time_proximity_min <= 15.0:
        return "5-15m"
    if time_proximity_min <= 30.0:
        return "15-30m"
    return "30m+"


def generate_fingerprint(report: dict, hypotheses: list[IncidentHypothesis]) -> str:
    """Generate a deterministic sha256 fingerprint for an incident.

    Args:
        report: output of generate_explanation() -- must include fields:
                reference_service, impact_direction, primary_metric_kind.
        hypotheses: ranked list from rank_hypotheses(); uses hypotheses[0].

    Returns:
        16-char hex prefix of sha256 (deterministic, stable).
        Returns sha256 of empty string if both report and hypotheses are empty.
    """
    top = hypotheses[0] if hypotheses else None

    reference_service   = str(report.get("reference_service", "")).lower()
    origin_service      = top.origin_service.lower() if top else ""
    origin_change_kind  = top.origin_change_kind.lower() if top else ""
    primary_metric_kind = str(report.get("primary_metric_kind", "")).lower()
    hop_class           = _hop_distance_class(top.dependency_distance) if top else "unknown"
    temporal_cls        = _temporal_class(top.time_proximity) if top else "30m+"
    impact_direction    = str(report.get("impact_direction", "")).lower()

    canonical = "|".join([
        reference_service,
        origin_service,
        origin_change_kind,
        primary_metric_kind,
        hop_class,
        temporal_cls,
        impact_direction,
    ])

    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
