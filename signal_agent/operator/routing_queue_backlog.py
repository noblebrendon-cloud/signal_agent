from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.hq.governance import resolve_lane_for_spine

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


STALE_QUEUE_HOURS = 72
RECENT_FILE_LIMIT = 3
PROMOTED_CANDIDATE_LIMIT = 5


def collect_routing_queue_backlog(
    repo_root: Path,
    *,
    target: str | None = None,
    target_kind: str | None = None,
    now: datetime | None = None,
    stale_queue_hours: int = STALE_QUEUE_HOURS,
    recent_file_limit: int = RECENT_FILE_LIMIT,
    promoted_candidate_limit: int = PROMOTED_CANDIDATE_LIMIT,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    now_utc = now.astimezone(timezone.utc) if now else datetime.now(timezone.utc)
    stale_cutoff = now_utc - timedelta(hours=stale_queue_hours)

    promotion_log_path = repo_root / "data" / "capture" / "promotion_log.jsonl"
    routing_log_path = repo_root / "data" / "capture" / "routing_log.jsonl"
    spine_router_path = repo_root / "config" / "spine_router.yaml"
    lanes_path = repo_root / "config" / "lanes.yaml"
    spines_root = repo_root / "constraints" / "spines"

    promotion_events = _load_jsonl(promotion_log_path)
    routing_events = _load_jsonl(routing_log_path)
    configured_destinations = _load_configured_destinations(spine_router_path)
    lanes_doc = _load_yaml(lanes_path)
    active_lanes = _load_active_lanes(lanes_doc)
    reserved_spines = _load_reserved_spines(lanes_doc)
    observed_destinations = sorted(
        {
            str(event.get("spine") or "").strip()
            for event in routing_events
            if str(event.get("spine") or "").strip()
        }
    )
    incoming_destinations = _discover_incoming_destinations(spines_root)
    all_destinations = sorted(
        set(configured_destinations)
        | set(reserved_spines.keys())
        | set(observed_destinations)
        | set(incoming_destinations)
    )
    lane_to_destinations = _group_destinations_by_lane(all_destinations)

    scope = _resolve_scope(
        target=target,
        target_kind=target_kind,
        all_destinations=all_destinations,
        lane_to_destinations=lane_to_destinations,
    )
    scope_destinations = scope["destinations"]

    successful_routed_bundles = _successful_routed_bundles_by_destination(routing_events)
    promoted_candidates = _promoted_without_route_by_destination(
        promotion_events,
        successful_routed_bundles,
    )

    destination_details: list[dict[str, Any]] = []
    consulted_files: list[str] = [
        "data/capture/promotion_log.jsonl",
        "data/capture/routing_log.jsonl",
        "config/spine_router.yaml",
        "config/lanes.yaml",
        "app/hq/capture/promote.py",
        "app/hq/capture/router.py",
    ]

    for destination in scope_destinations:
        lane_id = resolve_lane_for_spine(destination)
        lane_status = active_lanes.get(lane_id)
        reserved_status = reserved_spines.get(destination)
        incoming_dir = spines_root / destination / "incoming"
        queue_status = _inspect_queue_directory(
            incoming_dir,
            repo_root=repo_root,
            now=now_utc,
            stale_cutoff=stale_cutoff,
            recent_file_limit=recent_file_limit,
        )
        if queue_status["incoming_exists"]:
            consulted_files.append(queue_status["incoming_relative_path"])

        routing_rows = _routing_events_for_destination(routing_events, destination)
        latest_route_timestamp = _latest_event_timestamp(routing_rows)
        queue_status_value = _destination_operational_status(
            destination=destination,
            configured_destinations=configured_destinations,
            active_lanes=active_lanes,
            reserved_spines=reserved_spines,
            incoming_exists=queue_status["incoming_exists"],
        )
        destination_promoted_candidates = promoted_candidates.get(destination, [])

        destination_details.append(
            {
                "destination": destination,
                "lane_id": lane_id,
                "lane_status": lane_status or reserved_status,
                "operational_status": queue_status_value,
                "configured": destination in configured_destinations,
                "observed": destination in observed_destinations,
                "observed_route_count": len(routing_rows),
                "latest_route_timestamp": _format_timestamp(latest_route_timestamp),
                "incoming_exists": queue_status["incoming_exists"],
                "incoming_relative_path": queue_status["incoming_relative_path"],
                "queue_bundle_count": queue_status["queue_bundle_count"],
                "newest_queue_files": queue_status["newest_queue_files"],
                "stale_queue_files": queue_status["stale_queue_files"],
                "stale_queue_bundle_count": queue_status["stale_queue_bundle_count"],
                "newest_queue_timestamp": queue_status["newest_queue_timestamp"],
                "oldest_queue_timestamp": queue_status["oldest_queue_timestamp"],
                "oldest_queue_age_hours": queue_status["oldest_queue_age_hours"],
                "promoted_without_route_candidates": destination_promoted_candidates[:promoted_candidate_limit],
                "promoted_without_route_count": len(destination_promoted_candidates),
            }
        )

    unassigned_promoted_candidates = _unassigned_promoted_without_route(
        promotion_events,
        successful_routed_bundles,
        scope_destinations,
    )
    active_operational_destinations = sorted(
        detail["destination"]
        for detail in destination_details
        if detail["operational_status"] in {"active", "partial"}
    )
    reserved_inactive_destinations = sorted(
        detail["destination"]
        for detail in destination_details
        if detail["operational_status"] == "reserved"
    )
    configured_but_unobserved = sorted(
        detail["destination"]
        for detail in destination_details
        if detail["configured"] and not detail["observed"]
    )
    total_queue_bundle_count = sum(int(detail["queue_bundle_count"]) for detail in destination_details)
    total_stale_queue_bundle_count = sum(int(detail["stale_queue_bundle_count"]) for detail in destination_details)
    total_promoted_without_route = sum(int(detail["promoted_without_route_count"]) for detail in destination_details)

    notes = list(scope["notes"])
    if reserved_inactive_destinations:
        notes.append(
            "Reserved or inactive destinations in scope: " + ", ".join(reserved_inactive_destinations) + "."
        )
    if configured_but_unobserved:
        notes.append(
            "Configured but unobserved destinations in scope: " + ", ".join(configured_but_unobserved) + "."
        )
    if total_stale_queue_bundle_count:
        notes.append(
            f"Queue files older than {stale_queue_hours} hours were detected in the selected scope."
        )
    if total_promoted_without_route:
        notes.append(
            "Promoted bundles without a successful routing entry were detected in the selected scope."
        )
    if unassigned_promoted_candidates:
        notes.append(
            "Some promoted-but-unrouted bundles do not declare a target destination in the promotion ledger."
        )

    relevant_files = tuple(dict.fromkeys(path for path in consulted_files if path))
    return {
        "scope_kind": scope["scope_kind"],
        "requested_target": scope["requested_target"],
        "resolved_target": scope["resolved_target"],
        "resolved_destinations": scope_destinations,
        "stale_queue_hours": stale_queue_hours,
        "configured_destinations": configured_destinations,
        "observed_destinations": observed_destinations,
        "active_operational_destinations": active_operational_destinations,
        "reserved_inactive_destinations": reserved_inactive_destinations,
        "configured_but_unobserved_destinations": configured_but_unobserved,
        "total_queue_bundle_count": total_queue_bundle_count,
        "total_stale_queue_bundle_count": total_stale_queue_bundle_count,
        "total_promoted_without_route_count": total_promoted_without_route,
        "unassigned_promoted_without_route": unassigned_promoted_candidates[:promoted_candidate_limit],
        "destination_details": destination_details,
        "relevant_files": list(relevant_files),
        "notes": notes,
    }


def build_routing_queue_backlog_tool_result(
    repo_root: Path,
    *,
    target: str | None = None,
    target_kind: str | None = None,
) -> dict[str, Any]:
    backlog = collect_routing_queue_backlog(
        repo_root,
        target=target,
        target_kind=target_kind,
    )
    scope_label = _scope_label(backlog)
    summary = (
        "Routing queue backlog reconstructed from the routing ledgers, router manifests, and spine incoming directories. "
        f"Scope: {scope_label}. "
        f"Queued bundles: {backlog['total_queue_bundle_count']}. "
        f"Stale queued bundles: {backlog['total_stale_queue_bundle_count']} older than {backlog['stale_queue_hours']} hours. "
        f"Promoted but not yet successfully routed: {backlog['total_promoted_without_route_count']}."
    )

    highlights = [
        f"scope_kind={backlog['scope_kind']}",
        f"scope_target={backlog['resolved_target'] or 'all'}",
        "scope_destinations=" + _join_or_none(backlog["resolved_destinations"]),
        f"total_queue_bundle_count={backlog['total_queue_bundle_count']}",
        f"total_stale_queue_bundle_count={backlog['total_stale_queue_bundle_count']}",
        f"total_promoted_without_route_count={backlog['total_promoted_without_route_count']}",
        "active_operational_destinations=" + _join_or_none(backlog["active_operational_destinations"]),
        "reserved_inactive_destinations=" + _join_or_none(backlog["reserved_inactive_destinations"]),
        "configured_but_unobserved_destinations=" + _join_or_none(backlog["configured_but_unobserved_destinations"]),
    ]
    for detail in backlog["destination_details"]:
        highlights.append(
            "queue[{destination}]={count} stale={stale} status={status} lane={lane}".format(
                destination=detail["destination"],
                count=detail["queue_bundle_count"],
                stale=detail["stale_queue_bundle_count"],
                status=detail["operational_status"],
                lane=detail["lane_id"] or "none",
            )
        )
        if detail["newest_queue_files"]:
            newest = detail["newest_queue_files"][0]
            highlights.append(
                "newest_queue[{destination}]={bundle} age_hours={age}".format(
                    destination=detail["destination"],
                    bundle=newest["bundle_filename"],
                    age=_format_age_hours(newest["age_hours"]),
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
        if detail["stale_queue_files"]:
            highlights.append(
                "stale_queue[{destination}]={bundles}".format(
                    destination=detail["destination"],
                    bundles=", ".join(item["bundle_filename"] for item in detail["stale_queue_files"]),
                )
            )

    if backlog["unassigned_promoted_without_route"]:
        highlights.append(
            "unassigned_promoted_without_route="
            + ", ".join(item["bundle_filename"] for item in backlog["unassigned_promoted_without_route"])
        )

    return {
        "status": "ok",
        "summary": summary,
        "highlights": tuple(highlights),
        "authority_paths": tuple(backlog["relevant_files"]),
        "notes": tuple(backlog["notes"]),
        "details": backlog,
    }


def _resolve_scope(
    *,
    target: str | None,
    target_kind: str | None,
    all_destinations: list[str],
    lane_to_destinations: dict[str, list[str]],
) -> dict[str, Any]:
    if not target:
        return {
            "scope_kind": "global",
            "requested_target": None,
            "resolved_target": None,
            "destinations": all_destinations,
            "notes": (),
        }

    destination_lookup = {normalize_text(item): item for item in all_destinations}
    lane_lookup = {normalize_text(item): item for item in lane_to_destinations}
    cleaned_target = _clean_target(target)
    normalized_target = normalize_text(cleaned_target)

    if target_kind == "destination":
        destination = destination_lookup.get(normalized_target)
        if destination is None:
            return _unresolved_scope(target, "destination")
        return {
            "scope_kind": "destination",
            "requested_target": target,
            "resolved_target": destination,
            "destinations": [destination],
            "notes": (),
        }

    if target_kind == "lane":
        lane_id = lane_lookup.get(normalized_target)
        if lane_id is None:
            return _unresolved_scope(target, "lane")
        return {
            "scope_kind": "lane",
            "requested_target": target,
            "resolved_target": lane_id,
            "destinations": lane_to_destinations[lane_id],
            "notes": (),
        }

    destination = destination_lookup.get(normalized_target)
    if destination is not None:
        return {
            "scope_kind": "destination",
            "requested_target": target,
            "resolved_target": destination,
            "destinations": [destination],
            "notes": (),
        }

    lane_id = lane_lookup.get(normalized_target)
    if lane_id is not None:
        return {
            "scope_kind": "lane",
            "requested_target": target,
            "resolved_target": lane_id,
            "destinations": lane_to_destinations[lane_id],
            "notes": (),
        }

    return _unresolved_scope(target, "destination_or_lane")


def _unresolved_scope(target: str, kind: str) -> dict[str, Any]:
    return {
        "scope_kind": "unresolved",
        "requested_target": target,
        "resolved_target": None,
        "destinations": [],
        "notes": (f"The requested {kind} target could not be resolved from the current routing authority surfaces.",),
    }


def _clean_target(target: str) -> str:
    cleaned = normalize_text(target)
    for prefix in ("lane ", "destination ", "spine "):
        if cleaned.startswith(prefix):
            return cleaned[len(prefix):].strip()
    return cleaned


def _discover_incoming_destinations(spines_root: Path) -> list[str]:
    if not spines_root.exists():
        return []
    destinations: list[str] = []
    for incoming_dir in sorted(spines_root.glob("*/incoming")):
        if incoming_dir.is_dir():
            destinations.append(incoming_dir.parent.name)
    return destinations


def _group_destinations_by_lane(destinations: list[str]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for destination in destinations:
        lane_id = resolve_lane_for_spine(destination)
        if not lane_id:
            continue
        grouped.setdefault(lane_id, []).append(destination)
    for lane_id in grouped:
        grouped[lane_id] = sorted(grouped[lane_id])
    return grouped


def _successful_routed_bundles_by_destination(
    routing_events: list[dict[str, Any]],
) -> dict[str, set[str]]:
    grouped: dict[str, set[str]] = {}
    for event in routing_events:
        if str(event.get("status") or "").strip().lower() != "ok":
            continue
        destination = str(event.get("spine") or "").strip()
        bundle_filename = str(event.get("bundle_filename") or "").strip()
        if not destination or not bundle_filename:
            continue
        grouped.setdefault(destination, set()).add(bundle_filename)
    return grouped


def _promoted_without_route_by_destination(
    promotion_events: list[dict[str, Any]],
    successful_routed_bundles: dict[str, set[str]],
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    seen: set[tuple[str, str]] = set()
    for event in sorted(
        promotion_events,
        key=lambda row: _event_timestamp(row) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    ):
        destination = _promotion_destination(event)
        bundle_filename = str(event.get("bundle_filename") or "").strip()
        if not destination or not bundle_filename:
            continue
        key = (destination, bundle_filename)
        if key in seen:
            continue
        seen.add(key)
        if bundle_filename in successful_routed_bundles.get(destination, set()):
            continue
        grouped.setdefault(destination, []).append(
            {
                "bundle_filename": bundle_filename,
                "timestamp_utc": _format_timestamp(_event_timestamp(event)),
                "status": str(event.get("status") or "").strip() or None,
            }
        )
    return grouped


def _unassigned_promoted_without_route(
    promotion_events: list[dict[str, Any]],
    successful_routed_bundles: dict[str, set[str]],
    scope_destinations: list[str],
) -> list[dict[str, Any]]:
    all_successful = set().union(*successful_routed_bundles.values()) if successful_routed_bundles else set()
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for event in sorted(
        promotion_events,
        key=lambda row: _event_timestamp(row) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    ):
        destination = _promotion_destination(event)
        bundle_filename = str(event.get("bundle_filename") or "").strip()
        if destination or not bundle_filename or bundle_filename in seen:
            continue
        seen.add(bundle_filename)
        if bundle_filename in all_successful:
            continue
        if scope_destinations:
            items.append(
                {
                    "bundle_filename": bundle_filename,
                    "timestamp_utc": _format_timestamp(_event_timestamp(event)),
                    "status": str(event.get("status") or "").strip() or None,
                }
            )
    return items


def _promotion_destination(event: dict[str, Any]) -> str | None:
    for field_name in ("routed_spine", "spine", "destination_spine"):
        value = str(event.get(field_name) or "").strip()
        if value:
            return value
    bundle_contract = event.get("bundle_contract")
    if isinstance(bundle_contract, dict):
        value = str(bundle_contract.get("routed_spine") or bundle_contract.get("destination_spine") or "").strip()
        if value:
            return value
    return None


def _routing_events_for_destination(
    routing_events: list[dict[str, Any]],
    destination: str,
) -> list[dict[str, Any]]:
    rows = [row for row in routing_events if str(row.get("spine") or "").strip() == destination]
    rows.sort(
        key=lambda row: _event_timestamp(row) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return rows


def _latest_event_timestamp(events: list[dict[str, Any]]) -> datetime | None:
    for event in events:
        timestamp = _event_timestamp(event)
        if timestamp is not None:
            return timestamp
    return None


def _inspect_queue_directory(
    incoming_dir: Path,
    *,
    repo_root: Path,
    now: datetime,
    stale_cutoff: datetime,
    recent_file_limit: int,
) -> dict[str, Any]:
    incoming_relative_path = str(incoming_dir.relative_to(repo_root)).replace("\\", "/")
    if not incoming_dir.exists():
        return {
            "incoming_exists": False,
            "incoming_relative_path": incoming_relative_path,
            "queue_bundle_count": 0,
            "newest_queue_files": [],
            "stale_queue_files": [],
            "stale_queue_bundle_count": 0,
            "newest_queue_timestamp": None,
            "oldest_queue_timestamp": None,
            "oldest_queue_age_hours": None,
        }

    files = sorted(
        (path for path in incoming_dir.glob("*.md") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    file_rows = [_queue_file_row(path, now) for path in files]
    stale_rows = [row for row in file_rows if row["modified_at"] is not None and row["modified_at"] < stale_cutoff]
    newest_timestamp = file_rows[0]["modified_at"] if file_rows else None
    oldest_timestamp = file_rows[-1]["modified_at"] if file_rows else None
    return {
        "incoming_exists": True,
        "incoming_relative_path": incoming_relative_path,
        "queue_bundle_count": len(file_rows),
        "newest_queue_files": [_render_queue_row(row) for row in file_rows[:recent_file_limit]],
        "stale_queue_files": [_render_queue_row(row) for row in stale_rows[:recent_file_limit]],
        "stale_queue_bundle_count": len(stale_rows),
        "newest_queue_timestamp": _format_timestamp(newest_timestamp),
        "oldest_queue_timestamp": _format_timestamp(oldest_timestamp),
        "oldest_queue_age_hours": _age_hours(oldest_timestamp, now),
    }


def _queue_file_row(path: Path, now: datetime) -> dict[str, Any]:
    modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return {
        "bundle_filename": path.name,
        "modified_at": modified_at,
        "modified_at_utc": _format_timestamp(modified_at),
        "age_hours": _age_hours(modified_at, now),
    }


def _render_queue_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "bundle_filename": row["bundle_filename"],
        "modified_at_utc": row["modified_at_utc"],
        "age_hours": row["age_hours"],
    }


def _age_hours(timestamp: datetime | None, now: datetime) -> float | None:
    if timestamp is None:
        return None
    age = now - timestamp
    return round(age.total_seconds() / 3600, 1)


def _destination_operational_status(
    *,
    destination: str,
    configured_destinations: list[str],
    active_lanes: dict[str, str],
    reserved_spines: dict[str, str],
    incoming_exists: bool,
) -> str:
    if destination in reserved_spines:
        return "reserved"
    lane_id = resolve_lane_for_spine(destination)
    lane_status = active_lanes.get(lane_id)
    if lane_status in {"active", "partial"}:
        if incoming_exists:
            return lane_status
        return "configured_missing_incoming"
    if destination in configured_destinations:
        return "configured_inactive"
    return "observed_only"


def _scope_label(backlog: dict[str, Any]) -> str:
    if backlog["scope_kind"] == "global":
        return "all routing destinations"
    if backlog["scope_kind"] == "unresolved":
        return f"unresolved target {backlog['requested_target']!r}"
    return f"{backlog['scope_kind']} {backlog['resolved_target']}"


def _join_or_none(values: list[str]) -> str:
    return ", ".join(values) if values else "none"


def _format_age_hours(value: float | None) -> str:
    if value is None:
        return "unknown"
    return f"{value:.1f}"
