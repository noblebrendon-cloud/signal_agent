from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.hq.governance import resolve_lane_for_spine
from signal_agent.content.lineage_status import load_content_lifecycle_view

from .capture_routing_status import (
    _event_timestamp,
    _format_timestamp,
    _load_active_lanes,
    _load_configured_destinations,
    _load_jsonl,
    _load_reserved_spines,
    _load_yaml,
)
from .registry import normalize_text
from .routing_queue_backlog import (
    STALE_QUEUE_HOURS,
    _clean_target,
    _destination_operational_status,
    _format_age_hours,
    _promotion_destination,
    collect_routing_queue_backlog,
)


QUEUE_ITEM_LIMIT = 10
ROUTE_ITEM_LIMIT = 5


def collect_routing_lineage_drilldown(
    repo_root: Path,
    *,
    target: str | None,
    target_kind: str | None = None,
    now: datetime | None = None,
    stale_queue_hours: int = STALE_QUEUE_HOURS,
    queue_item_limit: int = QUEUE_ITEM_LIMIT,
    route_item_limit: int = ROUTE_ITEM_LIMIT,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    now_utc = now.astimezone(timezone.utc) if now else datetime.now(timezone.utc)

    if not target:
        return {
            "mode": "unresolved",
            "requested_target": None,
            "resolved_target": None,
            "condition_labels": [],
            "relevant_files": [],
            "notes": ("The drill-down workflow requires a bundle or destination target.",),
        }

    effective_kind = _effective_target_kind(target, target_kind)
    if effective_kind == "bundle":
        return _collect_bundle_drilldown(
            repo_root,
            target=target,
            now=now_utc,
            stale_queue_hours=stale_queue_hours,
            route_item_limit=route_item_limit,
        )

    return _collect_destination_drilldown(
        repo_root,
        target=target,
        target_kind=target_kind,
        now=now_utc,
        stale_queue_hours=stale_queue_hours,
        queue_item_limit=queue_item_limit,
    )


def build_routing_lineage_drilldown_tool_result(
    repo_root: Path,
    *,
    target: str | None,
    target_kind: str | None = None,
) -> dict[str, Any]:
    drilldown = collect_routing_lineage_drilldown(
        repo_root,
        target=target,
        target_kind=target_kind,
    )
    summary = _build_summary(drilldown)
    highlights = list(_build_highlights(drilldown))

    return {
        "status": "ok",
        "summary": summary,
        "highlights": tuple(highlights),
        "authority_paths": tuple(drilldown.get("relevant_files", ())),
        "notes": tuple(drilldown.get("notes", ())),
        "details": drilldown,
    }


def _collect_bundle_drilldown(
    repo_root: Path,
    *,
    target: str,
    now: datetime,
    stale_queue_hours: int,
    route_item_limit: int,
) -> dict[str, Any]:
    promotion_log_path = repo_root / "data" / "capture" / "promotion_log.jsonl"
    routing_log_path = repo_root / "data" / "capture" / "routing_log.jsonl"
    spine_router_path = repo_root / "config" / "spine_router.yaml"
    lanes_path = repo_root / "config" / "lanes.yaml"
    spines_root = repo_root / "constraints" / "spines"

    bundle_filename = _resolve_bundle_filename(target)
    promotion_events = _load_jsonl(promotion_log_path)
    routing_events = _load_jsonl(routing_log_path)
    configured_destinations = _load_configured_destinations(spine_router_path)
    lanes_doc = _load_yaml(lanes_path)
    active_lanes = _load_active_lanes(lanes_doc)
    reserved_spines = _load_reserved_spines(lanes_doc)

    promotion_records = sorted(
        [event for event in promotion_events if _bundle_matches(event.get("bundle_filename"), bundle_filename)],
        key=lambda row: _event_timestamp(row) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    routing_records = sorted(
        [event for event in routing_events if _bundle_matches(event.get("bundle_filename"), bundle_filename)],
        key=lambda row: _event_timestamp(row) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    successful_routes = [
        record for record in routing_records if str(record.get("status") or "").strip().lower() == "ok"
    ]
    queue_copies = _find_queue_copies(spines_root, repo_root, bundle_filename, now)
    queue_destinations = sorted({copy["destination"] for copy in queue_copies})
    candidate_destinations = _candidate_destinations_for_bundle(
        promotion_records=promotion_records,
        routing_records=routing_records,
        queue_copies=queue_copies,
    )

    resolved_destination, destination_source = _resolve_bundle_destination(
        promotion_records=promotion_records,
        routing_records=routing_records,
        queue_copies=queue_copies,
    )
    resolved_lane = resolve_lane_for_spine(resolved_destination) if resolved_destination else None
    downstream = _resolve_bundle_downstream_lineage(
        repo_root,
        bundle_filename=bundle_filename,
        candidate_destinations=candidate_destinations,
    )

    downstream_present = bool(downstream["downstream_evidence_present"])
    primary_queue = queue_copies[0] if queue_copies else None
    queue_exists = bool(queue_copies)
    queue_age_hours = primary_queue["age_hours"] if primary_queue else None
    stale_queue = bool(queue_exists and queue_age_hours is not None and queue_age_hours >= stale_queue_hours and not downstream_present)

    condition_labels: list[str] = []
    if successful_routes:
        condition_labels.append("routed")
    if len(queue_copies) > 1 or len(successful_routes) > 1:
        condition_labels.append("duplicated")
    if queue_exists and not promotion_records and not routing_records:
        condition_labels.append("orphaned")
    if queue_exists and not downstream_present:
        condition_labels.append("waiting")
        condition_labels.append("missing_downstream_evidence")
        if stale_queue:
            condition_labels.append("stale")

    notes = []
    if not promotion_records and not routing_records and not queue_copies and not downstream["lineage_found"]:
        notes.append("No matching promotion, routing, queue, or downstream lineage evidence was found for the requested bundle.")
    if resolved_destination and destination_source:
        notes.append(f"Destination resolved from {destination_source}: {resolved_destination}.")
    if downstream["lineage_found"]:
        if downstream_present:
            notes.append(
                "Downstream evidence is available through the content lineage view "
                f"({downstream['downstream_evidence_quality']})."
            )
        else:
            notes.append("No downstream artifact or package evidence was found in the content lineage view.")
        if downstream["integrity_flags"]:
            notes.append(
                "Downstream lineage integrity flags: " + ", ".join(downstream["integrity_flags"]) + "."
            )
    notes.append(
        "Downstream content lineage still consults legacy data/artifact_registry.jsonl as a content catalog, not as artifact-state authority."
    )

    relevant_files = [
        "data/capture/promotion_log.jsonl",
        "data/capture/routing_log.jsonl",
        "config/spine_router.yaml",
        "config/lanes.yaml",
        "constraints/spines/",
        "data/intake/intake.jsonl",
        "data/artifact_registry.jsonl",
        "artifacts/videos/video_package_registry.jsonl",
        "signal_agent/content/lineage_status.py",
        "app/hq/capture/promote.py",
        "app/hq/capture/router.py",
        "app/hq/governance/transition_gate.py",
    ]
    relevant_files.extend(copy["queue_path"] for copy in queue_copies)

    return {
        "mode": "bundle",
        "requested_target": target,
        "resolved_target": bundle_filename,
        "target_kind": "bundle",
        "bundle_filename": bundle_filename,
        "queue_exists": queue_exists,
        "queue_copy_count": len(queue_copies),
        "queue_path": primary_queue["queue_path"] if primary_queue else None,
        "queue_paths": [copy["queue_path"] for copy in queue_copies],
        "queue_destinations": queue_destinations,
        "queue_age_hours": queue_age_hours,
        "queue_age_display": _format_age_hours(queue_age_hours),
        "promotion_record_count": len(promotion_records),
        "promotion_records": [_promotion_record_view(record) for record in promotion_records[:route_item_limit]],
        "routing_record_count": len(routing_records),
        "routing_records": [_routing_record_view(record) for record in routing_records[:route_item_limit]],
        "successful_routing_count": len(successful_routes),
        "resolved_destination": resolved_destination,
        "resolved_destination_source": destination_source,
        "resolved_lane": resolved_lane,
        "configured_destination": bool(resolved_destination and resolved_destination in configured_destinations),
        "reserved_destination": bool(resolved_destination and resolved_destination in reserved_spines),
        "operational_status": (
            _destination_operational_status(
                destination=resolved_destination,
                configured_destinations=configured_destinations,
                active_lanes=active_lanes,
                reserved_spines=reserved_spines,
                incoming_exists=queue_exists,
            )
            if resolved_destination
            else None
        ),
        "downstream_evidence_present": downstream_present,
        "downstream_evidence_quality": downstream["downstream_evidence_quality"],
        "downstream_stage": downstream["current_stage"],
        "downstream_integrity_flags": downstream["integrity_flags"],
        "downstream_lineage": downstream["lineage"],
        "condition_labels": _ordered_unique(condition_labels),
        "relevant_files": list(dict.fromkeys(path for path in relevant_files if path)),
        "notes": tuple(notes),
    }


def _collect_destination_drilldown(
    repo_root: Path,
    *,
    target: str,
    target_kind: str | None,
    now: datetime,
    stale_queue_hours: int,
    queue_item_limit: int,
) -> dict[str, Any]:
    backlog = collect_routing_queue_backlog(
        repo_root,
        target=target,
        target_kind=target_kind,
        now=now,
        stale_queue_hours=stale_queue_hours,
        recent_file_limit=queue_item_limit,
    )
    repo_root = repo_root.resolve()
    spines_root = repo_root / "constraints" / "spines"

    destination_details: list[dict[str, Any]] = []
    condition_labels: list[str] = []
    notes = list(backlog.get("notes", ()))
    relevant_files = list(backlog.get("relevant_files", ()))

    for detail in backlog.get("destination_details", []):
        queue_items = _list_queue_items(
            spines_root / detail["destination"] / "incoming",
            repo_root=repo_root,
            now=now,
            limit=queue_item_limit,
        )
        detail_labels: list[str] = []
        if detail["operational_status"] == "reserved":
            detail_labels.append("reserved_inactive_destination")
        if detail["configured"] and not detail["observed"]:
            detail_labels.append("configured_but_unobserved")
        if detail["stale_queue_bundle_count"]:
            detail_labels.append("stale")
        destination_details.append(
            {
                **detail,
                "queued_items": queue_items["queued_items"],
                "newest_queue_file": queue_items["newest_queue_file"],
                "oldest_queue_file": queue_items["oldest_queue_file"],
                "condition_labels": detail_labels,
            }
        )
        condition_labels.extend(detail_labels)
        if queue_items["consulted_path"]:
            relevant_files.append(queue_items["consulted_path"])

    if backlog["scope_kind"] == "unresolved":
        notes.append("No destination or lane target in the current repo resolved from the request.")
    elif backlog["scope_kind"] == "lane":
        notes.append(
            f"Lane target {backlog['resolved_target']} resolves to {len(backlog['resolved_destinations'])} routing destination(s)."
        )

    return {
        "mode": "destination",
        "requested_target": target,
        "resolved_target": backlog.get("resolved_target"),
        "target_kind": target_kind or backlog.get("scope_kind"),
        "scope_kind": backlog.get("scope_kind"),
        "resolved_destinations": backlog.get("resolved_destinations", []),
        "destination_details": destination_details,
        "condition_labels": _ordered_unique(condition_labels),
        "relevant_files": list(dict.fromkeys(path for path in relevant_files if path)),
        "notes": tuple(notes),
    }


def _build_summary(drilldown: dict[str, Any]) -> str:
    if drilldown["mode"] == "bundle":
        condition = ", ".join(drilldown["condition_labels"]) or "no_condition"
        queue_status = "yes" if drilldown["queue_exists"] else "no"
        downstream_status = "present" if drilldown["downstream_evidence_present"] else "absent"
        return (
            "Bundle drill-down reconstructed from promotion, routing, queue, and downstream lineage evidence. "
            f"Bundle: {drilldown['bundle_filename']}. "
            f"Queue exists: {queue_status}. "
            f"Destination: {drilldown['resolved_destination'] or 'unresolved'}. "
            f"Downstream evidence: {downstream_status}. "
            f"Condition labels: {condition}."
        )

    if drilldown["mode"] == "destination":
        queue_count = sum(int(detail["queue_bundle_count"]) for detail in drilldown["destination_details"])
        stale_count = sum(int(detail["stale_queue_bundle_count"]) for detail in drilldown["destination_details"])
        condition = ", ".join(drilldown["condition_labels"]) or "no_condition"
        return (
            "Destination drill-down reconstructed from routing ledgers and live queue directories. "
            f"Target: {drilldown['resolved_target'] or drilldown['requested_target']}. "
            f"Queue count: {queue_count}. "
            f"Stale queued items: {stale_count}. "
            f"Condition labels: {condition}."
        )

    return "The requested drill-down target could not be resolved."


def _build_highlights(drilldown: dict[str, Any]) -> tuple[str, ...]:
    if drilldown["mode"] == "bundle":
        highlights = [
            "mode=bundle",
            f"target_bundle={drilldown['bundle_filename']}",
            f"queue_exists={'yes' if drilldown['queue_exists'] else 'no'}",
            f"queue_path={drilldown['queue_path'] or 'none'}",
            f"queue_age_hours={drilldown['queue_age_display']}",
            f"promotion_record_count={drilldown['promotion_record_count']}",
            f"routing_record_count={drilldown['routing_record_count']}",
            f"successful_routing_count={drilldown['successful_routing_count']}",
            f"resolved_destination={drilldown['resolved_destination'] or 'none'}",
            f"resolved_lane={drilldown['resolved_lane'] or 'none'}",
            f"downstream_evidence={'present' if drilldown['downstream_evidence_present'] else 'absent'}",
            f"downstream_stage={drilldown['downstream_stage'] or 'none'}",
            "condition_labels=" + (", ".join(drilldown["condition_labels"]) if drilldown["condition_labels"] else "none"),
        ]
        for record in drilldown["promotion_records"]:
            highlights.append(
                "promotion={bundle} spine={spine} status={status}".format(
                    bundle=record["bundle_filename"],
                    spine=record["routed_spine"] or "none",
                    status=record["status"] or "unknown",
                )
            )
        for record in drilldown["routing_records"]:
            highlights.append(
                "route={bundle} spine={spine} status={status}".format(
                    bundle=record["bundle_filename"],
                    spine=record["spine"] or "none",
                    status=record["status"] or "unknown",
                )
            )
        return tuple(highlights)

    if drilldown["mode"] == "destination":
        highlights = [
            "mode=destination",
            f"scope_kind={drilldown['scope_kind']}",
            f"scope_target={drilldown['resolved_target'] or drilldown['requested_target'] or 'none'}",
            "scope_destinations=" + (", ".join(drilldown["resolved_destinations"]) if drilldown["resolved_destinations"] else "none"),
            "condition_labels=" + (", ".join(drilldown["condition_labels"]) if drilldown["condition_labels"] else "none"),
        ]
        for detail in drilldown["destination_details"]:
            highlights.append(
                "destination[{destination}] queue={queue} observed_routes={routes} stale={stale} status={status}".format(
                    destination=detail["destination"],
                    queue=detail["queue_bundle_count"],
                    routes=detail["observed_route_count"],
                    stale=detail["stale_queue_bundle_count"],
                    status=detail["operational_status"],
                )
            )
            if detail["newest_queue_file"]:
                highlights.append(
                    "newest_queue[{destination}]={bundle} age_hours={age}".format(
                        destination=detail["destination"],
                        bundle=detail["newest_queue_file"]["bundle_filename"],
                        age=_format_age_hours(detail["newest_queue_file"]["age_hours"]),
                    )
                )
            if detail["oldest_queue_file"]:
                highlights.append(
                    "oldest_queue[{destination}]={bundle} age_hours={age}".format(
                        destination=detail["destination"],
                        bundle=detail["oldest_queue_file"]["bundle_filename"],
                        age=_format_age_hours(detail["oldest_queue_file"]["age_hours"]),
                    )
                )
            if detail["promoted_without_route_candidates"]:
                highlights.append(
                    "promoted_without_route[{destination}]={bundles}".format(
                        destination=detail["destination"],
                        bundles=", ".join(
                            item["bundle_filename"] for item in detail["promoted_without_route_candidates"]
                        ),
                    )
                )
        return tuple(highlights)

    return ("mode=unresolved",)


def _effective_target_kind(target: str, target_kind: str | None) -> str:
    if target_kind == "bundle":
        return "bundle"
    return "bundle" if _looks_like_bundle_target(target) else "destination"


def _looks_like_bundle_target(target: str | None) -> bool:
    cleaned = normalize_text(str(target or ""))
    return cleaned.startswith("bundle_") and cleaned.endswith(".md")


def _resolve_bundle_filename(target: str) -> str:
    cleaned_target = _clean_target(target)
    raw = cleaned_target.replace("\\", "/").split("/")[-1]
    return raw.strip()


def _bundle_matches(candidate: Any, bundle_filename: str) -> bool:
    return normalize_text(str(candidate or "")) == normalize_text(bundle_filename)


def _find_queue_copies(
    spines_root: Path,
    repo_root: Path,
    bundle_filename: str,
    now: datetime,
) -> list[dict[str, Any]]:
    queue_copies: list[dict[str, Any]] = []
    for incoming_dir in sorted(spines_root.glob("*/incoming")):
        queue_path = incoming_dir / bundle_filename
        if not queue_path.exists():
            continue
        modified_at = datetime.fromtimestamp(queue_path.stat().st_mtime, tz=timezone.utc)
        queue_copies.append(
            {
                "destination": incoming_dir.parent.name,
                "queue_path": str(queue_path.relative_to(repo_root)).replace("\\", "/"),
                "modified_at_utc": _format_timestamp(modified_at),
                "age_hours": round((now - modified_at).total_seconds() / 3600, 1),
            }
        )
    queue_copies.sort(key=lambda item: item["age_hours"], reverse=True)
    return queue_copies


def _candidate_destinations_for_bundle(
    *,
    promotion_records: list[dict[str, Any]],
    routing_records: list[dict[str, Any]],
    queue_copies: list[dict[str, Any]],
) -> list[str]:
    candidates = [copy["destination"] for copy in queue_copies]
    candidates.extend(
        str(record.get("spine") or "").strip()
        for record in routing_records
        if str(record.get("spine") or "").strip()
    )
    candidates.extend(
        str(_promotion_destination(record) or "").strip()
        for record in promotion_records
        if str(_promotion_destination(record) or "").strip()
    )
    return list(dict.fromkeys(candidate for candidate in candidates if candidate))


def _resolve_bundle_destination(
    *,
    promotion_records: list[dict[str, Any]],
    routing_records: list[dict[str, Any]],
    queue_copies: list[dict[str, Any]],
) -> tuple[str | None, str | None]:
    if queue_copies:
        return queue_copies[0]["destination"], "queue_path"
    if routing_records:
        return str(routing_records[0].get("spine") or "").strip() or None, "routing_log"
    if promotion_records:
        destination = _promotion_destination(promotion_records[0])
        if destination:
            return destination, "promotion_log"
    return None, None


def _resolve_bundle_downstream_lineage(
    repo_root: Path,
    *,
    bundle_filename: str,
    candidate_destinations: list[str],
) -> dict[str, Any]:
    candidate_spines = list(dict.fromkeys(candidate_destinations or ["content_publishing"]))
    best_lineage: dict[str, Any] | None = None
    best_score = -1

    for spine in candidate_spines:
        view = load_content_lifecycle_view(
            repo_root=repo_root,
            spine=spine,
            bundle_filename=bundle_filename,
            limit=5,
        )
        lineages = view.get("lineages", [])
        if not lineages:
            continue
        lineage = lineages[0]
        score = _lineage_strength(lineage)
        if score > best_score:
            best_score = score
            best_lineage = lineage

    if best_lineage is None:
        return {
            "lineage_found": False,
            "downstream_evidence_present": False,
            "downstream_evidence_quality": "missing",
            "current_stage": None,
            "integrity_flags": [],
            "lineage": None,
        }

    has_any_ref = any(
        int(best_lineage.get(ref_name, {}).get("count") or 0) > 0
        for ref_name in ("source_ref", "intake_ref", "promotion_ref", "route_ref", "artifact_ref", "package_ref")
    )
    if not has_any_ref:
        return {
            "lineage_found": False,
            "downstream_evidence_present": False,
            "downstream_evidence_quality": "missing",
            "current_stage": None,
            "integrity_flags": [],
            "lineage": None,
        }

    artifact_quality = str(best_lineage.get("artifact_ref", {}).get("link_quality") or "missing")
    package_quality = str(best_lineage.get("package_ref", {}).get("link_quality") or "missing")
    downstream_present = artifact_quality in {"exact", "inferred"} or package_quality in {"exact", "inferred"}
    downstream_quality = "exact" if "exact" in {artifact_quality, package_quality} else "inferred" if downstream_present else "missing"
    return {
        "lineage_found": True,
        "downstream_evidence_present": downstream_present,
        "downstream_evidence_quality": downstream_quality,
        "current_stage": best_lineage.get("current_stage"),
        "integrity_flags": list(best_lineage.get("integrity_flags", [])),
        "lineage": best_lineage,
    }


def _lineage_strength(lineage: dict[str, Any]) -> int:
    score = 0
    if str(lineage.get("artifact_ref", {}).get("link_quality")) == "exact":
        score += 4
    if str(lineage.get("package_ref", {}).get("link_quality")) == "exact":
        score += 3
    elif str(lineage.get("package_ref", {}).get("link_quality")) == "inferred":
        score += 2
    if str(lineage.get("route_ref", {}).get("link_quality")) == "exact":
        score += 2
    if str(lineage.get("promotion_ref", {}).get("link_quality")) == "exact":
        score += 1
    return score


def _promotion_record_view(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp_utc": record.get("timestamp_utc"),
        "cluster_id": record.get("cluster_id"),
        "bundle_filename": record.get("bundle_filename"),
        "routed_spine": _promotion_destination(record),
        "status": record.get("status"),
    }


def _routing_record_view(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp_utc": record.get("timestamp_utc"),
        "bundle_filename": record.get("bundle_filename"),
        "spine": record.get("spine"),
        "score": record.get("score"),
        "status": record.get("status"),
    }


def _list_queue_items(
    incoming_dir: Path,
    *,
    repo_root: Path,
    now: datetime,
    limit: int,
) -> dict[str, Any]:
    if not incoming_dir.exists():
        return {
            "queued_items": [],
            "newest_queue_file": None,
            "oldest_queue_file": None,
            "consulted_path": None,
        }

    files = sorted(
        (path for path in incoming_dir.glob("*.md") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    items = []
    for path in files[:limit]:
        modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        items.append(
            {
                "bundle_filename": path.name,
                "queue_path": str(path.relative_to(repo_root)).replace("\\", "/"),
                "modified_at_utc": _format_timestamp(modified_at),
                "age_hours": round((now - modified_at).total_seconds() / 3600, 1),
            }
        )
    newest = items[0] if items else None
    oldest = None
    if files:
        oldest_path = files[-1]
        oldest_modified = datetime.fromtimestamp(oldest_path.stat().st_mtime, tz=timezone.utc)
        oldest = {
            "bundle_filename": oldest_path.name,
            "queue_path": str(oldest_path.relative_to(repo_root)).replace("\\", "/"),
            "modified_at_utc": _format_timestamp(oldest_modified),
            "age_hours": round((now - oldest_modified).total_seconds() / 3600, 1),
        }
    return {
        "queued_items": items,
        "newest_queue_file": newest,
        "oldest_queue_file": oldest,
        "consulted_path": str(incoming_dir.relative_to(repo_root)).replace("\\", "/"),
    }


def _ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered
