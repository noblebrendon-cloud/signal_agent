from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any

import yaml

from app.hq.governance import resolve_lane_for_spine


RECENT_WINDOW_DAYS = 7
STALE_AFTER_DAYS = 7
RECENT_ITEM_LIMIT = 5


def collect_capture_routing_status(
    repo_root: Path,
    *,
    now: datetime | None = None,
    recent_window_days: int = RECENT_WINDOW_DAYS,
    stale_after_days: int = STALE_AFTER_DAYS,
    recent_item_limit: int = RECENT_ITEM_LIMIT,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    now_utc = now.astimezone(timezone.utc) if now else datetime.now(timezone.utc)
    recent_cutoff = now_utc - timedelta(days=recent_window_days)
    stale_cutoff = now_utc - timedelta(days=stale_after_days)

    promotion_log_path = repo_root / "data" / "capture" / "promotion_log.jsonl"
    routing_log_path = repo_root / "data" / "capture" / "routing_log.jsonl"
    spine_router_path = repo_root / "config" / "spine_router.yaml"
    lanes_path = repo_root / "config" / "lanes.yaml"
    spines_root = repo_root / "constraints" / "spines"
    capture_root = repo_root / "data" / "capture"
    raw_root = capture_root / "raw"
    promoted_root = capture_root / "promoted"
    archive_root = capture_root / "archive"

    promotion_events = _load_jsonl(promotion_log_path)
    routing_events = _load_jsonl(routing_log_path)
    configured_destinations = _load_configured_destinations(spine_router_path)
    lane_doc = _load_yaml(lanes_path)
    active_lanes = _load_active_lanes(lane_doc)
    reserved_spines = _load_reserved_spines(lane_doc)

    sorted_promotions = _sorted_events(promotion_events)
    sorted_routes = _sorted_events(routing_events)
    recent_promotions = [event for event in sorted_promotions if _event_timestamp(event) and _event_timestamp(event) >= recent_cutoff]
    recent_routes = [event for event in sorted_routes if _event_timestamp(event) and _event_timestamp(event) >= recent_cutoff]

    observed_destinations = sorted(
        {
            str(event.get("spine")).strip()
            for event in routing_events
            if str(event.get("spine") or "").strip()
        }
    )
    route_events_by_destination = _group_by_destination(routing_events)

    destination_statuses = []
    incoming_authority_paths: list[str] = []
    all_destinations = sorted(set(configured_destinations) | set(observed_destinations) | set(reserved_spines.keys()))
    operational_configured_destinations: list[str] = []
    reserved_configured_destinations: list[str] = []

    for destination in all_destinations:
        lane_id = resolve_lane_for_spine(destination)
        lane_status = active_lanes.get(lane_id)
        reserved_status = reserved_spines.get(destination)
        is_configured = destination in configured_destinations
        is_operational = lane_status in {"active", "partial"}
        is_reserved = reserved_status is not None
        incoming_dir = spines_root / destination / "incoming"
        queue_stats = _queue_stats(incoming_dir)
        if queue_stats["incoming_exists"]:
            incoming_authority_paths.append(str(incoming_dir.relative_to(repo_root)).replace("\\", "/"))
        route_events = route_events_by_destination.get(destination, [])
        latest_route_timestamp = _latest_event_timestamp(route_events)
        if is_configured and is_operational:
            operational_configured_destinations.append(destination)
        if is_configured and is_reserved:
            reserved_configured_destinations.append(destination)
        destination_statuses.append(
            {
                "destination": destination,
                "configured": is_configured,
                "lane_id": lane_id,
                "lane_status": lane_status or reserved_status,
                "observed_route_count": len(route_events),
                "latest_route_timestamp": _format_timestamp(latest_route_timestamp),
                "incoming_exists": queue_stats["incoming_exists"],
                "queue_bundle_count": queue_stats["queue_bundle_count"],
                "latest_queue_update": queue_stats["latest_queue_update"],
                "is_reserved": is_reserved,
                "is_operational": is_operational,
                "is_unobserved": is_configured and len(route_events) == 0,
                "is_stale": bool(is_operational and (latest_route_timestamp is None or latest_route_timestamp < stale_cutoff)),
            }
        )

    latest_promotion_timestamp = _latest_event_timestamp(sorted_promotions)
    latest_routing_timestamp = _latest_event_timestamp(sorted_routes)
    promoted_bundles = {
        str(event.get("bundle_filename")).strip()
        for event in promotion_events
        if str(event.get("bundle_filename") or "").strip()
    }
    routed_bundles = {
        str(event.get("bundle_filename")).strip()
        for event in routing_events
        if str(event.get("bundle_filename") or "").strip()
    }
    promoted_without_route = sorted(bundle for bundle in promoted_bundles if bundle not in routed_bundles)

    unobserved_configured_destinations = sorted(destination for destination in configured_destinations if destination not in observed_destinations)
    inactive_configured_destinations = sorted(
        status["destination"]
        for status in destination_statuses
        if status["configured"] and not status["incoming_exists"]
    )
    stale_operational_destinations = sorted(
        status["destination"]
        for status in destination_statuses
        if status["is_operational"] and status["is_stale"]
    )
    unexpected_observed_destinations = sorted(destination for destination in observed_destinations if destination not in configured_destinations)
    operational_alignment_ok = (
        not unexpected_observed_destinations
        and set(observed_destinations) == set(operational_configured_destinations)
    )

    recent_promotion_items = _unique_recent_items(
        sorted_promotions,
        key_name="bundle_filename",
        limit=recent_item_limit,
        fields=("status", "routed_spine", "cluster_id"),
    )
    recent_routing_items = _unique_recent_items(
        sorted_routes,
        key_name="bundle_filename",
        limit=recent_item_limit,
        fields=("spine", "status", "score"),
    )

    relevant_files = tuple(
        dict.fromkeys(
            (
                "data/capture/promotion_log.jsonl",
                "data/capture/routing_log.jsonl",
                "config/spine_router.yaml",
                "config/lanes.yaml",
                "app/hq/capture/promote.py",
                "app/hq/capture/router.py",
                *incoming_authority_paths,
            )
        )
    )

    notes = []
    if operational_alignment_ok:
        notes.append("Observed route destinations align with the operational destinations declared by the router and lane manifests.")
    else:
        notes.append("Observed route destinations do not fully align with the operational destinations declared by the router and lane manifests.")
    if reserved_configured_destinations:
        notes.append(
            "Configured but reserved destinations remain unobserved: "
            + ", ".join(sorted(reserved_configured_destinations))
            + "."
        )
    if promoted_without_route:
        notes.append(
            "Promoted bundles without a matching routing ledger entry: "
            + ", ".join(promoted_without_route[:recent_item_limit])
            + (", ..." if len(promoted_without_route) > recent_item_limit else ".")
        )
    if stale_operational_destinations:
        notes.append(
            f"Operational destinations with no observed route in the last {stale_after_days} days: "
            + ", ".join(stale_operational_destinations)
            + "."
        )

    return {
        "recent_window_days": recent_window_days,
        "stale_after_days": stale_after_days,
        "recent_promotions_count": len(recent_promotions),
        "recent_promoted_bundle_count": len(
            {
                str(event.get("bundle_filename")).strip()
                for event in recent_promotions
                if str(event.get("bundle_filename") or "").strip()
            }
        ),
        "recent_routed_events_count": len(recent_routes),
        "recent_routed_bundle_count": len(
            {
                str(event.get("bundle_filename")).strip()
                for event in recent_routes
                if str(event.get("bundle_filename") or "").strip()
            }
        ),
        "latest_promotion_timestamp": _format_timestamp(latest_promotion_timestamp),
        "latest_routing_timestamp": _format_timestamp(latest_routing_timestamp),
        "configured_destinations": configured_destinations,
        "operational_configured_destinations": sorted(operational_configured_destinations),
        "reserved_configured_destinations": sorted(reserved_configured_destinations),
        "observed_destinations": observed_destinations,
        "unobserved_configured_destinations": unobserved_configured_destinations,
        "unexpected_observed_destinations": unexpected_observed_destinations,
        "inactive_configured_destinations": inactive_configured_destinations,
        "stale_operational_destinations": stale_operational_destinations,
        "route_alignment_ok": operational_alignment_ok,
        "active_lanes": sorted(active_lanes.keys()),
        "raw_capture_count": _count_files(raw_root, "raw_*.md"),
        "promoted_bundle_count": _count_files(promoted_root, "bundle_*.md"),
        "archived_raw_count": _count_files(archive_root, "raw_*.md"),
        "recent_promotions": recent_promotion_items,
        "recent_routes": recent_routing_items,
        "promoted_without_route": promoted_without_route,
        "destination_statuses": destination_statuses,
        "relevant_files": list(relevant_files),
        "notes": notes,
    }


def build_capture_routing_status_tool_result(repo_root: Path) -> dict[str, Any]:
    status = collect_capture_routing_status(repo_root)
    latest_promotion = status["latest_promotion_timestamp"] or "never"
    latest_routing = status["latest_routing_timestamp"] or "never"
    reserved_unobserved = status["reserved_configured_destinations"]
    operational_alignment = "aligned" if status["route_alignment_ok"] else "not aligned"

    summary = (
        "Capture/promotion/routing status reconstructed from the authoritative ledgers and router manifests. "
        f"Recent promotions: {status['recent_promotions_count']} in the last {status['recent_window_days']} days "
        f"(latest {latest_promotion}). "
        f"Recent routing events: {status['recent_routed_events_count']} in the last {status['recent_window_days']} days "
        f"(latest {latest_routing}). "
        f"Operational configured destinations are {operational_alignment} with observed routes."
    )
    if reserved_unobserved:
        summary += " Reserved configured destinations remain inactive/unobserved: " + ", ".join(reserved_unobserved) + "."

    highlights = [
        (
            f"recent_promotions={status['recent_promotions_count']} entries / "
            f"{status['recent_promoted_bundle_count']} bundles in last {status['recent_window_days']}d"
        ),
        (
            f"recent_routing={status['recent_routed_events_count']} entries / "
            f"{status['recent_routed_bundle_count']} bundles in last {status['recent_window_days']}d"
        ),
        f"latest_promotion={latest_promotion}",
        f"latest_routing={latest_routing}",
        f"raw_capture_count={status['raw_capture_count']}",
        f"promoted_bundle_count={status['promoted_bundle_count']}",
        f"archived_raw_count={status['archived_raw_count']}",
        "configured_destinations=" + _join_or_none(status["configured_destinations"]),
        "observed_destinations=" + _join_or_none(status["observed_destinations"]),
        "active_lanes=" + _join_or_none(status["active_lanes"]),
        "unobserved_configured_destinations=" + _join_or_none(status["unobserved_configured_destinations"]),
        "inactive_configured_destinations=" + _join_or_none(status["inactive_configured_destinations"]),
        "stale_operational_destinations=" + _join_or_none(status["stale_operational_destinations"]),
        "promoted_without_route=" + _join_or_none(status["promoted_without_route"]),
    ]
    highlights.extend(_queue_highlights(status["destination_statuses"]))
    highlights.extend(_recent_item_highlights("recent_promotion", status["recent_promotions"]))
    highlights.extend(_recent_item_highlights("recent_route", status["recent_routes"]))

    return {
        "status": "ok",
        "summary": summary,
        "highlights": tuple(highlights),
        "authority_paths": tuple(status["relevant_files"]),
        "notes": tuple(status["notes"]),
        "details": status,
    }


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return payload if isinstance(payload, dict) else {}


def _load_configured_destinations(path: Path) -> list[str]:
    payload = _load_yaml(path)
    destinations = []
    for item in payload.get("spines", []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if name:
            destinations.append(name)
    return sorted(dict.fromkeys(destinations))


def _load_active_lanes(payload: dict[str, Any]) -> dict[str, str]:
    active: dict[str, str] = {}
    for lane in payload.get("lanes", []):
        if not isinstance(lane, dict):
            continue
        lane_id = str(lane.get("lane_id") or "").strip()
        status = str(lane.get("status") or "").strip()
        if lane_id and status in {"active", "partial"}:
            active[lane_id] = status
    return active


def _load_reserved_spines(payload: dict[str, Any]) -> dict[str, str]:
    reserved: dict[str, str] = {}
    for item in payload.get("reserved_spines", []):
        if not isinstance(item, dict):
            continue
        spine_id = str(item.get("spine_id") or "").strip()
        status = str(item.get("status") or "").strip()
        if spine_id:
            reserved[spine_id] = status
    return reserved


def _parse_timestamp(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _event_timestamp(event: dict[str, Any]) -> datetime | None:
    return _parse_timestamp(event.get("timestamp_utc"))


def _sorted_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(events, key=lambda event: _event_timestamp(event) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)


def _latest_event_timestamp(events: list[dict[str, Any]]) -> datetime | None:
    for event in events:
        timestamp = _event_timestamp(event)
        if timestamp is not None:
            return timestamp
    return None


def _format_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _count_files(path: Path, pattern: str) -> int:
    if not path.exists():
        return 0
    return len(list(path.glob(pattern)))


def _queue_stats(incoming_dir: Path) -> dict[str, Any]:
    incoming_exists = incoming_dir.exists()
    if not incoming_exists:
        return {
            "incoming_exists": False,
            "queue_bundle_count": 0,
            "latest_queue_update": None,
        }

    files = sorted(item for item in incoming_dir.glob("*.md") if item.is_file())
    latest_mtime = None
    if files:
        latest_mtime = max(datetime.fromtimestamp(item.stat().st_mtime, tz=timezone.utc) for item in files)
    return {
        "incoming_exists": True,
        "queue_bundle_count": len(files),
        "latest_queue_update": _format_timestamp(latest_mtime),
    }


def _group_by_destination(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        destination = str(event.get("spine") or "").strip()
        if not destination:
            continue
        grouped.setdefault(destination, []).append(event)
    for rows in grouped.values():
        rows.sort(key=lambda event: _event_timestamp(event) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return grouped


def _unique_recent_items(
    events: list[dict[str, Any]],
    *,
    key_name: str,
    limit: int,
    fields: tuple[str, ...],
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    items: list[dict[str, Any]] = []
    for event in events:
        key = str(event.get(key_name) or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        item = {
            key_name: key,
            "timestamp_utc": _format_timestamp(_event_timestamp(event)),
        }
        for field in fields:
            value = event.get(field)
            if value is not None:
                item[field] = value
        items.append(item)
        if len(items) >= limit:
            break
    return items


def _join_or_none(values: list[str]) -> str:
    return ", ".join(values) if values else "none"


def _queue_highlights(destination_statuses: list[dict[str, Any]]) -> list[str]:
    highlights: list[str] = []
    for status in destination_statuses:
        if not status["configured"]:
            continue
        queue_count = status["queue_bundle_count"]
        latest_queue_update = status["latest_queue_update"] or "none"
        highlights.append(
            f"queue[{status['destination']}]={queue_count} bundles latest_queue_update={latest_queue_update}"
        )
    return highlights


def _recent_item_highlights(prefix: str, items: list[dict[str, Any]]) -> list[str]:
    highlights: list[str] = []
    for item in items:
        if prefix == "recent_promotion":
            highlights.append(
                f"{prefix}={item.get('bundle_filename')} status={item.get('status', 'unknown')} routed_spine={item.get('routed_spine', 'none')}"
            )
        else:
            highlights.append(
                f"{prefix}={item.get('bundle_filename')} spine={item.get('spine', 'none')} status={item.get('status', 'unknown')}"
            )
    return highlights
