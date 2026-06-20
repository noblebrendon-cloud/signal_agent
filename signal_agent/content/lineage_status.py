from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_REPO_ROOT = Path(__file__).resolve().parents[2]


def _default_paths(repo_root: Path) -> dict[str, Path]:
    return {
        "intake": repo_root / "data" / "intake" / "intake.jsonl",
        "promotion": repo_root / "data" / "capture" / "promotion_log.jsonl",
        "routing": repo_root / "data" / "capture" / "routing_log.jsonl",
        "artifact": repo_root / "data" / "artifact_registry.jsonl",
        "package": repo_root / "artifacts" / "videos" / "video_package_registry.jsonl",
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "_schema" not in obj:
            records.append(obj)
    return records


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _timestamp_str(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _timestamp_display(value: Any) -> str:
    parsed = _parse_timestamp(value)
    if parsed is None:
        return str(value or "")
    return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")


def _norm_text(value: Any) -> str:
    return str(value or "").replace("\\", "/").strip()


def _relative_repo_path(raw_path: Any, repo_root: Path) -> str | None:
    text = _norm_text(raw_path)
    if not text:
        return None
    candidate = Path(text)
    if candidate.is_absolute():
        try:
            rel = candidate.resolve().relative_to(repo_root.resolve())
            return str(rel).replace("\\", "/")
        except ValueError:
            return str(candidate.resolve()).replace("\\", "/")
    return str(candidate).replace("\\", "/")


def _path_key(raw_path: Any, repo_root: Path) -> str | None:
    rel = _relative_repo_path(raw_path, repo_root)
    if not rel:
        return None
    return rel.lower()


def _safe_bundle_stem(bundle_filename: str) -> str:
    if bundle_filename.lower().endswith(".md"):
        return bundle_filename[:-3]
    return bundle_filename


def _bundle_from_route_copy_path(raw_path: Any, repo_root: Path, spine: str) -> str | None:
    rel = _relative_repo_path(raw_path, repo_root)
    if not rel:
        return None
    expected_prefix = f"constraints/spines/{spine}/incoming/".lower()
    rel_lower = rel.lower()
    if not rel_lower.startswith(expected_prefix):
        return None
    return rel[len(expected_prefix) :]


def _overall_quality(qualities: list[str]) -> str:
    ranked = {"exact": 0, "inferred": 1, "missing": 2, "orphaned": 3}
    if not qualities:
        return "missing"
    return max(qualities, key=lambda item: ranked.get(item, 99))


def _dedupe_items(items: list[dict[str, Any]], keys: list[str]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        marker = tuple(item.get(key) for key in keys)
        if marker in seen:
            continue
        seen.add(marker)
        out.append(item)
    return out


def _merge_intake_matches(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[tuple[Any, ...], dict[str, Any]] = {}
    for item in items:
        marker = (
            item.get("source_path"),
            item.get("source_sha256"),
            item.get("text_output_path"),
            item.get("text_sha256"),
        )
        existing = merged.get(marker)
        reason = item.get("match_reason")
        if existing is None:
            created = dict(item)
            created["match_reasons"] = [reason] if reason else []
            merged[marker] = created
            continue
        if reason and reason not in existing["match_reasons"]:
            existing["match_reasons"].append(reason)
    out = list(merged.values())
    for item in out:
        if "match_reason" in item:
            item.pop("match_reason", None)
    return out


def _ref_block(
    kind: str,
    items: list[dict[str, Any]] | list[str] | None,
    link_quality: str,
    note: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "kind": kind,
        "link_quality": link_quality,
        "count": len(items or []),
        "primary": None,
        "items": items or [],
    }
    if items:
        payload["primary"] = items[0]
    if note:
        payload["note"] = note
    return payload


def _latest_record(records: list[dict[str, Any]], timestamp_key: str) -> dict[str, Any] | None:
    if not records:
        return None
    return sorted(
        records,
        key=lambda rec: (_parse_timestamp(rec.get(timestamp_key)) or datetime.min.replace(tzinfo=timezone.utc)),
    )[-1]


def _artifact_needles(bundle_filename: str, artifacts: list[dict[str, Any]]) -> set[str]:
    needles = {_safe_bundle_stem(bundle_filename).lower(), bundle_filename.lower()}
    for artifact in artifacts:
        for key in ("name", "original_name", "sha256", "path"):
            value = _norm_text(artifact.get(key))
            if value:
                needles.add(value.lower())
                needles.add(Path(value).stem.lower())
    return {needle for needle in needles if len(needle) >= 6}


def _build_package_ref(
    bundle_filename: str,
    artifacts: list[dict[str, Any]],
    package_records: list[dict[str, Any]],
) -> tuple[dict[str, Any], set[str]]:
    exact_items: list[dict[str, Any]] = []
    inferred_items: list[dict[str, Any]] = []
    matched_ids: set[str] = set()

    artifact_paths = {
        _norm_text(artifact.get("path")).lower()
        for artifact in artifacts
        if _norm_text(artifact.get("path"))
    }
    artifact_shas = {
        _norm_text(artifact.get("sha256")).lower()
        for artifact in artifacts
        if _norm_text(artifact.get("sha256"))
    }
    needles = _artifact_needles(bundle_filename, artifacts)
    bundle_key = bundle_filename.lower()

    for pkg in package_records:
        run_id = _norm_text(pkg.get("run_id"))
        package_artifact_sha = _norm_text(pkg.get("artifact_sha256")).lower()
        package_bundle_filename = _norm_text(pkg.get("bundle_filename")).lower()
        fields = [
            _norm_text(pkg.get("output_video")).lower(),
            _norm_text(pkg.get("manifest_path")).lower(),
            _norm_text(pkg.get("package_index_path")).lower(),
            _norm_text(pkg.get("package_dir")).lower(),
            _norm_text(pkg.get("title")).lower(),
            _norm_text(pkg.get("channel_target")).lower(),
        ]

        exact_match_reason: str | None = None
        if package_artifact_sha and package_artifact_sha in artifact_shas:
            exact_match_reason = "artifact_sha256"
        elif package_bundle_filename and package_bundle_filename == bundle_key:
            exact_match_reason = "bundle_filename"
        elif artifact_paths and any(field and field in artifact_paths for field in fields):
            exact_match_reason = "artifact_path"

        if exact_match_reason:
            exact_items.append(
                {
                    "run_id": run_id or None,
                    "created_at": pkg.get("created_at"),
                    "title": pkg.get("title"),
                    "output_video": pkg.get("output_video"),
                    "package_dir": pkg.get("package_dir"),
                    "manifest_path": pkg.get("manifest_path"),
                    "package_index_path": pkg.get("package_index_path"),
                    "artifact_sha256": pkg.get("artifact_sha256"),
                    "bundle_filename": pkg.get("bundle_filename"),
                    "match_reason": exact_match_reason,
                }
            )
            if run_id:
                matched_ids.add(run_id)
            continue

        searchable = " ".join(field for field in fields if field)
        if searchable and any(needle in searchable for needle in needles):
            inferred_items.append(
                {
                    "run_id": run_id or None,
                    "created_at": pkg.get("created_at"),
                    "title": pkg.get("title"),
                    "output_video": pkg.get("output_video"),
                    "package_dir": pkg.get("package_dir"),
                    "manifest_path": pkg.get("manifest_path"),
                    "package_index_path": pkg.get("package_index_path"),
                    "artifact_sha256": pkg.get("artifact_sha256"),
                    "bundle_filename": pkg.get("bundle_filename"),
                    "match_reason": "bundle_or_artifact_name_substring",
                }
            )
            if run_id:
                matched_ids.add(run_id)

    if exact_items:
        return (_ref_block("video_package", exact_items, "exact"), matched_ids)
    if inferred_items:
        return (
            _ref_block(
                "video_package",
                inferred_items,
                "inferred",
                note="Package linkage inferred from bundle or artifact naming because the registry does not expose a canonical content input id.",
            ),
            matched_ids,
        )
    return (
        _ref_block(
            "video_package",
            [],
            "missing",
            note="No exact package link was found in video_package_registry.jsonl.",
        ),
        matched_ids,
    )


def load_content_lifecycle_view(
    repo_root: Path | str | None = None,
    *,
    spine: str = "content_publishing",
    bundle_filename: str | None = None,
    limit: int | None = 20,
) -> dict[str, Any]:
    repo_root = Path(repo_root or _REPO_ROOT).resolve()
    paths = _default_paths(repo_root)

    intake_records = [rec for rec in _read_jsonl(paths["intake"]) if rec.get("status") == "success"]
    promotion_records = _read_jsonl(paths["promotion"])
    routing_records = [rec for rec in _read_jsonl(paths["routing"]) if rec.get("status") == "ok"]
    artifact_records = _read_jsonl(paths["artifact"])
    package_records = _read_jsonl(paths["package"])

    intake_by_path: dict[str, list[dict[str, Any]]] = {}
    intake_by_sha: dict[str, list[dict[str, Any]]] = {}
    for record in intake_records:
        path_key = _path_key(record.get("source_path"), repo_root)
        if path_key:
            intake_by_path.setdefault(path_key, []).append(record)
        source_sha = _norm_text(record.get("source_sha256")).lower()
        if source_sha:
            intake_by_sha.setdefault(source_sha, []).append(record)

    promotions_by_bundle: dict[str, list[dict[str, Any]]] = {}
    for record in promotion_records:
        bundle = _norm_text(record.get("bundle_filename"))
        if bundle:
            promotions_by_bundle.setdefault(bundle, []).append(record)

    routes_by_bundle: dict[str, list[dict[str, Any]]] = {}
    for record in routing_records:
        bundle = _norm_text(record.get("bundle_filename"))
        if bundle:
            routes_by_bundle.setdefault(bundle, []).append(record)

    artifacts_by_original_name: dict[str, list[dict[str, Any]]] = {}
    for record in artifact_records:
        bundle = _norm_text(record.get("original_name"))
        if bundle:
            artifacts_by_original_name.setdefault(bundle, []).append(record)

    candidate_bundles: set[str] = set()
    if bundle_filename:
        candidate_bundles.add(bundle_filename)
    else:
        for record in promotion_records:
            if _norm_text(record.get("routed_spine")) == spine:
                candidate_bundles.add(_norm_text(record.get("bundle_filename")))
        for record in routing_records:
            if _norm_text(record.get("spine")) == spine:
                candidate_bundles.add(_norm_text(record.get("bundle_filename")))
        for record in intake_records:
            bundle = _bundle_from_route_copy_path(record.get("source_path"), repo_root, spine)
            if bundle:
                candidate_bundles.add(bundle)

    matched_package_ids: set[str] = set()
    lineages: list[dict[str, Any]] = []

    for bundle in sorted(filter(None, candidate_bundles)):
        promotion_items = promotions_by_bundle.get(bundle, [])
        route_items = [rec for rec in routes_by_bundle.get(bundle, []) if _norm_text(rec.get("spine")) == spine]
        artifact_items = sorted(
            artifacts_by_original_name.get(bundle, []),
            key=lambda rec: (_parse_timestamp(rec.get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc)),
        )

        promotion = _latest_record(promotion_items, "timestamp_utc")
        route = _latest_record(route_items, "timestamp_utc")

        route_spine = _norm_text(route.get("spine") if route else None) or _norm_text(promotion.get("routed_spine") if promotion else None) or spine
        expected_route_copy_path = f"constraints/spines/{route_spine}/incoming/{bundle}"

        source_items: list[dict[str, Any]] = []
        if promotion:
            for raw_file in promotion.get("raw_files", []):
                source_items.append({"raw_file": raw_file})

        intake_items: list[dict[str, Any]] = []
        expected_route_key = _path_key(expected_route_copy_path, repo_root)
        if expected_route_key and expected_route_key in intake_by_path:
            for record in intake_by_path[expected_route_key]:
                intake_items.append(
                    {
                        "timestamp": record.get("timestamp"),
                        "source_path": record.get("source_path"),
                        "source_sha256": record.get("source_sha256"),
                        "text_output_path": record.get("text_output_path"),
                        "text_sha256": record.get("text_sha256"),
                        "match_reason": "route_copy_path",
                    }
                )

        for artifact in artifact_items:
            artifact_path_key = _path_key(artifact.get("path"), repo_root)
            if artifact_path_key and artifact_path_key in intake_by_path:
                for record in intake_by_path[artifact_path_key]:
                    intake_items.append(
                        {
                            "timestamp": record.get("timestamp"),
                            "source_path": record.get("source_path"),
                            "source_sha256": record.get("source_sha256"),
                            "text_output_path": record.get("text_output_path"),
                            "text_sha256": record.get("text_sha256"),
                            "match_reason": "artifact_path",
                        }
                    )
            artifact_sha = _norm_text(artifact.get("sha256")).lower()
            for record in intake_by_sha.get(artifact_sha, []):
                intake_items.append(
                    {
                        "timestamp": record.get("timestamp"),
                        "source_path": record.get("source_path"),
                        "source_sha256": record.get("source_sha256"),
                        "text_output_path": record.get("text_output_path"),
                        "text_sha256": record.get("text_sha256"),
                        "match_reason": "artifact_sha256",
                    }
                )

        intake_items = _merge_intake_matches(intake_items)

        artifact_payload = [
            {
                "timestamp": record.get("timestamp"),
                "name": record.get("name"),
                "original_name": record.get("original_name"),
                "sha256": record.get("sha256"),
                "path": record.get("path"),
                "route": record.get("route"),
                "kind": record.get("kind"),
            }
            for record in artifact_items
        ]

        package_ref, package_ids = _build_package_ref(bundle, artifact_items, package_records)
        matched_package_ids |= package_ids

        source_ref = _ref_block("capture_raw", source_items, "exact" if source_items else "missing")
        intake_ref = _ref_block("intake_record", intake_items, "exact" if intake_items else "missing")
        promotion_ref = _ref_block(
            "promotion_log",
            [
                {
                    "timestamp_utc": record.get("timestamp_utc"),
                    "cluster_id": record.get("cluster_id"),
                    "bundle_filename": record.get("bundle_filename"),
                    "raw_file_count": len(record.get("raw_files", [])),
                    "routed_spine": record.get("routed_spine"),
                    "status": record.get("status"),
                }
                for record in sorted(
                    promotion_items,
                    key=lambda rec: (_parse_timestamp(rec.get("timestamp_utc")) or datetime.min.replace(tzinfo=timezone.utc)),
                    reverse=True,
                )
            ],
            "exact" if promotion_items else "missing",
        )
        route_ref = _ref_block(
            "routing_log",
            [
                {
                    "timestamp_utc": record.get("timestamp_utc"),
                    "bundle_filename": record.get("bundle_filename"),
                    "spine": record.get("spine"),
                    "score": record.get("score"),
                    "router_ruleset_hash": record.get("router_ruleset_hash"),
                }
                for record in sorted(
                    route_items,
                    key=lambda rec: (_parse_timestamp(rec.get("timestamp_utc")) or datetime.min.replace(tzinfo=timezone.utc)),
                    reverse=True,
                )
            ],
            "exact" if route_items else "missing",
        )
        artifact_ref = _ref_block("artifact_registry", artifact_payload, "exact" if artifact_payload else "missing")

        link_quality = {
            "source_ref": source_ref["link_quality"],
            "intake_ref": intake_ref["link_quality"],
            "promotion_ref": promotion_ref["link_quality"],
            "route_ref": route_ref["link_quality"],
            "artifact_ref": artifact_ref["link_quality"],
            "package_ref": package_ref["link_quality"],
        }
        link_quality["overall"] = _overall_quality(list(link_quality.values()))

        if package_ref["link_quality"] == "exact":
            current_stage = "packaged_output"
        elif package_ref["link_quality"] == "inferred":
            current_stage = "packaged_output_inferred"
        elif artifact_ref["link_quality"] == "exact":
            current_stage = "artifact_registered"
        elif route_ref["link_quality"] == "exact":
            current_stage = "routed"
        elif promotion_ref["link_quality"] == "exact":
            current_stage = "promoted"
        elif intake_ref["link_quality"] == "exact":
            current_stage = "intake_only"
        else:
            current_stage = "unknown"

        missing_refs = [
            ref_name
            for ref_name, quality in link_quality.items()
            if ref_name != "overall" and quality == "missing"
        ]
        integrity_flags = [f"missing_{name}" for name in missing_refs]
        if len(route_items) > 1:
            integrity_flags.append("duplicate_route_records")
        if len(artifact_items) > 1:
            integrity_flags.append("multiple_artifact_records")
        if promotion and route and _norm_text(promotion.get("routed_spine")) and _norm_text(promotion.get("routed_spine")) != _norm_text(route.get("spine")):
            integrity_flags.append("promotion_route_spine_mismatch")
        if intake_items and artifact_items:
            route_copy_records = [
                item
                for item in intake_items
                if "route_copy_path" in item.get("match_reasons", [])
            ]
            if route_copy_records:
                route_sha_values = {str(item.get("source_sha256", "")).lower() for item in route_copy_records if item.get("source_sha256")}
                artifact_sha_values = {str(item.get("sha256", "")).lower() for item in artifact_items if item.get("sha256")}
                if route_sha_values and artifact_sha_values and route_sha_values.isdisjoint(artifact_sha_values):
                    integrity_flags.append("route_copy_artifact_sha_mismatch")

        timestamps: list[datetime] = []
        for record in promotion_items:
            parsed = _parse_timestamp(record.get("timestamp_utc"))
            if parsed:
                timestamps.append(parsed)
        for record in route_items:
            parsed = _parse_timestamp(record.get("timestamp_utc"))
            if parsed:
                timestamps.append(parsed)
        for record in artifact_items:
            parsed = _parse_timestamp(record.get("timestamp"))
            if parsed:
                timestamps.append(parsed)
        for record in intake_items:
            parsed = _parse_timestamp(record.get("timestamp"))
            if parsed:
                timestamps.append(parsed)
        for record in package_ref.get("items", []):
            parsed = _parse_timestamp(record.get("created_at"))
            if parsed:
                timestamps.append(parsed)

        lineages.append(
            {
                "lineage_id": f"content:{_safe_bundle_stem(bundle)}",
                "source_ref": source_ref,
                "intake_ref": intake_ref,
                "promotion_ref": promotion_ref,
                "route_ref": route_ref,
                "artifact_ref": artifact_ref,
                "package_ref": package_ref,
                "current_stage": current_stage,
                "link_quality": link_quality,
                "missing_refs": missing_refs,
                "integrity_flags": integrity_flags,
                "last_event_at": _timestamp_str(max(timestamps) if timestamps else None),
            }
        )

    for package in package_records:
        run_id = _norm_text(package.get("run_id"))
        if not run_id or run_id in matched_package_ids:
            continue
        created_at = _parse_timestamp(package.get("created_at"))
        package_ref = _ref_block(
            "video_package",
            [
                {
                    "run_id": run_id,
                    "created_at": package.get("created_at"),
                    "title": package.get("title"),
                    "output_video": package.get("output_video"),
                    "package_dir": package.get("package_dir"),
                    "manifest_path": package.get("manifest_path"),
                    "package_index_path": package.get("package_index_path"),
                    "artifact_sha256": package.get("artifact_sha256"),
                    "bundle_filename": package.get("bundle_filename"),
                }
            ],
            "orphaned",
            note="Package record has no exact or inferred content-domain lineage link from the available ledgers.",
        )
        lineages.append(
            {
                "lineage_id": f"package:{run_id}",
                "source_ref": _ref_block("capture_raw", [], "missing"),
                "intake_ref": _ref_block("intake_record", [], "missing"),
                "promotion_ref": _ref_block("promotion_log", [], "missing"),
                "route_ref": _ref_block("routing_log", [], "missing"),
                "artifact_ref": _ref_block("artifact_registry", [], "missing"),
                "package_ref": package_ref,
                "current_stage": "orphaned_package",
                "link_quality": {
                    "source_ref": "missing",
                    "intake_ref": "missing",
                    "promotion_ref": "missing",
                    "route_ref": "missing",
                    "artifact_ref": "missing",
                    "package_ref": "orphaned",
                    "overall": "orphaned",
                },
                "missing_refs": ["source_ref", "intake_ref", "promotion_ref", "route_ref", "artifact_ref"],
                "integrity_flags": ["orphaned_package_ref"],
                "last_event_at": _timestamp_str(created_at),
            }
        )

    lineages.sort(
        key=lambda item: (
            _parse_timestamp(item.get("last_event_at")) or datetime.min.replace(tzinfo=timezone.utc),
            item.get("lineage_id", ""),
        ),
        reverse=True,
    )
    if limit is not None:
        lineages = lineages[: max(int(limit), 0)]

    return {
        "repo_root": str(repo_root),
        "spine": spine,
        "source_paths": {name: str(path) for name, path in paths.items()},
        "lineage_count": len(lineages),
        "lineages": lineages,
    }


def _normalize_lookup_token(value: Any) -> str:
    return _norm_text(value).lower()


def _path_basename(value: Any) -> str | None:
    text = _norm_text(value)
    if not text:
        return None
    return Path(text).name.lower() or None


def _package_lookup_fields(item: dict[str, Any]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for key in ("run_id", "output_video", "package_dir", "manifest_path", "package_index_path"):
        value = _norm_text(item.get(key))
        if value:
            fields[key] = value
    return fields


def find_package_lineage(
    view: dict[str, Any],
    package_identifier: str,
) -> dict[str, Any] | None:
    target = _normalize_lookup_token(package_identifier)
    if not target:
        return None

    exact_matches: list[dict[str, Any]] = []
    basename_matches: list[dict[str, Any]] = []

    for lineage in view.get("lineages", []):
        package_ref = lineage.get("package_ref", {})
        for item in package_ref.get("items", []):
            lookup_fields = _package_lookup_fields(item)
            exact_field = next(
                (
                    field_name
                    for field_name, field_value in lookup_fields.items()
                    if _normalize_lookup_token(field_value) == target
                ),
                None,
            )
            if exact_field:
                exact_matches.append(
                    {
                        "lineage": lineage,
                        "package_item": item,
                        "identifier_match_field": exact_field,
                        "identifier_match_quality": "exact",
                    }
                )
                continue

            basename_field = next(
                (
                    field_name
                    for field_name in ("output_video", "package_dir", "manifest_path", "package_index_path")
                    if _path_basename(lookup_fields.get(field_name)) == target
                ),
                None,
            )
            if basename_field:
                basename_matches.append(
                    {
                        "lineage": lineage,
                        "package_item": item,
                        "identifier_match_field": basename_field,
                        "identifier_match_quality": "basename",
                    }
                )

    if len(exact_matches) == 1:
        return exact_matches[0]
    if len(exact_matches) > 1:
        raise ValueError(f"Package identifier matched multiple package rows exactly: {package_identifier}")
    if len(basename_matches) == 1:
        return basename_matches[0]
    if len(basename_matches) > 1:
        raise ValueError(f"Package identifier matched multiple package rows by basename: {package_identifier}")
    return None


def _trace_identity(ref_name: str, ref: dict[str, Any], package_item: dict[str, Any] | None = None) -> str:
    if ref_name == "package_ref" and package_item:
        return _norm_text(package_item.get("run_id")) or _norm_text(package_item.get("output_video")) or "(unidentified package)"

    primary = ref.get("primary")
    if not isinstance(primary, dict):
        return "missing"

    if ref_name == "artifact_ref":
        return (
            _norm_text(primary.get("name"))
            or _norm_text(primary.get("path"))
            or _norm_text(primary.get("sha256"))
            or "artifact"
        )
    if ref_name == "route_ref":
        return _norm_text(primary.get("bundle_filename")) or _norm_text(primary.get("spine")) or "route"
    if ref_name == "promotion_ref":
        return _norm_text(primary.get("bundle_filename")) or _norm_text(primary.get("cluster_id")) or "promotion"
    if ref_name == "intake_ref":
        return (
            _norm_text(primary.get("source_path"))
            or _norm_text(primary.get("text_output_path"))
            or _norm_text(primary.get("source_sha256"))
            or "intake"
        )
    if ref_name == "source_ref":
        raw_files = [item.get("raw_file") for item in ref.get("items", []) if item.get("raw_file")]
        if raw_files:
            preview = ", ".join(str(name) for name in raw_files[:3])
            if len(raw_files) > 3:
                preview += f", +{len(raw_files) - 3} more"
            return preview
        return "missing"
    return "missing"


def _trace_detail_lines(
    ref_name: str,
    ref: dict[str, Any],
    package_item: dict[str, Any] | None = None,
) -> list[str]:
    lines: list[str] = []
    primary = ref.get("primary") if isinstance(ref.get("primary"), dict) else None

    if ref_name == "package_ref":
        item = package_item or primary or {}
        output_video = _norm_text(item.get("output_video"))
        if output_video:
            lines.append(f"  output_video: {output_video}")
        artifact_sha = _norm_text(item.get("artifact_sha256"))
        if artifact_sha:
            lines.append(f"  artifact_sha256: {artifact_sha}")
        bundle_filename = _norm_text(item.get("bundle_filename"))
        if bundle_filename:
            lines.append(f"  bundle_filename: {bundle_filename}")
        package_dir = _norm_text(item.get("package_dir"))
        if package_dir:
            lines.append(f"  package_dir: {package_dir}")
        if ref.get("note") and ref.get("link_quality") != "exact":
            lines.append(f"  note: {ref['note']}")
        return lines

    if not primary:
        return lines

    if ref_name == "artifact_ref":
        artifact_sha = _norm_text(primary.get("sha256"))
        if artifact_sha:
            lines.append(f"  sha256: {artifact_sha}")
        artifact_path = _norm_text(primary.get("path"))
        if artifact_path:
            lines.append(f"  path: {artifact_path}")
        bundle_filename = _norm_text(primary.get("original_name"))
        if bundle_filename:
            lines.append(f"  bundle_filename: {bundle_filename}")
        return lines

    if ref_name == "route_ref":
        spine = _norm_text(primary.get("spine"))
        if spine:
            lines.append(f"  spine: {spine}")
        timestamp = _norm_text(primary.get("timestamp_utc"))
        if timestamp:
            lines.append(f"  timestamp: {timestamp}")
        return lines

    if ref_name == "promotion_ref":
        cluster_id = _norm_text(primary.get("cluster_id"))
        if cluster_id:
            lines.append(f"  cluster_id: {cluster_id}")
        timestamp = _norm_text(primary.get("timestamp_utc"))
        if timestamp:
            lines.append(f"  timestamp: {timestamp}")
        return lines

    if ref_name == "intake_ref":
        source_sha = _norm_text(primary.get("source_sha256"))
        if source_sha:
            lines.append(f"  source_sha256: {source_sha}")
        reasons = primary.get("match_reasons") or []
        if reasons:
            lines.append(f"  match_reasons: {', '.join(str(reason) for reason in reasons)}")
        return lines

    if ref_name == "source_ref":
        items = ref.get("items", [])
        if items:
            lines.append(f"  raw_file_count: {len(items)}")
        return lines

    return lines


def _trace_node_payload(
    ref_name: str,
    ref: dict[str, Any],
    package_item: dict[str, Any] | None = None,
) -> dict[str, Any]:
    primary = package_item if ref_name == "package_ref" and package_item else ref.get("primary")
    payload: dict[str, Any] = {
        "status": ref.get("link_quality", "missing"),
        "kind": ref.get("kind"),
        "count": ref.get("count", 0),
        "identity": _trace_identity(ref_name, ref, package_item if ref_name == "package_ref" else None),
        "primary": primary if isinstance(primary, dict) else None,
    }
    if ref.get("note"):
        payload["note"] = ref["note"]
    return payload


def build_package_lineage_trace_payload(
    trace: dict[str, Any],
    requested_identifier: str,
) -> dict[str, Any]:
    lineage = trace["lineage"]
    package_item = trace["package_item"]
    package_ref = lineage.get("package_ref", {})
    return {
        "requested_identifier": requested_identifier,
        "matched_identifier_type": trace.get("identifier_match_field"),
        "matched_identifier_quality": trace.get("identifier_match_quality"),
        "package_status": package_ref.get("link_quality", "missing"),
        "lineage_id": lineage.get("lineage_id"),
        "stage": lineage.get("current_stage"),
        "last_event_at": lineage.get("last_event_at"),
        "integrity_flags": lineage.get("integrity_flags", []),
        "nodes": {
            "package": _trace_node_payload("package_ref", package_ref, package_item),
            "artifact": _trace_node_payload("artifact_ref", lineage.get("artifact_ref", {})),
            "route": _trace_node_payload("route_ref", lineage.get("route_ref", {})),
            "promotion": _trace_node_payload("promotion_ref", lineage.get("promotion_ref", {})),
            "intake": _trace_node_payload("intake_ref", lineage.get("intake_ref", {})),
            "source": _trace_node_payload("source_ref", lineage.get("source_ref", {})),
        },
    }


def _graph_edge_status(from_status: str, to_status: str) -> str:
    if from_status in {"missing", "orphaned"} or to_status in {"missing", "orphaned"}:
        return "missing"
    if from_status == "inferred" or to_status == "inferred":
        return "inferred"
    return "exact"


def build_package_lineage_graph_payload(
    trace: dict[str, Any],
    requested_identifier: str,
) -> dict[str, Any]:
    lineage = trace["lineage"]
    package_item = trace["package_item"]
    package_ref = lineage.get("package_ref", {})
    graph_order = [
        ("package", "package_ref"),
        ("artifact", "artifact_ref"),
        ("route", "route_ref"),
        ("promotion", "promotion_ref"),
        ("intake", "intake_ref"),
        ("source", "source_ref"),
    ]

    nodes: list[dict[str, Any]] = []
    for node_id, ref_name in graph_order:
        node_payload = _trace_node_payload(
            ref_name,
            lineage.get(ref_name, {}),
            package_item if ref_name == "package_ref" else None,
        )
        node = {
            "id": node_id,
            "kind": node_payload.get("kind"),
            "status": node_payload.get("status"),
            "identity": node_payload.get("identity"),
            "primary": node_payload.get("primary"),
        }
        if "note" in node_payload:
            node["note"] = node_payload["note"]
        nodes.append(node)

    edges: list[dict[str, Any]] = []
    for index in range(len(nodes) - 1):
        current = nodes[index]
        nxt = nodes[index + 1]
        edges.append(
            {
                "from": current["id"],
                "to": nxt["id"],
                "status": _graph_edge_status(
                    str(current.get("status") or "missing"),
                    str(nxt.get("status") or "missing"),
                ),
            }
        )

    return {
        "requested_identifier": requested_identifier,
        "matched_identifier_type": trace.get("identifier_match_field"),
        "matched_identifier_quality": trace.get("identifier_match_quality"),
        "package_status": package_ref.get("link_quality", "missing"),
        "lineage_id": lineage.get("lineage_id"),
        "integrity_flags": lineage.get("integrity_flags", []),
        "nodes": nodes,
        "edges": edges,
    }


def _mermaid_escape(value: Any) -> str:
    text = _norm_text(value) or "missing"
    return text.replace('"', '\\"')


def render_package_lineage_mermaid(graph_payload: dict[str, Any]) -> str:
    lines = ["flowchart TD"]

    for node in graph_payload.get("nodes", []):
        node_id = _norm_text(node.get("id")) or "unknown"
        label = "\\n".join(
            [
                _mermaid_escape(node_id),
                _mermaid_escape(node.get("status")),
                _mermaid_escape(node.get("identity")),
            ]
        )
        lines.append(f'  {node_id}["{label}"]')

    lines.append("")

    for edge in graph_payload.get("edges", []):
        from_id = _norm_text(edge.get("from")) or "unknown"
        to_id = _norm_text(edge.get("to")) or "unknown"
        lines.append(f"  {from_id} --> {to_id}")

    return "\n".join(lines)


def render_package_lineage_trace(trace: dict[str, Any]) -> str:
    lineage = trace["lineage"]
    package_item = trace["package_item"]
    package_ref = lineage.get("package_ref", {})
    lines = [
        "PACKAGE LINEAGE TRACE",
        f"Package    : {_trace_identity('package_ref', package_ref, package_item)}",
        f"Lineage ID : {lineage.get('lineage_id')}",
        f"Stage      : {lineage.get('current_stage')}",
        f"Last Event : {lineage.get('last_event_at') or '(unknown)'}",
        f"Flags      : {', '.join(lineage.get('integrity_flags', [])) or '(none)'}",
        "",
    ]

    steps = [
        ("package", "package_ref"),
        ("artifact", "artifact_ref"),
        ("route", "route_ref"),
        ("promotion", "promotion_ref"),
        ("intake", "intake_ref"),
        ("source", "source_ref"),
    ]

    for index, (label, ref_name) in enumerate(steps):
        ref = lineage.get(ref_name, {})
        identity = _trace_identity(ref_name, ref, package_item if ref_name == "package_ref" else None)
        lines.append(f"{label}: {identity} [{ref.get('link_quality', 'missing')}]")
        lines.extend(_trace_detail_lines(ref_name, ref, package_item if ref_name == "package_ref" else None))
        if index < len(steps) - 1:
            lines.append("  ↓")

    return "\n".join(lines)


def render_content_lifecycle_text(view: dict[str, Any]) -> str:
    lineages = view.get("lineages", [])
    lines = [
        "CONTENT LIFECYCLE VIEW",
        f"Spine     : {view.get('spine')}",
        f"Repo Root : {view.get('repo_root')}",
        f"Lineages  : {view.get('lineage_count')}",
        "",
    ]

    if not lineages:
        lines.append("No matching lineages.")
        return "\n".join(lines)

    if len(lineages) > 1:
        header = f"{'lineage_id':<34} {'stage':<24} {'src':<8} {'intake':<8} {'promo':<8} {'route':<8} {'artifact':<9} {'package':<8} {'last_event_at':<20}"
        lines.append(header)
        lines.append("-" * len(header))
        for lineage in lineages:
            quality = lineage.get("link_quality", {})
            last_event_display = _timestamp_display(lineage.get("last_event_at"))
            lines.append(
                f"{str(lineage.get('lineage_id', ''))[:34]:<34} "
                f"{str(lineage.get('current_stage', ''))[:24]:<24} "
                f"{str(quality.get('source_ref', '')):<8} "
                f"{str(quality.get('intake_ref', '')):<8} "
                f"{str(quality.get('promotion_ref', '')):<8} "
                f"{str(quality.get('route_ref', '')):<8} "
                f"{str(quality.get('artifact_ref', '')):<9} "
                f"{str(quality.get('package_ref', '')):<8} "
                f"{last_event_display[:20]:<20}"
            )
        return "\n".join(lines)

    lineage = lineages[0]
    quality = lineage.get("link_quality", {})
    lines.extend(
        [
            f"Lineage ID : {lineage.get('lineage_id')}",
            f"Stage      : {lineage.get('current_stage')}",
            f"Last Event : {lineage.get('last_event_at')}",
            "Link Qual. : "
            + ", ".join(
                [
                    f"source={quality.get('source_ref')}",
                    f"intake={quality.get('intake_ref')}",
                    f"promotion={quality.get('promotion_ref')}",
                    f"route={quality.get('route_ref')}",
                    f"artifact={quality.get('artifact_ref')}",
                    f"package={quality.get('package_ref')}",
                    f"overall={quality.get('overall')}",
                ]
            ),
            f"Missing    : {', '.join(lineage.get('missing_refs', [])) or '(none)'}",
            f"Flags      : {', '.join(lineage.get('integrity_flags', [])) or '(none)'}",
            "",
            f"Source Ref     : {lineage['source_ref']['count']} item(s)",
            f"Intake Ref     : {lineage['intake_ref']['count']} item(s)",
            f"Promotion Ref  : {lineage['promotion_ref']['count']} item(s)",
            f"Route Ref      : {lineage['route_ref']['count']} item(s)",
            f"Artifact Ref   : {lineage['artifact_ref']['count']} item(s)",
            f"Package Ref    : {lineage['package_ref']['count']} item(s)",
        ]
    )

    for label in ("source_ref", "intake_ref", "promotion_ref", "route_ref", "artifact_ref", "package_ref"):
        ref = lineage[label]
        if not ref.get("items"):
            continue
        lines.append("")
        lines.append(f"{label}:")
        for item in ref["items"][:5]:
            lines.append(f"  - {json.dumps(item, ensure_ascii=False, sort_keys=True)}")
        extra_count = max(ref["count"] - 5, 0)
        if extra_count:
            lines.append(f"  - ... {extra_count} more")

    return "\n".join(lines)
