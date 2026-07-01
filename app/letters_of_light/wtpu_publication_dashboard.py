"""
Read-only WTPU publication dashboard payloads and HTML rendering.

This module reads the WTPU append-only ledger and rebuilds projections for local
operator inspection. It does not append events, edit source records, create
summaries, publish, schedule, export, or call platform adapters.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from html import escape
from http import HTTPStatus
from typing import Any, Dict, Iterable, List, Mapping, Tuple
from urllib.parse import parse_qs

from app.letters_of_light.release import _get_root
from signal_agent.wtpu_publication.ledgers import WTPUPublicationLedger
from signal_agent.wtpu_publication.projection import (
    WTPUProjectionReplayError,
    WTPUProjectionTransitionError,
    WTPUPublicationProjection,
    replay_wtpu_publication_events,
)
from signal_agent.wtpu_publication.taxonomy import EDITORIAL_SECTIONS, WTPU_BRAND_ID


WTPU_DASHBOARD_SCHEMA_VERSION = "wtpu_publication_dashboard.v1"
WTPU_NO_LEDGER_NOTICE = "No WTPU editorial ledger records exist yet."
WTPU_DASHBOARD_AUTHORITY = {
    "release": False,
    "publish": False,
    "schedule": False,
    "export": False,
    "approve": False,
}
WTPU_DASHBOARD_DISCLOSURES = {
    "internal_only": "Local internal WTPU editorial dashboard. Read-only projection view. No publication authority is available here.",
    "canonical": "Canonical means internally reviewed record quality. It does not mean published, released, scheduled, or true by decree.",
    "archive_ready": "Archive ready means the internal dossier has no current readiness blockers. It does not make anything public.",
    "adaptation": "Draft adaptation only. Target platform is descriptive metadata; no platform action can be taken here.",
    "blocked": "Blocked for internal record quality. Resolve through approved editorial workflows, not from this dashboard.",
    "provenance": "Source references show provenance and limitations. A source link or hash is not independent factual verification.",
    "correction": "History is ledger-derived and preserved. Corrections append context; they do not erase prior canonical records.",
}


class WTPUDashboardError(RuntimeError):
    status_code = HTTPStatus.BAD_REQUEST
    error_code = "wtpu_dashboard_error"


class WTPUDashboardNotFound(WTPUDashboardError):
    status_code = HTTPStatus.NOT_FOUND
    error_code = "wtpu_record_missing"


class WTPUDashboardBadRequest(WTPUDashboardError):
    status_code = HTTPStatus.BAD_REQUEST
    error_code = "wtpu_request_invalid"


def is_wtpu_publication_path(path: str) -> bool:
    return path == "/wtpu-publication" or path.startswith("/api/wtpu-publication")


def wtpu_method_not_allowed_payload(method: str) -> Dict[str, Any]:
    return _envelope(
        ok=False,
        status="method_not_allowed",
        error="wtpu_publication_read_only",
        message=f"{method.upper()} is not allowed for the WTPU read-only dashboard.",
    )


def render_wtpu_publication_dashboard_page() -> str:
    try:
        context = _projection_context()
        payload = dashboard_payload(context=context)
        sections = sections_payload(context=context)["sections"]
        issues = issues_payload(context=context)["issues"]
        essays = essays_payload(context=context)["essays"]
        source_packets = _source_packet_rows(context.projection)
        corrections = correction_chains_payload(context=context)["correction_chains"]
        archive = archive_readiness_payload(context=context)["archive_readiness"]
        error = ""
    except Exception as exc:
        payload = _envelope(ok=False, status="error", error="wtpu_projection_replay_failed", message=str(exc))
        sections = []
        issues = []
        essays = []
        source_packets = []
        corrections = []
        archive = []
        error = str(exc)

    return _dashboard_html(
        dashboard=payload,
        sections=sections,
        issues=issues,
        essays=essays,
        source_packets=source_packets,
        corrections=corrections,
        archive_readiness=archive,
        error=error,
    )


def handle_wtpu_publication_api(path: str, query: str = "") -> Tuple[Dict[str, Any], HTTPStatus]:
    try:
        context = _projection_context()
        payload = _api_payload(path=path, query=parse_qs(query), context=context)
        return payload, HTTPStatus.OK
    except WTPUDashboardError as exc:
        return _envelope(
            ok=False,
            status="not_found" if exc.status_code == HTTPStatus.NOT_FOUND else "validation_error",
            error=exc.error_code,
            message=str(exc),
        ), exc.status_code
    except (WTPUProjectionReplayError, WTPUProjectionTransitionError, ValueError, TypeError) as exc:
        return _envelope(
            ok=False,
            status="validation_error",
            error="wtpu_projection_replay_failed",
            message=str(exc),
        ), HTTPStatus.BAD_REQUEST
    except Exception as exc:
        return _envelope(
            ok=False,
            status="error",
            error="wtpu_dashboard_unavailable",
            message=str(exc),
        ), HTTPStatus.INTERNAL_SERVER_ERROR


class _ProjectionContext:
    def __init__(
        self,
        *,
        projection: WTPUPublicationProjection,
        events: list[Any],
        ledger_records: list[Mapping[str, Any]],
        ledger_path: str,
    ) -> None:
        self.projection = projection
        self.events = events
        self.ledger_records = ledger_records
        self.ledger_path = ledger_path

    @property
    def has_ledger_records(self) -> bool:
        return bool(self.ledger_records)


def _projection_context() -> _ProjectionContext:
    ledger = WTPUPublicationLedger(root=_get_root())
    events = ledger.read_events(validate=True)
    projection = replay_wtpu_publication_events(events)
    records = ledger.read_records(validate=True)
    return _ProjectionContext(
        projection=projection,
        events=events,
        ledger_records=records,
        ledger_path=str(ledger.path),
    )


def _api_payload(path: str, query: Mapping[str, list[str]], context: _ProjectionContext) -> Dict[str, Any]:
    prefix = "/api/wtpu-publication"
    if path == f"{prefix}/dashboard":
        return dashboard_payload(context=context)
    if path == f"{prefix}/sections":
        return sections_payload(context=context)
    if path.startswith(f"{prefix}/sections/"):
        section_id = _tail_id(path, f"{prefix}/sections/")
        return section_payload(section_id, context=context)
    if path == f"{prefix}/issues":
        return issues_payload(context=context, query=query)
    if path.startswith(f"{prefix}/issues/"):
        issue_id = _tail_id(path, f"{prefix}/issues/")
        return issue_payload(issue_id, context=context)
    if path == f"{prefix}/essays":
        return essays_payload(context=context, query=query)
    if path.startswith(f"{prefix}/essays/"):
        essay_id = _tail_id(path, f"{prefix}/essays/")
        return essay_payload(essay_id, context=context)
    if path.startswith(f"{prefix}/source-packets/"):
        source_packet_id = _tail_id(path, f"{prefix}/source-packets/")
        return source_packet_payload(source_packet_id, context=context)
    if path.startswith(f"{prefix}/adaptations/"):
        adaptation_id = _tail_id(path, f"{prefix}/adaptations/")
        return adaptation_payload(adaptation_id, context=context)
    if path.startswith(f"{prefix}/corrections/"):
        correction_id = _tail_id(path, f"{prefix}/corrections/")
        return correction_payload(correction_id, context=context)
    if path == f"{prefix}/archive-readiness":
        return archive_readiness_payload(context=context, query=query)
    if path.startswith(f"{prefix}/history/"):
        parts = path[len(f"{prefix}/history/") :].split("/")
        if len(parts) != 2:
            raise WTPUDashboardBadRequest("wtpu_history_route_invalid")
        return history_payload(parts[0], parts[1], context=context)
    raise WTPUDashboardNotFound(f"wtpu_dashboard_route_missing:{path}")


def dashboard_payload(*, context: _ProjectionContext) -> Dict[str, Any]:
    projection = context.projection
    summary = dict(projection.dashboard_summary())
    summary["ledger_section_record_count"] = summary.get("section_count", 0)
    summary["section_count"] = len(EDITORIAL_SECTIONS)
    archive_rows = [_archive_readiness_row(projection, issue_id) for issue_id in sorted(projection.issues)]
    blocker_counts = Counter(blocker for row in archive_rows for blocker in row.get("blockers", ()))
    payload = _envelope(
        status="ready",
        brand_id=WTPU_BRAND_ID,
        no_ledger_records=not context.has_ledger_records,
        no_ledger_notice=WTPU_NO_LEDGER_NOTICE if not context.has_ledger_records else "",
        ledger={"event_count": len(context.events), "path": context.ledger_path},
        summary=summary,
        sections=_section_rows(projection),
        issue_count=len(projection.issues),
        canonical_essay_count=summary.get("canonical_essay_count", 0),
        review_needed_count=summary.get("review_requested_count", 0),
        correction_pending_count=sum(1 for essay in projection.essays.values() if essay.status == "correction_pending"),
        archive_readiness_blocker_counts=dict(sorted(blocker_counts.items())),
        recent_internal_events=_recent_events(context.events),
        disclosures=dict(WTPU_DASHBOARD_DISCLOSURES),
    )
    return payload


def sections_payload(*, context: _ProjectionContext) -> Dict[str, Any]:
    return _envelope(
        status="ready",
        brand_id=WTPU_BRAND_ID,
        no_ledger_records=not context.has_ledger_records,
        no_ledger_notice=WTPU_NO_LEDGER_NOTICE if not context.has_ledger_records else "",
        sections=_section_rows(context.projection),
    )


def section_payload(section_id: str, *, context: _ProjectionContext) -> Dict[str, Any]:
    if section_id not in EDITORIAL_SECTIONS:
        raise WTPUDashboardNotFound(f"wtpu_section_missing:{section_id}")
    section = next(row for row in _section_rows(context.projection) if row["section_id"] == section_id)
    issues = [
        _issue_row(issue, context.projection)
        for issue in sorted(context.projection.issues.values(), key=lambda item: item.issue_id)
        if issue.section_id == section_id
    ]
    return _envelope(status="ready", brand_id=WTPU_BRAND_ID, section=section, issues=issues)


def issues_payload(*, context: _ProjectionContext, query: Mapping[str, list[str]] | None = None) -> Dict[str, Any]:
    rows = [_issue_row(issue, context.projection) for issue in sorted(context.projection.issues.values(), key=lambda item: item.issue_id)]
    rows = _filter_rows(rows, query or {}, allowed={"section_id", "status", "jurisdiction", "scope", "archive_status"})
    return _envelope(status="ready", brand_id=WTPU_BRAND_ID, issues=rows, count=len(rows))


def issue_payload(issue_id: str, *, context: _ProjectionContext) -> Dict[str, Any]:
    if issue_id not in context.projection.issues:
        raise WTPUDashboardNotFound(f"wtpu_issue_missing:{issue_id}")
    summary = context.projection.issue_summary(issue_id)
    return _envelope(status="ready", brand_id=WTPU_BRAND_ID, **_without_event_ids(summary))


def essays_payload(*, context: _ProjectionContext, query: Mapping[str, list[str]] | None = None) -> Dict[str, Any]:
    rows = [_essay_row(essay, context.projection) for essay in sorted(context.projection.essays.values(), key=lambda item: item.essay_id)]
    rows = _filter_rows(rows, query or {}, allowed={"section_id", "issue_id", "status"})
    return _envelope(status="ready", brand_id=WTPU_BRAND_ID, essays=rows, count=len(rows))


def essay_payload(essay_id: str, *, context: _ProjectionContext) -> Dict[str, Any]:
    if essay_id not in context.projection.essays:
        raise WTPUDashboardNotFound(f"wtpu_essay_missing:{essay_id}")
    summary = context.projection.essay_summary(essay_id)
    summary["publication_boundary"] = _publication_boundary("essay")
    return _envelope(status="ready", brand_id=WTPU_BRAND_ID, **_without_event_ids(summary))


def source_packet_payload(source_packet_id: str, *, context: _ProjectionContext) -> Dict[str, Any]:
    packet = context.projection.source_packets.get(source_packet_id)
    if packet is None:
        raise WTPUDashboardNotFound(f"wtpu_source_packet_missing:{source_packet_id}")
    return _envelope(
        status="ready",
        brand_id=WTPU_BRAND_ID,
        source_packet=_source_packet_row(packet, context.projection),
        linked_claims=_linked_claims_for_source_packet(source_packet_id, context.projection),
        linked_essays=[
            _essay_row(essay, context.projection)
            for essay in context.projection.essays.values()
            if source_packet_id in essay.source_packet_ids
        ],
        locator_rendering="plain_text_only",
    )


def adaptation_payload(adaptation_id: str, *, context: _ProjectionContext) -> Dict[str, Any]:
    adaptation = context.projection.adaptations.get(adaptation_id)
    if adaptation is None:
        raise WTPUDashboardNotFound(f"wtpu_adaptation_missing:{adaptation_id}")
    essay = context.projection.essays.get(adaptation.essay_id)
    return _envelope(
        status="ready",
        brand_id=WTPU_BRAND_ID,
        adaptation=adaptation.to_dict(),
        parent_essay=_essay_row(essay, context.projection) if essay else None,
        disclosure=WTPU_DASHBOARD_DISCLOSURES["adaptation"],
        publication_boundary=_publication_boundary("adaptation"),
    )


def correction_payload(correction_id: str, *, context: _ProjectionContext) -> Dict[str, Any]:
    correction = context.projection.corrections.get(correction_id)
    if correction is None:
        raise WTPUDashboardNotFound(f"wtpu_correction_missing:{correction_id}")
    return _envelope(
        status="ready",
        brand_id=WTPU_BRAND_ID,
        correction=correction.to_dict(),
        correction_chain=_correction_chain_for_target(correction.target_id, context.projection),
        disclosure=WTPU_DASHBOARD_DISCLOSURES["correction"],
    )


def correction_chains_payload(*, context: _ProjectionContext) -> Dict[str, Any]:
    return _envelope(
        status="ready",
        brand_id=WTPU_BRAND_ID,
        correction_chains=_correction_chains(context.projection),
    )


def archive_readiness_payload(
    *,
    context: _ProjectionContext,
    query: Mapping[str, list[str]] | None = None,
) -> Dict[str, Any]:
    issue_id = _query_value(query or {}, "issue_id")
    if issue_id:
        if issue_id not in context.projection.issues:
            raise WTPUDashboardNotFound(f"wtpu_issue_missing:{issue_id}")
        rows = [_archive_readiness_row(context.projection, issue_id)]
    else:
        rows = [_archive_readiness_row(context.projection, item) for item in sorted(context.projection.issues)]
    return _envelope(
        status="ready",
        brand_id=WTPU_BRAND_ID,
        archive_readiness=rows,
        disclosure=WTPU_DASHBOARD_DISCLOSURES["archive_ready"],
    )


def history_payload(record_type: str, record_id: str, *, context: _ProjectionContext) -> Dict[str, Any]:
    normalized = record_type.strip().lower().replace("-", "_")
    histories: Dict[str, Mapping[str, Iterable[Any]]] = {
        "issue": context.projection.issue_history,
        "issues": context.projection.issue_history,
        "source_packet": context.projection.source_packet_history,
        "source_packets": context.projection.source_packet_history,
        "essay": context.projection.essay_history,
        "essays": context.projection.essay_history,
        "campaign_link": context.projection.campaign_link_history,
        "campaign_links": context.projection.campaign_link_history,
        "adaptation": context.projection.adaptation_history,
        "adaptations": context.projection.adaptation_history,
    }
    if normalized in {"correction", "corrections"}:
        chain = _correction_chain_for_target(record_id, context.projection)
        if not chain["hash_groups"]:
            correction = context.projection.corrections.get(record_id)
            if correction is None:
                raise WTPUDashboardNotFound(f"wtpu_history_missing:{record_type}:{record_id}")
            chain = _correction_chain_for_target(correction.target_id, context.projection)
        return _envelope(status="ready", brand_id=WTPU_BRAND_ID, record_type=normalized, record_id=record_id, history=chain)
    history = histories.get(normalized)
    if history is None:
        raise WTPUDashboardBadRequest(f"wtpu_record_type_invalid:{record_type}")
    versions = history.get(record_id, ())
    if not versions:
        raise WTPUDashboardNotFound(f"wtpu_history_missing:{record_type}:{record_id}")
    return _envelope(
        status="ready",
        brand_id=WTPU_BRAND_ID,
        record_type=normalized,
        record_id=record_id,
        versions=[_without_event_ids(item.to_dict()) for item in versions],
    )


def _envelope(ok: bool = True, status: str = "ready", **payload: Any) -> Dict[str, Any]:
    base = {
        "ok": ok,
        "status": status,
        "schema_version": WTPU_DASHBOARD_SCHEMA_VERSION,
        "read_only": True,
        "mutation_allowed": False,
        "authority": dict(WTPU_DASHBOARD_AUTHORITY),
    }
    base.update(payload)
    return base


def _section_rows(projection: WTPUPublicationProjection) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for section_id in EDITORIAL_SECTIONS:
        section = projection.sections.get(section_id)
        issues = [issue for issue in projection.issues.values() if issue.section_id == section_id]
        archive_blockers = [
            blocker
            for issue in issues
            for blocker in projection.archive_readiness(issue.issue_id).blockers
        ]
        statuses = Counter(issue.status for issue in issues)
        tags = sorted({tag for issue in issues for tag in issue.topic_tags})
        rows.append(
            {
                "section_id": section_id,
                "display_name": section.display_name if section else _display_name(section_id),
                "description": section.description if section else "",
                "brand_id": WTPU_BRAND_ID,
                "issue_count": len(issues),
                "topic_tags": tags,
                "status_distribution": dict(sorted(statuses.items())),
                "unresolved_review_or_blocker_count": len(archive_blockers),
                "archive_readiness_blockers": sorted(set(archive_blockers)),
            }
        )
    return rows


def _issue_row(issue: Any, projection: WTPUPublicationProjection) -> Dict[str, Any]:
    readiness = projection.archive_readiness(issue.issue_id)
    essays = [essay for essay in projection.essays.values() if essay.issue_id == issue.issue_id]
    corrections = [
        correction
        for correction in projection.corrections.values()
        if correction.target_id == issue.issue_id or correction.target_id in {essay.essay_id for essay in essays}
    ]
    row = issue.to_dict()
    row.update(
        {
            "essay_count": len(essays),
            "source_packet_count": len(readiness.source_packet_ids),
            "campaign_link_count": len([link for link in projection.campaign_links.values() if link.issue_id == issue.issue_id]),
            "adaptation_count": len([item for item in projection.adaptations.values() if item.essay_id in {essay.essay_id for essay in essays}]),
            "correction_count": len(corrections),
            "archive_readiness": readiness.to_dict(),
            "publication_boundary": _publication_boundary("issue"),
        }
    )
    return _without_event_ids(row)


def _essay_row(essay: Any, projection: WTPUPublicationProjection) -> Dict[str, Any]:
    if essay is None:
        return {}
    claim_types = Counter(claim.claim_type or "untyped" for claim in essay.claim_index)
    row = essay.to_dict()
    row.update(
        {
            "claim_type_counts": dict(sorted(claim_types.items())),
            "reviewer_hash_status": "matched" if essay.approved_content_hash and essay.approved_content_hash == essay.content_hash else "not_approved_current_hash",
            "correction_count": len([item for item in projection.corrections.values() if item.target_id == essay.essay_id]),
            "publication_boundary": _publication_boundary("essay"),
        }
    )
    return _without_event_ids(row)


def _source_packet_rows(projection: WTPUPublicationProjection) -> List[Dict[str, Any]]:
    return [
        _source_packet_row(packet, projection)
        for packet in sorted(projection.source_packets.values(), key=lambda item: item.source_packet_id)
    ]


def _source_packet_row(packet: Any, projection: WTPUPublicationProjection) -> Dict[str, Any]:
    row = packet.to_dict()
    row["source_refs"] = [
        {
            **ref.to_dict(),
            "locator_rendering": "plain_text_only",
        }
        for ref in packet.source_refs
    ]
    row["linked_essay_ids"] = sorted(
        essay.essay_id for essay in projection.essays.values() if packet.source_packet_id in essay.source_packet_ids
    )
    row["linked_claim_count"] = len(_linked_claims_for_source_packet(packet.source_packet_id, projection))
    return _without_event_ids(row)


def _linked_claims_for_source_packet(source_packet_id: str, projection: WTPUPublicationProjection) -> List[Dict[str, Any]]:
    packet = projection.source_packets.get(source_packet_id)
    if packet is None:
        return []
    source_ref_ids = {ref.source_ref_id for ref in packet.source_refs}
    claims: List[Dict[str, Any]] = []
    for essay in projection.essays.values():
        if source_packet_id not in essay.source_packet_ids:
            continue
        for claim in essay.claim_index:
            if source_ref_ids & set(claim.source_refs):
                payload = claim.to_dict()
                payload["essay_id"] = essay.essay_id
                claims.append(payload)
    return claims


def _archive_readiness_row(projection: WTPUPublicationProjection, issue_id: str) -> Dict[str, Any]:
    readiness = projection.archive_readiness(issue_id)
    issue = projection.issues[issue_id]
    row = readiness.to_dict()
    row.update(
        {
            "issue_title": issue.title,
            "jurisdiction": issue.jurisdiction,
            "scope": issue.scope,
            "disclosure": WTPU_DASHBOARD_DISCLOSURES["archive_ready"],
        }
    )
    return row


def _correction_chains(projection: WTPUPublicationProjection) -> List[Dict[str, Any]]:
    target_ids = sorted({correction.target_id for correction in projection.corrections.values()})
    return [_correction_chain_for_target(target_id, projection) for target_id in target_ids]


def _correction_chain_for_target(target_id: str, projection: WTPUPublicationProjection) -> Dict[str, Any]:
    corrections = [
        correction
        for correction in projection.corrections.values()
        if correction.target_id == target_id
    ]
    by_hash: Dict[str, List[Any]] = defaultdict(list)
    for correction in sorted(corrections, key=lambda item: (item.created_at, item.correction_id)):
        by_hash[correction.target_hash].append(correction)
    return {
        "target_id": target_id,
        "hash_groups": [
            {
                "target_hash": target_hash,
                "records": [_without_event_ids(item.to_dict()) for item in records],
            }
            for target_hash, records in sorted(by_hash.items())
        ],
    }


def _recent_events(events: List[Any], limit: int = 8) -> List[Dict[str, str]]:
    return [
        {
            "event_type": str(event.event_type),
            "occurred_at": str(event.occurred_at),
            "entity_type": str(event.entity_type),
            "entity_id": str(event.entity_id),
            "section_id": str(event.section_id),
            "issue_id": str(event.issue_id),
            "essay_id": str(event.essay_id),
        }
        for event in sorted(events, key=lambda item: str(item.occurred_at))[-limit:]
    ]


def _publication_boundary(record_type: str) -> Dict[str, Any]:
    return {
        "record_type": record_type,
        "editorial_status_is_release_status": False,
        "canonical_means_published": False,
        "reviewed_means_scheduled": False,
        "archive_ready_means_public": False,
        "notice": "Editorial status is not release status.",
    }


def _filter_rows(rows: List[Dict[str, Any]], query: Mapping[str, list[str]], *, allowed: set[str]) -> List[Dict[str, Any]]:
    unknown = sorted(key for key in query if key not in allowed)
    if unknown:
        raise WTPUDashboardBadRequest(f"wtpu_filter_invalid:{','.join(unknown)}")
    filtered = rows
    for key in sorted(allowed):
        expected = _query_value(query, key)
        if expected:
            filtered = [row for row in filtered if str(row.get(key) or "") == expected]
    return filtered


def _query_value(query: Mapping[str, list[str]], key: str) -> str:
    values = query.get(key) or []
    return str(values[0] or "").strip() if values else ""


def _tail_id(path: str, prefix: str) -> str:
    value = path[len(prefix) :].strip("/")
    if not value or "/" in value:
        raise WTPUDashboardBadRequest(f"wtpu_route_id_invalid:{path}")
    return value


def _without_event_ids(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _without_event_ids(item)
            for key, item in value.items()
            if str(key) not in {"event_id", "audit_event_refs", "command_event_ids"}
        }
    if isinstance(value, list):
        return [_without_event_ids(item) for item in value]
    if isinstance(value, tuple):
        return [_without_event_ids(item) for item in value]
    return value


def _display_name(section_id: str) -> str:
    return section_id.replace("_", " ").title()


def _dashboard_html(
    *,
    dashboard: Mapping[str, Any],
    sections: List[Mapping[str, Any]],
    issues: List[Mapping[str, Any]],
    essays: List[Mapping[str, Any]],
    source_packets: List[Mapping[str, Any]],
    corrections: List[Mapping[str, Any]],
    archive_readiness: List[Mapping[str, Any]],
    error: str,
) -> str:
    notices = WTPU_DASHBOARD_DISCLOSURES
    no_ledger_notice = str(dashboard.get("no_ledger_notice") or "")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WTPU Read-Only Publication Dashboard</title>
  <style>
    :root {{
      --bg: #f5f7f6;
      --panel: #ffffff;
      --ink: #202528;
      --muted: #667076;
      --line: #d9dfdc;
      --soft: #edf1ef;
      --green: #17613b;
      --green-bg: #e6f4eb;
      --red: #9b302c;
      --red-bg: #f8e8e4;
      --blue: #22577a;
      --blue-bg: #e4eef7;
      --amber: #755700;
      --amber-bg: #fff2ca;
      font-family: Inter, "Segoe UI", Arial, sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: var(--bg); color: var(--ink); font-size: 14px; line-height: 1.45; }}
    header {{ padding: 18px 22px; border-bottom: 1px solid var(--line); background: var(--panel); }}
    main {{ display: grid; gap: 16px; padding: 18px 22px 28px; }}
    h1, h2, h3, p {{ margin: 0; }}
    h1 {{ font-size: 22px; }}
    h2 {{ font-size: 16px; margin-bottom: 10px; }}
    h3 {{ font-size: 14px; margin-bottom: 6px; }}
    .banner {{ border: 1px solid var(--blue); background: var(--blue-bg); color: var(--ink); padding: 12px; border-radius: 8px; }}
    .warning {{ border: 1px solid var(--amber); background: var(--amber-bg); color: var(--ink); padding: 10px; border-radius: 8px; }}
    .error {{ border: 1px solid var(--red); background: var(--red-bg); color: var(--ink); padding: 10px; border-radius: 8px; }}
    .panel {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 14px; overflow-x: auto; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; }}
    .metric {{ background: var(--soft); border: 1px solid var(--line); border-radius: 8px; padding: 10px; }}
    .metric strong {{ display: block; font-size: 20px; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 720px; }}
    th, td {{ text-align: left; vertical-align: top; padding: 8px; border-bottom: 1px solid var(--line); }}
    th {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0; }}
    .muted {{ color: var(--muted); }}
    .badge {{ display: inline-block; border-radius: 999px; padding: 2px 8px; background: var(--soft); border: 1px solid var(--line); margin: 1px; }}
    .badge.good {{ color: var(--green); background: var(--green-bg); border-color: #c8e5d3; }}
    .badge.warn {{ color: var(--amber); background: var(--amber-bg); border-color: #e8d38d; }}
    .badge.bad {{ color: var(--red); background: var(--red-bg); border-color: #edc4bd; }}
    code {{ background: var(--soft); border: 1px solid var(--line); border-radius: 6px; padding: 1px 4px; }}
    .plain {{ word-break: break-word; }}
  </style>
</head>
<body>
  <header>
    <h1>WTPU Read-Only Publication Dashboard</h1>
    <p class="muted">Projection-derived local operator view for <code>{escape(WTPU_BRAND_ID)}</code>.</p>
  </header>
  <main>
    <section class="banner">
      <strong>Internal only.</strong> {escape(notices["internal_only"])}
      <div>{escape(notices["canonical"])}</div>
      <div>{escape(notices["archive_ready"])}</div>
    </section>
    {_notice_html(no_ledger_notice)}
    {_error_html(error)}
    <section class="panel">
      <h2>Dashboard Home</h2>
      {_metrics_html(dashboard)}
    </section>
    <section class="panel">
      <h2>Editorial Sections</h2>
      {_sections_table(sections)}
    </section>
    <section class="panel">
      <h2>Issues</h2>
      {_issues_table(issues)}
    </section>
    <section class="panel">
      <h2>Canonical Civic Essays</h2>
      <p class="muted">{escape(notices["canonical"])}</p>
      {_essays_table(essays)}
    </section>
    <section class="panel">
      <h2>Source Packets</h2>
      <p class="muted">{escape(notices["provenance"])} Source locators are rendered as plain text only.</p>
      {_source_packets_table(source_packets)}
    </section>
    <section class="panel">
      <h2>Corrections And Updates</h2>
      <p class="muted">{escape(notices["correction"])}</p>
      {_corrections_table(corrections)}
    </section>
    <section class="panel">
      <h2>Archive Readiness</h2>
      <p class="muted">{escape(notices["archive_ready"])}</p>
      {_archive_table(archive_readiness)}
    </section>
    <section class="warning">
      {escape(notices["adaptation"])} Editorial status is not release status. Nothing in this dashboard grants publication authority.
    </section>
  </main>
</body>
</html>
"""


def _notice_html(notice: str) -> str:
    return f'<section class="warning">{escape(notice)}</section>' if notice else ""


def _error_html(error: str) -> str:
    return f'<section class="error">{escape(error)}</section>' if error else ""


def _metrics_html(dashboard: Mapping[str, Any]) -> str:
    summary = dict(dashboard.get("summary") or {})
    metrics = [
        ("Sections", summary.get("section_count", 0)),
        ("Issues", summary.get("issue_count", 0)),
        ("Canonical Essays", dashboard.get("canonical_essay_count", 0)),
        ("Review Needed", dashboard.get("review_needed_count", 0)),
        ("Correction Pending", dashboard.get("correction_pending_count", 0)),
        ("Ledger Events", dict(dashboard.get("ledger") or {}).get("event_count", 0)),
    ]
    return '<div class="grid">' + "".join(
        f'<div class="metric"><span>{escape(label)}</span><strong>{escape(str(value))}</strong></div>'
        for label, value in metrics
    ) + "</div>"


def _sections_table(sections: List[Mapping[str, Any]]) -> str:
    rows = "".join(
        "<tr>"
        f"<td><code>{escape(str(row.get('section_id') or ''))}</code></td>"
        f"<td>{escape(str(row.get('display_name') or ''))}</td>"
        f"<td>{escape(str(row.get('issue_count') or 0))}</td>"
        f"<td>{_badges(row.get('topic_tags') or [])}</td>"
        f"<td>{_badges((row.get('archive_readiness_blockers') or []), empty='none')}</td>"
        "</tr>"
        for row in sections
    )
    return f"<table><thead><tr><th>Section</th><th>Name</th><th>Issues</th><th>Topic Tags</th><th>Blockers</th></tr></thead><tbody>{rows}</tbody></table>"


def _issues_table(issues: List[Mapping[str, Any]]) -> str:
    if not issues:
        return '<p class="muted">No issue records.</p>'
    rows = "".join(
        "<tr>"
        f"<td><code>{escape(str(row.get('issue_id') or ''))}</code></td>"
        f"<td>{escape(str(row.get('title') or ''))}</td>"
        f"<td>{escape(str(row.get('jurisdiction') or ''))}</td>"
        f"<td>{escape(str(row.get('scope') or ''))}</td>"
        f"<td>{escape(str(row.get('status') or ''))}</td>"
        f"<td>{_badges(dict(row.get('archive_readiness') or {}).get('blockers') or [], empty='ready')}</td>"
        "</tr>"
        for row in issues
    )
    return f"<table><thead><tr><th>Issue</th><th>Title</th><th>Jurisdiction</th><th>Scope</th><th>Editorial Status</th><th>Archive Blockers</th></tr></thead><tbody>{rows}</tbody></table>"


def _essays_table(essays: List[Mapping[str, Any]]) -> str:
    if not essays:
        return '<p class="muted">No canonical civic essay records.</p>'
    rows = "".join(
        "<tr>"
        f"<td><code>{escape(str(row.get('essay_id') or ''))}</code></td>"
        f"<td>{escape(str(row.get('title') or ''))}</td>"
        f"<td>{escape(str(row.get('status') or ''))}</td>"
        f"<td>{escape(str(row.get('reviewer_hash_status') or ''))}</td>"
        f"<td>{_badges((row.get('claim_type_counts') or {}).keys(), empty='none')}</td>"
        "</tr>"
        for row in essays
    )
    return f"<table><thead><tr><th>Essay</th><th>Title</th><th>Internal Lifecycle</th><th>Reviewer/Hash</th><th>Claim Types</th></tr></thead><tbody>{rows}</tbody></table>"


def _source_packets_table(source_packets: List[Mapping[str, Any]]) -> str:
    if not source_packets:
        return '<p class="muted">No source packet records.</p>'
    rows: List[str] = []
    for packet in source_packets:
        refs = packet.get("source_refs") or []
        ref_text = "<br>".join(
            f"<code>{escape(str(ref.get('source_ref_id') or ''))}</code> "
            f"{escape(str(ref.get('source_type') or ''))}<br>"
            f"<span class=\"plain\">{escape(str(ref.get('locator') or ''))}</span><br>"
            f"<code>{escape(str(ref.get('source_content_hash') or ''))}</code>"
            for ref in refs
            if isinstance(ref, Mapping)
        )
        rows.append(
            "<tr>"
            f"<td><code>{escape(str(packet.get('source_packet_id') or ''))}</code></td>"
            f"<td>{escape(str(packet.get('title') or ''))}</td>"
            f"<td>{ref_text}</td>"
            f"<td>{_badges(packet.get('source_limitations') or [], empty='none')}</td>"
            "</tr>"
        )
    return f"<table><thead><tr><th>Packet</th><th>Title</th><th>Plain Text Source References</th><th>Limitations</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"


def _corrections_table(corrections: List[Mapping[str, Any]]) -> str:
    if not corrections:
        return '<p class="muted">No correction or update records.</p>'
    rows: List[str] = []
    for chain in corrections:
        target_id = str(chain.get("target_id") or "")
        for group in chain.get("hash_groups") or []:
            target_hash = str(group.get("target_hash") or "")
            for record in group.get("records") or []:
                if not isinstance(record, Mapping):
                    continue
                rows.append(
                    "<tr>"
                    f"<td><code>{escape(target_id)}</code></td>"
                    f"<td><code>{escape(target_hash)}</code></td>"
                    f"<td><code>{escape(str(record.get('correction_id') or ''))}</code></td>"
                    f"<td>{escape(str(record.get('correction_type') or ''))}</td>"
                    f"<td>{escape(str(record.get('status') or ''))}</td>"
                    f"<td>{escape(str(record.get('reason') or ''))}</td>"
                    "</tr>"
                )
    return f"<table><thead><tr><th>Target ID</th><th>Target Hash</th><th>Correction</th><th>Type</th><th>Status</th><th>Reason</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"


def _archive_table(rows_payload: List[Mapping[str, Any]]) -> str:
    if not rows_payload:
        return '<p class="muted">No issue records available for archive-readiness calculation.</p>'
    rows = "".join(
        "<tr>"
        f"<td><code>{escape(str(row.get('issue_id') or ''))}</code></td>"
        f"<td>{escape(str(row.get('issue_title') or ''))}</td>"
        f"<td>{_yes_no(bool(row.get('archive_ready')))}</td>"
        f"<td>{_badges(row.get('blockers') or [], empty='none')}</td>"
        "</tr>"
        for row in rows_payload
    )
    return f"<table><thead><tr><th>Issue</th><th>Title</th><th>Archive Ready</th><th>Blockers</th></tr></thead><tbody>{rows}</tbody></table>"


def _badges(values: Iterable[Any], *, empty: str = "") -> str:
    clean = [str(value) for value in values if str(value or "").strip()]
    if not clean and empty:
        return f'<span class="badge good">{escape(empty)}</span>'
    return " ".join(f'<span class="badge">{escape(value)}</span>' for value in clean)


def _yes_no(value: bool) -> str:
    return '<span class="badge good">yes</span>' if value else '<span class="badge warn">no</span>'
