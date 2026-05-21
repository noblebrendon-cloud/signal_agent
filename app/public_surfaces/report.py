"""
Read-only public-surface governance readiness reporting.

This module summarizes validated domain profiles and primitives for operator
inspection. It does not route, approve, emit, post, or mutate any files.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from shared import public_surfaces


def build_governance_report(
    *,
    domain_profiles_path: str | Path,
    primitive_registry_path: str | Path,
) -> dict[str, Any]:
    """
    Build a deterministic public-surface governance readiness report.

    Primitive validation remains owned by `shared.public_surfaces`. Domain
    documents that fail whole-file loading are inspected row by row with the
    shared validator so structurally invalid surfaces remain visible to the
    operator report instead of disappearing behind one loader error.
    """
    profiles, invalid_domains, observed_domain_count = _load_report_domains(domain_profiles_path)
    primitives = public_surfaces.load_primitive_registry(primitive_registry_path)

    known_domain_ids = set(profiles)
    primitives_by_domain: dict[str, list[str]] = defaultdict(list)
    missing_domain_refs: list[dict[str, Any]] = []
    approval_counts: Counter[str] = Counter()

    for domain_id in sorted(profiles):
        approval_counts[_domain_approval_class(profiles[domain_id])] += 1

    for primitive in sorted(primitives, key=lambda row: str(row["primitive_id"])):
        primitive_id = str(primitive["primitive_id"])
        compatible_domains = sorted(set(str(domain_id) for domain_id in primitive["compatible_domains"]))
        missing = sorted(domain_id for domain_id in compatible_domains if domain_id not in known_domain_ids)
        if missing:
            missing_domain_refs.append(
                {
                    "primitive_id": primitive_id,
                    "domain_ids": missing,
                }
            )
        for domain_id in compatible_domains:
            if domain_id in known_domain_ids:
                primitives_by_domain[domain_id].append(primitive_id)

    normalized_primitives_by_domain = {
        domain_id: sorted(set(primitives_by_domain.get(domain_id, [])))
        for domain_id in sorted(known_domain_ids)
    }
    routable_domains = sorted(
        domain_id
        for domain_id, profile in profiles.items()
        if public_surfaces.is_domain_routable(profile)
    )
    quarantined_domains = sorted(
        domain_id
        for domain_id, profile in profiles.items()
        if _domain_lifecycle_state(profile) == "quarantined"
        or _domain_approval_class(profile) == "quarantined"
    )
    domains_without_primitives = sorted(
        domain_id
        for domain_id, primitive_ids in normalized_primitives_by_domain.items()
        if not primitive_ids
    )

    recommended_holds = _build_recommended_holds(
        profiles=profiles,
        invalid_domains=invalid_domains,
        missing_domain_refs=missing_domain_refs,
    )

    return {
        "schema_version": "1.0",
        "summary": "public_surface_governance",
        "total_domains": observed_domain_count,
        "routable_domains": routable_domains,
        "quarantined_domains": quarantined_domains,
        "invalid_domains": invalid_domains,
        "total_primitives": len(primitives),
        "primitives_by_domain": normalized_primitives_by_domain,
        "primitives_with_missing_domain_refs": missing_domain_refs,
        "domains_without_primitives": domains_without_primitives,
        "approval_class_counts": dict(sorted(approval_counts.items())),
        "recommended_holds": recommended_holds,
    }


def _load_report_domains(
    domain_profiles_path: str | Path,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], int]:
    path = Path(domain_profiles_path)
    try:
        profiles = public_surfaces.load_domain_profiles(path)
    except public_surfaces.PublicSurfaceValidationError as loader_error:
        return _load_domains_row_by_row(path, loader_error)
    return profiles, [], len(profiles)


def _load_domains_row_by_row(
    path: Path,
    loader_error: public_surfaces.PublicSurfaceValidationError,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], int]:
    try:
        with path.open(encoding="utf-8") as handle:
            document = yaml.safe_load(handle) or {}
    except yaml.YAMLError as exc:
        return {}, [_invalid_document(str(exc))], 0

    if not isinstance(document, Mapping) or not isinstance(document.get("domain_profiles"), list):
        return {}, [_invalid_document(str(loader_error))], 0

    profiles: dict[str, dict[str, Any]] = {}
    invalid_domains: list[dict[str, Any]] = []
    rows = document["domain_profiles"]
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping):
            invalid_domains.append(
                {
                    "domain_id": f"row_{index}",
                    "row_index": index,
                    "error": "invalid_domain_profile_row:expected_mapping",
                }
            )
            continue

        profile = _normalize_domain_profile(row)
        try:
            public_surfaces.validate_domain_profile(profile)
        except public_surfaces.PublicSurfaceValidationError as exc:
            invalid_domains.append(
                {
                    "domain_id": str(profile.get("domain_id") or f"row_{index}"),
                    "row_index": index,
                    "error": str(exc),
                }
            )
            continue

        domain_id = str(profile["domain_id"])
        if domain_id in profiles:
            invalid_domains.append(
                {
                    "domain_id": domain_id,
                    "row_index": index,
                    "error": f"duplicate_domain_id:{domain_id}",
                }
            )
            continue
        profiles[domain_id] = profile

    if not invalid_domains:
        invalid_domains.append(_invalid_document(str(loader_error)))

    return profiles, _sort_invalid_domains(invalid_domains), len(rows)


def _build_recommended_holds(
    *,
    profiles: Mapping[str, Mapping[str, Any]],
    invalid_domains: list[dict[str, Any]],
    missing_domain_refs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    holds: list[dict[str, Any]] = []

    for domain_id in sorted(profiles):
        profile = profiles[domain_id]
        lifecycle_state = _domain_lifecycle_state(profile)
        approval_class = _domain_approval_class(profile)
        if lifecycle_state == "quarantined" or approval_class == "quarantined":
            holds.append(
                {
                    "subject_type": "domain",
                    "subject_id": domain_id,
                    "reason_code": "domain_quarantined",
                }
            )
        elif not public_surfaces.is_domain_routable(profile):
            holds.append(
                {
                    "subject_type": "domain",
                    "subject_id": domain_id,
                    "reason_code": "domain_not_routable",
                    "detail": f"lifecycle_state:{lifecycle_state}",
                }
            )

    for invalid_domain in invalid_domains:
        holds.append(
            {
                "subject_type": "domain",
                "subject_id": invalid_domain["domain_id"],
                "reason_code": "invalid_domain_profile",
                "detail": invalid_domain["error"],
            }
        )

    for gap in missing_domain_refs:
        holds.append(
            {
                "subject_type": "primitive",
                "subject_id": gap["primitive_id"],
                "reason_code": "unknown_domain_refs",
                "domain_ids": list(gap["domain_ids"]),
            }
        )

    return sorted(
        holds,
        key=lambda row: (
            str(row["subject_type"]),
            str(row["subject_id"]),
            str(row["reason_code"]),
            str(row.get("detail", "")),
        ),
    )


def _normalize_domain_profile(record: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(record)
    if "lifecycle_state" not in normalized and "status" in normalized:
        normalized["lifecycle_state"] = normalized["status"]
    if "approval_class" not in normalized and "required_approval_class" in normalized:
        normalized["approval_class"] = normalized["required_approval_class"]
    return normalized


def _domain_lifecycle_state(profile: Mapping[str, Any]) -> str:
    return str(profile.get("lifecycle_state") or profile.get("status") or "")


def _domain_approval_class(profile: Mapping[str, Any]) -> str:
    return str(profile.get("approval_class") or profile.get("required_approval_class") or "")


def _invalid_document(error: str) -> dict[str, Any]:
    return {
        "domain_id": "domain_profiles_document",
        "row_index": 0,
        "error": error,
    }


def _sort_invalid_domains(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (
            str(row["domain_id"]),
            int(row["row_index"]),
            str(row["error"]),
        ),
    )
