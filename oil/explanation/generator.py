"""
OIL Explanation -- Incident Report Generator (v0.4)

v0.4 additions:
  - generate_explanation returns extra metadata fields for DIM fingerprinting:
      reference_service, impact_direction, primary_metric_kind,
      impact_domain, hop_distance_class
  - similar_incidents section: populated externally by run_analysis after
    memory lookup; format_human_block renders it if present.

v0.3 history:
  origin_service drives domain lookup (not compound suspected_origin key).
  Change-origin rendered as "payment deploy sha-xxx".
"""
from __future__ import annotations

from oil.correlation.ranker import _select_primary_impact_event
from oil.impact.mapper import map_impact
from oil.models.schemas import Event, IncidentHypothesis

_IMPACT_EVENT_TYPES = {"metric", "error_rate", "latency"}


def _top_evidence(
    events: list[Event],
    n: int = 3,
) -> list[dict]:
    """Return the top-N events sorted by abs(delta) with a short reason string."""
    sorted_events = sorted(events, key=lambda e: abs(e.delta), reverse=True)
    evidence = []
    for i, e in enumerate(sorted_events[:n]):
        if i == 0:
            reason = "highest delta magnitude in batch"
        elif e.metric_kind:
            reason = f"metric_kind={e.metric_kind!r} with significant delta"
        elif e.event_type in _IMPACT_EVENT_TYPES:
            reason = f"qualifying event type ({e.event_type!r}) with significant delta"
        else:
            reason = "notable delta relative to batch"
        evidence.append({
            "event_id": e.event_id,
            "service": e.service,
            "metric_name": e.metric_name,
            "metric_kind": e.metric_kind,
            "delta": e.delta,
            "event_type": e.event_type,
            "reason": reason,
        })
    return evidence


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


def generate_explanation(
    hypotheses: list[IncidentHypothesis],
    events: list[Event],
    impact_map: dict[str, str],
    reference_service: str,
) -> dict:
    """Generate a structured incident report.

    Returns a dict with 6 required report keys, evidence, and v0.4 metadata fields:
      reference_service, impact_direction, primary_metric_kind,
      impact_domain, hop_distance_class.
    similar_incidents is initially absent; run_analysis populates it post memory lookup.
    """
    top = hypotheses[0] if hypotheses else None
    primary_event = _select_primary_impact_event(events, reference_service)

    # Incident summary
    if top:
        incident_summary = (
            f"Incident detected in {reference_service!r}. "
            f"Top suspected origin: {top.suspected_origin!r} "
            f"(confidence {top.confidence_score:.2f})."
        )
    else:
        incident_summary = f"Incident detected in {reference_service!r}. No ranked hypotheses available."

    # Primary technical impact (Rule 8)
    if primary_event:
        primary_technical_impact = (
            f"{primary_event.service} / {primary_event.metric_name}: "
            f"delta {primary_event.delta:+.2f} "
            f"[{primary_event.event_type or 'unknown type'}]"
        )
    else:
        primary_technical_impact = "No qualifying events found."

    # Business effect -- explicitly labelled domains
    impact_domain = ""
    if top:
        impact_domain = map_impact(reference_service, impact_map)
        origin_svc = top.origin_service or top.suspected_origin
        origin_domain = map_impact(origin_svc, impact_map)
        business_effect_estimate = (
            f"Impact domain: {impact_domain!r} (affected: {reference_service!r}). "
            f"Suspected origin domain: {origin_domain!r} (origin: {origin_svc!r})."
        )
    else:
        business_effect_estimate = "Insufficient data to estimate business effect."

    # Top ranked cause -- v0.3: render change-origin as "service kind id"
    cause_label = ""
    if top:
        if top.origin_change_kind:
            cause_label = top.origin_service
            cause_label += f" {top.origin_change_kind}"
            if top.origin_change_id:
                cause_label += f" {top.origin_change_id}"
        else:
            cause_label = top.suspected_origin
        top_ranked_cause = (
            f"{cause_label!r} -- "
            f"{top.dependency_distance} hop(s) from {reference_service!r}, "
            f"{top.time_proximity:.1f} min before reference timestamp."
        )
    else:
        top_ranked_cause = "No hypothesis ranked."

    # Recommended action
    if top and top.confidence_score >= 0.6:
        recommended_human_action = (
            f"Investigate recent changes to {cause_label!r}. "
            f"Check deployment logs and rollback options if applicable."
        )
    elif top:
        recommended_human_action = (
            f"Low-confidence signal. Collect additional telemetry from "
            f"{cause_label!r} before taking action."
        )
    else:
        recommended_human_action = "Expand telemetry coverage before escalating."

    # v0.4 DIM metadata fields (used by fingerprint + memory store)
    impact_direction = ""
    primary_metric_kind = ""
    if primary_event:
        impact_direction = "decrease" if primary_event.delta < 0 else "increase"
        primary_metric_kind = primary_event.metric_kind or ""

    return {
        # Core report keys (unchanged across versions)
        "incident_summary": incident_summary,
        "primary_technical_impact": primary_technical_impact,
        "business_effect_estimate": business_effect_estimate,
        "top_ranked_cause": top_ranked_cause,
        "confidence_score": top.confidence_score if top else 0.0,
        "recommended_human_action": recommended_human_action,
        "evidence": _top_evidence(events),
        # v0.4 DIM metadata (not rendered by format_human_block directly)
        "reference_service": reference_service,
        "impact_direction": impact_direction,
        "primary_metric_kind": primary_metric_kind,
        "impact_domain": impact_domain,
        "hop_distance_class": _hop_distance_class(top.dependency_distance) if top else "unknown",
        # similar_incidents: populated by run_analysis after memory lookup
        # "similar_incidents": {}  -- added externally
    }


def format_human_block(report: dict) -> str:
    """Render the incident report as a plain-text block for stdout."""
    lines = [
        "=" * 60,
        "OIL -- INCIDENT EXPLANATION",
        "=" * 60,
        f"SUMMARY:          {report.get('incident_summary', '')}",
        f"TECHNICAL IMPACT: {report.get('primary_technical_impact', '')}",
        "BUSINESS EFFECT:",
        f"  {report.get('business_effect_estimate', '')}",
        f"TOP CAUSE:        {report.get('top_ranked_cause', '')}",
        f"CONFIDENCE:       {report.get('confidence_score', 0.0):.2f}",
        f"ACTION:           {report.get('recommended_human_action', '')}",
    ]
    evidence = report.get("evidence", [])
    if evidence:
        lines.append("EVIDENCE:")
        for ev in evidence:
            lines.append(
                f"  [{ev['event_id']}] {ev['service']}/{ev['metric_name']} "
                f"delta={ev['delta']:+.2f} -- {ev['reason']}"
            )

    # v0.4+: SIMILAR INCIDENTS section
    similar = report.get("similar_incidents", {})
    if similar and similar.get("occurrence_count", 0) > 0:
        lines.append("SIMILAR INCIDENTS:")
        lines.append(f"  occurrence_count:            {similar['occurrence_count']}")
        lines.append(f"  most_common_origin:          {similar.get('most_common_origin', '')}")
        # v0.5: action category summary
        mac = similar.get("most_common_action_category", "")
        if mac:
            lines.append(f"  most_common_action_category: {mac}")
        recent = similar.get("recent_examples", [])
        if recent:
            lines.append("  recent_examples:")
            for ex in recent[:3]:
                action_cat = ex.get("action_category", "")
                action_part = f" action={action_cat}" if action_cat else ""
                lines.append(
                    f"    [{ex.get('created_utc', '?')}] "
                    f"origin={ex.get('origin_service', '?')} "
                    f"confidence={ex.get('confidence', 0):.2f} "
                    f"score={ex.get('similarity_score', 0)}"
                    f"{action_part}"
                )
        # v0.6: outcome summary
        os_data = similar.get("outcome_summary")
        if os_data and os_data.get("total_with_outcomes", 0) > 0:
            lines.append("  outcome_summary:")
            lines.append(f"    total_with_outcomes: {os_data['total_with_outcomes']}")
            lines.append(f"    resolved_rate:       {os_data['resolved_rate']:.2%}")
            cnts = os_data.get("counts", {})
            parts = "  ".join(f"{k}={v}" for k, v in cnts.items() if v > 0)
            if parts:
                lines.append(f"    counts: {parts}")

    lines.append("=" * 60)
    return "\n".join(lines)
