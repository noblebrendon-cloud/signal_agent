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
from urllib.parse import parse_qs, quote, urlencode

from app.letters_of_light.release import _get_root
from signal_agent.wtpu_publication.ledgers import WTPUPublicationLedger
from signal_agent.wtpu_publication.projection import (
    WTPUProjectionReplayError,
    WTPUProjectionTransitionError,
    WTPUPublicationProjection,
    replay_wtpu_publication_events,
)
from signal_agent.wtpu_publication.taxonomy import EDITORIAL_SECTIONS, ESSAY_LIFECYCLE, WTPU_BRAND_ID


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


class WTPUDashboardFilterInvalid(WTPUDashboardError):
    status_code = HTTPStatus.BAD_REQUEST
    error_code = "wtpu_filter_invalid"


def is_wtpu_publication_path(path: str) -> bool:
    return (
        path == "/wtpu-publication"
        or path.startswith("/wtpu-publication/")
        or path.startswith("/api/wtpu-publication")
    )


def wtpu_method_not_allowed_payload(method: str) -> Dict[str, Any]:
    return _envelope(
        ok=False,
        status="method_not_allowed",
        error="wtpu_publication_read_only",
        message=f"{method.upper()} is not allowed for the WTPU read-only dashboard.",
    )


def render_wtpu_publication_dashboard_page(
    path: str = "/wtpu-publication",
    query: str = "",
) -> Tuple[str, HTTPStatus]:
    try:
        context = _projection_context()
        return _html_payload(path=path, query=parse_qs(query), context=context), HTTPStatus.OK
    except WTPUDashboardError as exc:
        return _error_page(str(exc)), exc.status_code
    except Exception as exc:
        return _error_page(str(exc)), HTTPStatus.INTERNAL_SERVER_ERROR


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
        return dashboard_payload(context=context, query=query)
    if path == f"{prefix}/sections":
        return sections_payload(context=context)
    if path.startswith(f"{prefix}/sections/"):
        section_id = _tail_id(path, f"{prefix}/sections/")
        return section_payload(section_id, context=context, query=query)
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
    if path == f"{prefix}/source-packets":
        return source_packets_payload(context=context)
    if path.startswith(f"{prefix}/source-packets/"):
        source_packet_id = _tail_id(path, f"{prefix}/source-packets/")
        return source_packet_payload(source_packet_id, context=context)
    if path.startswith(f"{prefix}/adaptations/"):
        adaptation_id = _tail_id(path, f"{prefix}/adaptations/")
        return adaptation_payload(adaptation_id, context=context)
    if path == f"{prefix}/corrections":
        return correction_chains_payload(context=context)
    if path.startswith(f"{prefix}/corrections/"):
        parts = path[len(f"{prefix}/corrections/") :].strip("/").split("/")
        if len(parts) == 1 and parts[0]:
            return correction_payload(parts[0], context=context)
        if len(parts) == 2 and all(parts):
            return correction_target_payload(parts[0], parts[1], context=context)
        raise WTPUDashboardBadRequest(f"wtpu_route_id_invalid:{path}")
    if path == f"{prefix}/archive-readiness":
        return archive_readiness_payload(context=context, query=query)
    if path.startswith(f"{prefix}/archive-readiness/"):
        issue_id = _tail_id(path, f"{prefix}/archive-readiness/")
        return archive_readiness_detail_payload(issue_id, context=context)
    if path.startswith(f"{prefix}/history/"):
        parts = path[len(f"{prefix}/history/") :].split("/")
        if len(parts) != 2:
            raise WTPUDashboardBadRequest("wtpu_history_route_invalid")
        return history_payload(parts[0], parts[1], context=context)
    raise WTPUDashboardNotFound(f"wtpu_dashboard_route_missing:{path}")


def dashboard_payload(
    *,
    context: _ProjectionContext,
    query: Mapping[str, list[str]] | None = None,
) -> Dict[str, Any]:
    projection = context.projection
    filters = _active_filters(query or {}, projection)
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
        ledger={"event_count": len(context.events)},
        summary=summary,
        sections=_section_rows(projection),
        active_filters=filters,
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


def section_payload(
    section_id: str,
    *,
    context: _ProjectionContext,
    query: Mapping[str, list[str]] | None = None,
) -> Dict[str, Any]:
    if section_id not in EDITORIAL_SECTIONS:
        raise WTPUDashboardNotFound(f"wtpu_section_missing:{section_id}")
    filters = _active_filters(query or {}, context.projection)
    filters["section"] = section_id
    section = next(row for row in _section_rows(context.projection) if row["section_id"] == section_id)
    issues = _filtered_issue_rows(context.projection, filters)
    return _envelope(
        status="ready",
        brand_id=WTPU_BRAND_ID,
        active_filters=filters,
        section=section,
        issues=issues,
        count=len(issues),
    )


def issues_payload(*, context: _ProjectionContext, query: Mapping[str, list[str]] | None = None) -> Dict[str, Any]:
    filters = _active_filters(query or {}, context.projection)
    rows = _filtered_issue_rows(context.projection, filters)
    return _envelope(
        status="ready",
        brand_id=WTPU_BRAND_ID,
        active_filters=filters,
        issues=rows,
        count=len(rows),
        empty_result=bool(_nonempty_filters(filters)) and not rows,
    )


def issue_payload(issue_id: str, *, context: _ProjectionContext) -> Dict[str, Any]:
    if issue_id not in context.projection.issues:
        raise WTPUDashboardNotFound(f"wtpu_issue_missing:{issue_id}")
    summary = context.projection.issue_summary(issue_id)
    issue = context.projection.issues[issue_id]
    related_essays = [
        essay
        for essay in sorted(context.projection.essays.values(), key=lambda item: item.essay_id)
        if essay.issue_id == issue_id
    ]
    related_source_packet_ids = set(issue.source_packet_ids)
    for essay in related_essays:
        related_source_packet_ids.update(essay.source_packet_ids)
    source_packets = [
        _source_packet_row(packet, context.projection)
        for packet in sorted(context.projection.source_packets.values(), key=lambda item: item.source_packet_id)
        if packet.source_packet_id in related_source_packet_ids
    ]
    corrections = [
        correction
        for correction in context.projection.corrections.values()
        if correction.target_id == issue_id or correction.target_id in {essay.essay_id for essay in related_essays}
    ]
    summary.update(
        {
            "section": next(row for row in _section_rows(context.projection) if row["section_id"] == issue.section_id),
            "issue": _issue_row(issue, context.projection),
            "essays": [_essay_row(essay, context.projection) for essay in related_essays],
            "source_packets": source_packets,
            "correction_chains": [
                _correction_chain_for_target(target_id, context.projection)
                for target_id in sorted({correction.target_id for correction in corrections})
            ],
            "archive_readiness_detail": _archive_readiness_detail_row(context.projection, issue_id),
            "publication_boundary": _publication_boundary("issue"),
        }
    )
    return _envelope(status="ready", brand_id=WTPU_BRAND_ID, **_without_event_ids(summary))


def essays_payload(*, context: _ProjectionContext, query: Mapping[str, list[str]] | None = None) -> Dict[str, Any]:
    filters = _active_filters(query or {}, context.projection)
    rows = _filtered_essay_rows(context.projection, filters)
    return _envelope(
        status="ready",
        brand_id=WTPU_BRAND_ID,
        active_filters=filters,
        essays=rows,
        count=len(rows),
        empty_result=bool(_nonempty_filters(filters)) and not rows,
    )


def essay_payload(essay_id: str, *, context: _ProjectionContext) -> Dict[str, Any]:
    if essay_id not in context.projection.essays:
        raise WTPUDashboardNotFound(f"wtpu_essay_missing:{essay_id}")
    summary = context.projection.essay_summary(essay_id)
    essay = context.projection.essays[essay_id]
    issue = context.projection.issues.get(essay.issue_id)
    summary["essay"] = _essay_row(essay, context.projection)
    summary["issue"] = _issue_row(issue, context.projection) if issue else None
    summary["source_packets"] = [
        _source_packet_row(packet, context.projection)
        for packet in context.projection.source_packets.values()
        if packet.source_packet_id in essay.source_packet_ids
    ]
    summary["correction_chain"] = _correction_chain_for_target(essay_id, context.projection)
    summary["publication_boundary"] = _publication_boundary("essay")
    return _envelope(status="ready", brand_id=WTPU_BRAND_ID, **_without_event_ids(summary))


def source_packets_payload(*, context: _ProjectionContext) -> Dict[str, Any]:
    rows = _source_packet_rows(context.projection)
    return _envelope(status="ready", brand_id=WTPU_BRAND_ID, source_packets=rows, count=len(rows))


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


def correction_target_payload(
    target_type: str,
    target_id: str,
    *,
    context: _ProjectionContext,
) -> Dict[str, Any]:
    normalized = _normalize_target_type(target_type)
    target = _target_payload(normalized, target_id, context.projection)
    if target is None:
        raise WTPUDashboardNotFound(f"wtpu_correction_target_missing:{normalized}:{target_id}")
    return _envelope(
        status="ready",
        brand_id=WTPU_BRAND_ID,
        target_type=normalized,
        target_id=target_id,
        target=target,
        correction_chain=_correction_chain_for_target(target_id, context.projection),
        disclosure=WTPU_DASHBOARD_DISCLOSURES["correction"],
        preservation_notice="Correction history is preserved and not overwritten.",
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


def archive_readiness_detail_payload(issue_id: str, *, context: _ProjectionContext) -> Dict[str, Any]:
    if issue_id not in context.projection.issues:
        raise WTPUDashboardNotFound(f"wtpu_issue_missing:{issue_id}")
    return _envelope(
        status="ready",
        brand_id=WTPU_BRAND_ID,
        issue=_issue_row(context.projection.issues[issue_id], context.projection),
        archive_readiness=_archive_readiness_detail_row(context.projection, issue_id),
        disclosure=WTPU_DASHBOARD_DISCLOSURES["archive_ready"],
        publication_boundary=_publication_boundary("archive_readiness"),
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


def _active_filters(query: Mapping[str, list[str]], projection: WTPUPublicationProjection) -> Dict[str, str]:
    allowed = {"section", "essay_status", "issue_status", "jurisdiction", "scope"}
    unknown = sorted(key for key in query if key not in allowed)
    if unknown:
        raise WTPUDashboardFilterInvalid(f"wtpu_filter_invalid:{','.join(unknown)}")

    filters = {key: _query_value(query, key) for key in sorted(allowed)}
    section = filters.get("section") or ""
    if section and section not in EDITORIAL_SECTIONS:
        raise WTPUDashboardFilterInvalid(f"wtpu_filter_invalid:section:{section}")

    essay_status = filters.get("essay_status") or ""
    if essay_status and essay_status not in ESSAY_LIFECYCLE:
        raise WTPUDashboardFilterInvalid(f"wtpu_filter_invalid:essay_status:{essay_status}")

    issue_status = filters.get("issue_status") or ""
    existing_issue_statuses = {issue.status for issue in projection.issues.values() if str(issue.status).strip()}
    if issue_status and issue_status not in existing_issue_statuses:
        raise WTPUDashboardFilterInvalid(f"wtpu_filter_invalid:issue_status:{issue_status}")

    return filters


def _nonempty_filters(filters: Mapping[str, str]) -> Dict[str, str]:
    return {key: value for key, value in filters.items() if value}


def _filtered_issue_rows(projection: WTPUPublicationProjection, filters: Mapping[str, str]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for issue in sorted(projection.issues.values(), key=lambda item: item.issue_id):
        if not _issue_matches_filters(issue, filters):
            continue
        rows.append(_issue_row(issue, projection))
    return rows


def _filtered_essay_rows(projection: WTPUPublicationProjection, filters: Mapping[str, str]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for essay in sorted(projection.essays.values(), key=lambda item: item.essay_id):
        issue = projection.issues.get(essay.issue_id)
        if filters.get("essay_status") and essay.status != filters["essay_status"]:
            continue
        if filters.get("section") and essay.section_id != filters["section"]:
            continue
        if issue is not None and not _issue_matches_filters(issue, filters):
            continue
        if issue is None and any(filters.get(key) for key in ("issue_status", "jurisdiction", "scope")):
            continue
        rows.append(_essay_row(essay, projection))
    return rows


def _issue_matches_filters(issue: Any, filters: Mapping[str, str]) -> bool:
    if filters.get("section") and issue.section_id != filters["section"]:
        return False
    if filters.get("issue_status") and issue.status != filters["issue_status"]:
        return False
    if filters.get("jurisdiction") and _normalized_match_value(issue.jurisdiction) != _normalized_match_value(filters["jurisdiction"]):
        return False
    if filters.get("scope") and _normalized_match_value(issue.scope) != _normalized_match_value(filters["scope"]):
        return False
    return True


def _normalized_match_value(value: object) -> str:
    return str(value or "").strip().casefold()


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


def _archive_readiness_detail_row(projection: WTPUPublicationProjection, issue_id: str) -> Dict[str, Any]:
    row = _archive_readiness_row(projection, issue_id)
    row["blocker_details"] = _archive_blocker_details(projection, row)
    row["publication_boundary"] = _publication_boundary("archive_readiness")
    return row


def _archive_blocker_details(
    projection: WTPUPublicationProjection,
    readiness_row: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    issue_id = str(readiness_row.get("issue_id") or "")
    essay_ids = [str(item) for item in readiness_row.get("essay_ids") or []]
    source_packet_ids = [str(item) for item in readiness_row.get("source_packet_ids") or []]
    correction_ids = [str(item) for item in readiness_row.get("correction_ids") or []]
    details: List[Dict[str, Any]] = []
    for blocker in readiness_row.get("blockers") or []:
        code = str(blocker)
        links: List[Dict[str, str]] = []
        if code in {"issue_jurisdiction_missing", "issue_scope_missing", "canonical_essay_missing"}:
            links.append({"label": issue_id, "href": _local_path("issues", issue_id)})
        elif code == "canonical_essay_not_approved":
            links.extend({"label": essay_id, "href": _local_path("essays", essay_id)} for essay_id in essay_ids)
        elif code == "source_packet_missing":
            links.append({"label": issue_id, "href": _local_path("issues", issue_id)})
        elif code.startswith("source_limitations_missing:"):
            packet_id = code.split(":", 1)[1]
            links.append({"label": packet_id, "href": _local_path("source-packets", packet_id)})
        elif code == "correction_pending":
            for correction_id in correction_ids:
                correction = projection.corrections.get(correction_id)
                if correction is None:
                    continue
                links.append(
                    {
                        "label": correction.target_id,
                        "href": _local_path("corrections", correction.target_type, correction.target_id),
                    }
                )
        else:
            links.extend({"label": packet_id, "href": _local_path("source-packets", packet_id)} for packet_id in source_packet_ids)
        details.append({"blocker": code, "local_links": links})
    return details


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
    hash_groups = []
    for target_hash, records in by_hash.items():
        ordered = sorted(records, key=lambda item: (item.created_at, item.correction_id))
        hash_groups.append(
            {
                "target_hash": target_hash,
                "records": [
                    {
                        **_without_event_ids(item.to_dict()),
                        "type_label": _correction_type_label(item),
                    }
                    for item in ordered
                ],
                "first_recorded_at": str(ordered[0].created_at) if ordered else "",
            }
        )
    return {
        "target_id": target_id,
        "hash_groups": sorted(hash_groups, key=lambda item: (str(item.get("first_recorded_at") or ""), str(item.get("target_hash") or ""))),
        "preservation_notice": "Correction history is preserved and not overwritten.",
    }


def _correction_type_label(correction: Any) -> str:
    correction_type = str(correction.correction_type or "").strip().replace("_", " ")
    status = str(correction.status or "").strip().replace("_", " ")
    if correction_type:
        return correction_type
    return status or "correction record"


def _normalize_target_type(target_type: str) -> str:
    normalized = str(target_type or "").strip().lower().replace("-", "_")
    if normalized not in {"issue", "essay", "source_packet"}:
        raise WTPUDashboardBadRequest(f"wtpu_correction_target_type_invalid:{target_type}")
    return normalized


def _target_payload(target_type: str, target_id: str, projection: WTPUPublicationProjection) -> Dict[str, Any] | None:
    if target_type == "issue":
        issue = projection.issues.get(target_id)
        return _issue_row(issue, projection) if issue else None
    if target_type == "essay":
        essay = projection.essays.get(target_id)
        return _essay_row(essay, projection) if essay else None
    if target_type == "source_packet":
        packet = projection.source_packets.get(target_id)
        return _source_packet_row(packet, projection) if packet else None
    return None


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


def _html_payload(path: str, query: Mapping[str, list[str]], context: _ProjectionContext) -> str:
    if path == "/wtpu-publication":
        return _dashboard_route_html(query=query, context=context)
    prefix = "/wtpu-publication/"
    if not path.startswith(prefix):
        raise WTPUDashboardNotFound(f"wtpu_dashboard_route_missing:{path}")
    parts = path[len(prefix) :].strip("/").split("/")
    if len(parts) == 2 and parts[0] == "sections":
        return _section_detail_html(section_payload(parts[1], context=context, query=query))
    if len(parts) == 2 and parts[0] == "issues":
        return _issue_detail_html(issue_payload(parts[1], context=context))
    if len(parts) == 2 and parts[0] == "essays":
        return _essay_detail_html(essay_payload(parts[1], context=context))
    if len(parts) == 2 and parts[0] == "source-packets":
        return _source_packet_detail_html(source_packet_payload(parts[1], context=context))
    if len(parts) == 3 and parts[0] == "corrections":
        return _correction_chain_detail_html(correction_target_payload(parts[1], parts[2], context=context))
    if len(parts) == 2 and parts[0] == "archive-readiness":
        return _archive_readiness_detail_html(archive_readiness_detail_payload(parts[1], context=context))
    raise WTPUDashboardNotFound(f"wtpu_dashboard_route_missing:{path}")


def _dashboard_route_html(query: Mapping[str, list[str]], context: _ProjectionContext) -> str:
    payload = dashboard_payload(context=context, query=query)
    issues_payload_data = issues_payload(context=context, query=query)
    essays_payload_data = essays_payload(context=context, query=query)
    return _dashboard_html(
        dashboard=payload,
        sections=sections_payload(context=context)["sections"],
        issues=issues_payload_data["issues"],
        essays=essays_payload_data["essays"],
        source_packets=_source_packet_rows(context.projection),
        corrections=correction_chains_payload(context=context)["correction_chains"],
        archive_readiness=archive_readiness_payload(context=context)["archive_readiness"],
        active_filters=payload.get("active_filters") or {},
        projection=context.projection,
        error="",
    )


def _section_detail_html(payload: Mapping[str, Any]) -> str:
    section = payload.get("section") or {}
    title = f"Section: {section.get('display_name') or section.get('section_id') or ''}"
    body = (
        _standard_notice()
        + "<section class=\"panel\">"
        + f"<h2>{escape(title)}</h2>"
        + f"<p><code>{escape(str(section.get('section_id') or ''))}</code></p>"
        + f"<p class=\"muted\">{escape(str(section.get('description') or ''))}</p>"
        + f"<p>Issues: <strong>{escape(str(payload.get('count') or 0))}</strong></p>"
        + "</section>"
        + "<section class=\"panel\"><h2>Related Issues</h2>"
        + _issues_table(list(payload.get("issues") or []))
        + "</section>"
    )
    return _page_shell(title, body)


def _issue_detail_html(payload: Mapping[str, Any]) -> str:
    issue = payload.get("issue") or {}
    archive = payload.get("archive_readiness_detail") or {}
    body = (
        _standard_notice(include_release_status=True)
        + "<section class=\"panel\">"
        + f"<h2>{escape(str(issue.get('title') or 'Issue Detail'))}</h2>"
        + _kv_table(
            [
                ("Issue", _local_link(_local_path("issues", issue.get("issue_id")), str(issue.get("issue_id") or ""))),
                ("Section", _local_link(_local_path("sections", issue.get("section_id")), str(issue.get("section_id") or ""))),
                ("Jurisdiction", str(issue.get("jurisdiction") or "")),
                ("Scope", str(issue.get("scope") or "")),
                ("Issue Status", str(issue.get("status") or "")),
                ("Archive Status", str(issue.get("archive_status") or "")),
                ("Topic Tags", _badges(issue.get("topic_tags") or [], empty="none")),
            ]
        )
        + "</section>"
        + "<section class=\"panel\"><h2>Linked Essays</h2>"
        + _essays_table(list(payload.get("essays") or []))
        + "</section>"
        + "<section class=\"panel\"><h2>Linked Source Packets</h2>"
        + _source_packets_table(list(payload.get("source_packets") or []))
        + "</section>"
        + "<section class=\"panel\"><h2>Campaign Lineage</h2>"
        + "<p class=\"muted\">Campaign links are descriptive lineage only and transfer no release authority.</p>"
        + _campaign_links_table(list(payload.get("campaign_links") or []))
        + "</section>"
        + "<section class=\"panel\"><h2>Related Corrections</h2>"
        + _corrections_table(list(payload.get("correction_chains") or []))
        + "</section>"
        + "<section class=\"panel\"><h2>Archive-Readiness Blockers</h2>"
        + _archive_detail_block(archive)
        + "</section>"
    )
    return _page_shell(str(issue.get("title") or "Issue Detail"), body)


def _essay_detail_html(payload: Mapping[str, Any]) -> str:
    essay = payload.get("essay") or {}
    issue = payload.get("issue") or {}
    body = (
        _standard_notice(include_release_status=True)
        + "<section class=\"panel\">"
        + f"<h2>{escape(str(essay.get('title') or 'Essay Detail'))}</h2>"
        + _kv_table(
            [
                ("Essay", _local_link(_local_path("essays", essay.get("essay_id")), str(essay.get("essay_id") or ""))),
                ("Issue", _local_link(_local_path("issues", issue.get("issue_id")), str(issue.get("issue_id") or ""))),
                ("Lifecycle Status", str(essay.get("status") or "")),
                ("Content Hash", f"<code>{escape(str(essay.get('content_hash') or ''))}</code>"),
                ("Reviewed/Approved Hash Status", str(essay.get("reviewer_hash_status") or "")),
                ("Reviewer Reference", str(essay.get("reviewer_ref") or "")),
            ]
        )
        + "</section>"
        + "<section class=\"panel\"><h2>Evidence Summary</h2>"
        + f"<p>{escape(str(essay.get('evidence_summary') or ''))}</p>"
        + "</section>"
        + "<section class=\"panel\"><h2>Interpretation Summary</h2>"
        + f"<p>{escape(str(essay.get('interpretation_summary') or ''))}</p>"
        + "</section>"
        + "<section class=\"panel\"><h2>Claim Index</h2>"
        + _claims_table(list(essay.get("claim_index") or []))
        + "</section>"
        + "<section class=\"panel\"><h2>Linked Source Packets</h2>"
        + _source_packets_table(list(payload.get("source_packets") or []))
        + "</section>"
        + "<section class=\"panel\"><h2>Correction Chain</h2>"
        + _corrections_table([payload.get("correction_chain") or {}])
        + "</section>"
        + "<section class=\"panel\"><h2>Historical Versions</h2>"
        + _essay_history_table(list(payload.get("history") or []))
        + "</section>"
    )
    return _page_shell(str(essay.get("title") or "Essay Detail"), body)


def _source_packet_detail_html(payload: Mapping[str, Any]) -> str:
    packet = payload.get("source_packet") or {}
    body = (
        _standard_notice()
        + "<section class=\"panel\">"
        + f"<h2>{escape(str(packet.get('title') or 'Source Packet Detail'))}</h2>"
        + _kv_table(
            [
                ("Source Packet", f"<code>{escape(str(packet.get('source_packet_id') or ''))}</code>"),
                ("Content Hash", f"<code>{escape(str(packet.get('content_hash') or ''))}</code>"),
                ("Status", str(packet.get("status") or "")),
                ("Created By", str(packet.get("created_by") or "")),
                ("Provenance Note", str(packet.get("provenance_note") or "")),
                ("Limitations", _badges(packet.get("source_limitations") or [], empty="none")),
            ]
        )
        + "</section>"
        + "<section class=\"panel\"><h2>Source References</h2>"
        + _source_refs_table(list(packet.get("source_refs") or []))
        + "</section>"
        + "<section class=\"panel\"><h2>Linked Essays</h2>"
        + _essays_table(list(payload.get("linked_essays") or []))
        + "</section>"
        + "<section class=\"panel\"><h2>Linked Claims</h2>"
        + _claims_table(list(payload.get("linked_claims") or []))
        + "</section>"
    )
    return _page_shell(str(packet.get("title") or "Source Packet Detail"), body)


def _correction_chain_detail_html(payload: Mapping[str, Any]) -> str:
    chain = payload.get("correction_chain") or {}
    body = (
        _standard_notice()
        + "<section class=\"panel\">"
        + "<h2>Correction Chain</h2>"
        + _kv_table(
            [
                ("Target Type", str(payload.get("target_type") or "")),
                ("Target ID", f"<code>{escape(str(payload.get('target_id') or ''))}</code>"),
                ("History", str(payload.get("preservation_notice") or "")),
            ]
        )
        + "</section>"
        + "<section class=\"panel\"><h2>Chronology</h2>"
        + _corrections_table([chain])
        + "</section>"
    )
    return _page_shell("Correction Chain", body)


def _archive_readiness_detail_html(payload: Mapping[str, Any]) -> str:
    issue = payload.get("issue") or {}
    readiness = payload.get("archive_readiness") or {}
    body = (
        _standard_notice(include_release_status=True)
        + "<section class=\"panel\">"
        + "<h2>Archive Readiness</h2>"
        + _kv_table(
            [
                ("Issue", _local_link(_local_path("issues", issue.get("issue_id")), str(issue.get("issue_id") or ""))),
                ("Issue Title", str(issue.get("title") or "")),
                ("Jurisdiction", str(issue.get("jurisdiction") or "")),
                ("Scope", str(issue.get("scope") or "")),
                ("Archive Ready", _yes_no(bool(readiness.get("archive_ready")))),
                ("Meaning", "Archive readiness is internal record quality only. It is not website or public archive publication."),
            ]
        )
        + "</section>"
        + "<section class=\"panel\"><h2>Blocker Detail</h2>"
        + _archive_detail_block(readiness)
        + "</section>"
    )
    return _page_shell("Archive Readiness", body)


def _error_page(error: str) -> str:
    return _page_shell("WTPU Dashboard Error", _standard_notice() + _error_html(error))


def _page_shell(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)} - WTPU Read-Only Publication Dashboard</title>
  {_dashboard_style()}
</head>
<body>
  <header>
    <h1>{escape(title)}</h1>
    <p class="muted">Projection-derived local operator view for <code>{escape(WTPU_BRAND_ID)}</code>. {_local_link("/wtpu-publication", "Dashboard home")}</p>
  </header>
  <main>
    {body}
  </main>
</body>
</html>
"""


def _standard_notice(*, include_release_status: bool = False) -> str:
    release_status = " Editorial status is not release status." if include_release_status else ""
    return (
        '<section class="banner">'
        f"<strong>Internal only.</strong> {escape(WTPU_DASHBOARD_DISCLOSURES['internal_only'])}"
        f"{escape(release_status)}"
        "</section>"
    )


def _local_path(*parts: object) -> str:
    if not parts:
        return "/wtpu-publication"
    clean = [quote(str(part or "").strip(), safe="._-") for part in parts if str(part or "").strip()]
    return "/wtpu-publication/" + "/".join(clean)


def _local_query_path(params: Mapping[str, str]) -> str:
    clean = {key: value for key, value in params.items() if value}
    return "/wtpu-publication" + (f"?{urlencode(clean)}" if clean else "")


def _local_link(path: str, label: str) -> str:
    if not str(path).startswith("/wtpu-publication"):
        return escape(label)
    return f'<a href="{escape(str(path), quote=True)}">{escape(label)}</a>'


def _links_html(links: Iterable[Mapping[str, str]]) -> str:
    rendered = [
        _local_link(str(link.get("href") or ""), str(link.get("label") or link.get("href") or "detail"))
        for link in links
        if str(link.get("href") or "").startswith("/wtpu-publication")
    ]
    return " ".join(rendered) if rendered else '<span class="muted">none</span>'


def _filters_html(active_filters: Mapping[str, str], projection: WTPUPublicationProjection) -> str:
    issue_statuses = sorted({issue.status for issue in projection.issues.values() if str(issue.status).strip()})
    jurisdictions = sorted({issue.jurisdiction for issue in projection.issues.values() if str(issue.jurisdiction).strip()})
    scopes = sorted({issue.scope for issue in projection.issues.values() if str(issue.scope).strip()})
    rows = [
        ("Section", [""] + list(EDITORIAL_SECTIONS), "section"),
        ("Essay Lifecycle", [""] + list(ESSAY_LIFECYCLE), "essay_status"),
        ("Issue Status", [""] + issue_statuses, "issue_status"),
        ("Jurisdiction", [""] + jurisdictions, "jurisdiction"),
        ("Scope", [""] + scopes, "scope"),
    ]
    groups = []
    for label, values, key in rows:
        links = []
        for value in values:
            params = {item_key: item_value for item_key, item_value in active_filters.items() if item_value}
            if value:
                params[key] = value
                link_label = value
            else:
                params.pop(key, None)
                link_label = "all"
            css = "badge good" if str(active_filters.get(key) or "") == str(value or "") else "badge"
            links.append(f'<span class="{css}">{_local_link(_local_query_path(params), link_label)}</span>')
        groups.append(f"<div><strong>{escape(label)}</strong> {' '.join(links)}</div>")
    active = _badges([f"{key}={value}" for key, value in active_filters.items() if value], empty="none")
    return (
        '<section class="panel">'
        "<h2>Read-Only Filters</h2>"
        f"<p class=\"muted\">Active filters: {active}</p>"
        + "".join(groups)
        + "</section>"
    )


def _kv_table(rows: Iterable[Tuple[str, str]]) -> str:
    body = "".join(
        "<tr>"
        f"<th>{escape(str(label))}</th>"
        f"<td>{value}</td>"
        "</tr>"
        for label, value in rows
    )
    return f"<table><tbody>{body}</tbody></table>"


def _dashboard_style() -> str:
    return """<style>
    :root {
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
    }
    * { box-sizing: border-box; }
    body { margin: 0; background: var(--bg); color: var(--ink); font-size: 14px; line-height: 1.45; }
    header { padding: 18px 22px; border-bottom: 1px solid var(--line); background: var(--panel); }
    main { display: grid; gap: 16px; padding: 18px 22px 28px; }
    h1, h2, h3, p { margin: 0; }
    h1 { font-size: 22px; }
    h2 { font-size: 16px; margin-bottom: 10px; }
    h3 { font-size: 14px; margin-bottom: 6px; }
    a { color: var(--blue); text-decoration: none; }
    a:hover { text-decoration: underline; }
    .banner { border: 1px solid var(--blue); background: var(--blue-bg); color: var(--ink); padding: 12px; border-radius: 8px; }
    .warning { border: 1px solid var(--amber); background: var(--amber-bg); color: var(--ink); padding: 10px; border-radius: 8px; }
    .error { border: 1px solid var(--red); background: var(--red-bg); color: var(--ink); padding: 10px; border-radius: 8px; }
    .panel { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 14px; overflow-x: auto; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; }
    .metric { background: var(--soft); border: 1px solid var(--line); border-radius: 8px; padding: 10px; }
    .metric strong { display: block; font-size: 20px; }
    table { width: 100%; border-collapse: collapse; min-width: 720px; }
    th, td { text-align: left; vertical-align: top; padding: 8px; border-bottom: 1px solid var(--line); }
    th { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0; }
    .muted { color: var(--muted); }
    .badge { display: inline-block; border-radius: 999px; padding: 2px 8px; background: var(--soft); border: 1px solid var(--line); margin: 1px; }
    .badge.good { color: var(--green); background: var(--green-bg); border-color: #c8e5d3; }
    .badge.warn { color: var(--amber); background: var(--amber-bg); border-color: #e8d38d; }
    .badge.bad { color: var(--red); background: var(--red-bg); border-color: #edc4bd; }
    code { background: var(--soft); border: 1px solid var(--line); border-radius: 6px; padding: 1px 4px; }
    .plain { word-break: break-word; }
  </style>"""


def _dashboard_html(
    *,
    dashboard: Mapping[str, Any],
    sections: List[Mapping[str, Any]],
    issues: List[Mapping[str, Any]],
    essays: List[Mapping[str, Any]],
    source_packets: List[Mapping[str, Any]],
    corrections: List[Mapping[str, Any]],
    archive_readiness: List[Mapping[str, Any]],
    active_filters: Mapping[str, str],
    projection: WTPUPublicationProjection,
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
  {_dashboard_style()}
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
    {_filters_html(active_filters, projection)}
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
        f"<td>{_local_link(_local_path('sections', row.get('section_id')), str(row.get('section_id') or ''))}</td>"
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
        f"<td>{_local_link(_local_path('issues', row.get('issue_id')), str(row.get('issue_id') or ''))}</td>"
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
        f"<td>{_local_link(_local_path('essays', row.get('essay_id')), str(row.get('essay_id') or ''))}</td>"
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
            f"<td>{_local_link(_local_path('source-packets', packet.get('source_packet_id')), str(packet.get('source_packet_id') or ''))}</td>"
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
                    f"<td>{_local_link(_local_path('corrections', record.get('target_type'), target_id), target_id)}</td>"
                    f"<td><code>{escape(target_hash)}</code></td>"
                    f"<td><code>{escape(str(record.get('correction_id') or ''))}</code></td>"
                    f"<td>{escape(str(record.get('type_label') or record.get('correction_type') or ''))}</td>"
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
        f"<td>{_local_link(_local_path('archive-readiness', row.get('issue_id')), str(row.get('issue_id') or ''))}</td>"
        f"<td>{escape(str(row.get('issue_title') or ''))}</td>"
        f"<td>{_yes_no(bool(row.get('archive_ready')))}</td>"
        f"<td>{_badges(row.get('blockers') or [], empty='none')}</td>"
        "</tr>"
        for row in rows_payload
    )
    return f"<table><thead><tr><th>Issue</th><th>Title</th><th>Archive Ready</th><th>Blockers</th></tr></thead><tbody>{rows}</tbody></table>"


def _campaign_links_table(campaign_links: List[Mapping[str, Any]]) -> str:
    if not campaign_links:
        return '<p class="muted">No campaign lineage records.</p>'
    rows = "".join(
        "<tr>"
        f"<td><code>{escape(str(row.get('campaign_link_id') or ''))}</code></td>"
        f"<td>{escape(str(row.get('campaign_system') or ''))}</td>"
        f"<td><code>{escape(str(row.get('campaign_id') or ''))}</code></td>"
        f"<td><code>{escape(str(row.get('campaign_hash') or ''))}</code></td>"
        f"<td>{escape(str(row.get('relationship_type') or ''))}</td>"
        "</tr>"
        for row in campaign_links
    )
    return f"<table><thead><tr><th>Link</th><th>System</th><th>Campaign</th><th>Hash</th><th>Relationship</th></tr></thead><tbody>{rows}</tbody></table>"


def _claims_table(claims: List[Mapping[str, Any]]) -> str:
    if not claims:
        return '<p class="muted">No claim records.</p>'
    rows = "".join(
        "<tr>"
        f"<td><code>{escape(str(row.get('claim_id') or ''))}</code></td>"
        f"<td>{escape(str(row.get('claim_type') or ''))}</td>"
        f"<td>{escape(str(row.get('text') or ''))}</td>"
        f"<td>{_badges(row.get('source_refs') or [], empty='none')}</td>"
        f"<td>{escape(str(row.get('evidence_confidence') or ''))}</td>"
        f"<td>{escape(str(row.get('interpretation_status') or ''))}</td>"
        f"<td><code>{escape(str(row.get('claim_hash') or ''))}</code></td>"
        "</tr>"
        for row in claims
    )
    return f"<table><thead><tr><th>Claim</th><th>Type</th><th>Text</th><th>Source Refs</th><th>Evidence</th><th>Interpretation</th><th>Hash</th></tr></thead><tbody>{rows}</tbody></table>"


def _source_refs_table(refs: List[Mapping[str, Any]]) -> str:
    if not refs:
        return '<p class="muted">No source references.</p>'
    rows = "".join(
        "<tr>"
        f"<td><code>{escape(str(row.get('source_ref_id') or ''))}</code></td>"
        f"<td>{escape(str(row.get('source_type') or ''))}</td>"
        f"<td><span class=\"plain\">{escape(str(row.get('locator') or ''))}</span></td>"
        f"<td><code>{escape(str(row.get('source_content_hash') or ''))}</code></td>"
        f"<td>{escape(str(row.get('retrieved_at') or ''))}</td>"
        f"<td>{escape(str(row.get('accessed_by') or ''))}</td>"
        f"<td>{escape(str(row.get('provenance_note') or ''))}</td>"
        "</tr>"
        for row in refs
    )
    return f"<table><thead><tr><th>Source Ref</th><th>Type</th><th>Plain Text Locator</th><th>Content Hash</th><th>Retrieved</th><th>Accessed By</th><th>Provenance</th></tr></thead><tbody>{rows}</tbody></table>"


def _essay_history_table(versions: List[Mapping[str, Any]]) -> str:
    if not versions:
        return '<p class="muted">No historical versions.</p>'
    rows = "".join(
        "<tr>"
        f"<td>{escape(str(row.get('version') or ''))}</td>"
        f"<td>{escape(str(row.get('status') or ''))}</td>"
        f"<td><code>{escape(str(row.get('content_hash') or ''))}</code></td>"
        f"<td>{escape(str(row.get('updated_at') or row.get('created_at') or ''))}</td>"
        "</tr>"
        for row in versions
    )
    return f"<table><thead><tr><th>Version</th><th>Status</th><th>Content Hash</th><th>Recorded</th></tr></thead><tbody>{rows}</tbody></table>"


def _archive_detail_block(readiness: Mapping[str, Any]) -> str:
    blockers = list(readiness.get("blockers") or [])
    if not blockers:
        return '<p><span class="badge good">ready</span> No current archive-readiness blockers.</p>'
    details = readiness.get("blocker_details") or []
    rows = "".join(
        "<tr>"
        f"<td>{escape(str(row.get('blocker') or ''))}</td>"
        f"<td>{_links_html(row.get('local_links') or [])}</td>"
        "</tr>"
        for row in details
        if isinstance(row, Mapping)
    )
    if not rows:
        rows = "".join(f"<tr><td>{escape(str(blocker))}</td><td><span class=\"muted\">none</span></td></tr>" for blocker in blockers)
    return (
        '<p class="muted">Blockers describe internal record quality only; they do not control public publication.</p>'
        f"<table><thead><tr><th>Blocker</th><th>Local Detail</th></tr></thead><tbody>{rows}</tbody></table>"
    )


def _badges(values: Iterable[Any], *, empty: str = "") -> str:
    clean = [str(value) for value in values if str(value or "").strip()]
    if not clean and empty:
        return f'<span class="badge good">{escape(empty)}</span>'
    return " ".join(f'<span class="badge">{escape(value)}</span>' for value in clean)


def _yes_no(value: bool) -> str:
    return '<span class="badge good">yes</span>' if value else '<span class="badge warn">no</span>'
