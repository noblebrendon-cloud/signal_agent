"""
Read-only public-surface governance config loading and validation.

This module only reads and validates domain profile YAML and primitive registry
JSONL records. It does not route, emit, approve, post, or mutate files.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml


APPROVAL_CLASSES = frozenset(
    {
        "local_review",
        "human_public_review",
        "human_high_trust_review",
        "quarantined",
    }
)
ROUTABLE_DOMAIN_STATES = frozenset({"active"})

_DOMAIN_ALIAS_FIELDS = {
    "lifecycle_state": "status",
    "approval_class": "required_approval_class",
}
_PRIMITIVE_ALIAS_FIELDS = {"compatible_domains": "compatible_domain_ids"}


class PublicSurfaceValidationError(ValueError):
    """Raised when public-surface config cannot be validated."""


def load_domain_profiles(path: str | Path) -> dict[str, dict[str, Any]]:
    """
    Load and validate public-surface domain profiles from YAML.

    Returns a dictionary keyed by `domain_id`. Records are copied and normalized
    in memory so existing example aliases do not mutate the source file.
    """
    config_path = Path(path)
    document = _load_yaml_mapping(config_path)
    _validate_config_approval_classes(document.get("approval_classes"))

    rows = document.get("domain_profiles")
    if not isinstance(rows, list):
        raise PublicSurfaceValidationError("invalid_domain_profiles:expected_list")

    profiles: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping):
            raise PublicSurfaceValidationError(f"invalid_domain_profile_row:{index}:expected_mapping")
        profile = _normalize_domain_profile(row)
        validate_domain_profile(profile)
        domain_id = profile["domain_id"]
        if domain_id in profiles:
            raise PublicSurfaceValidationError(f"duplicate_domain_id:{domain_id}")
        profiles[domain_id] = profile

    return profiles


def load_primitive_registry(path: str | Path) -> list[dict[str, Any]]:
    """
    Load and validate public-surface primitive registry rows from JSONL.

    Blank lines are ignored. Invalid or non-object rows fail closed with line
    numbers instead of being skipped.
    """
    registry_path = Path(path)
    rows: list[dict[str, Any]] = []

    with registry_path.open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                decoded = json.loads(line)
            except json.JSONDecodeError as exc:
                raise PublicSurfaceValidationError(
                    f"invalid_jsonl_row:{line_number}:{exc.msg}"
                ) from exc
            if not isinstance(decoded, Mapping):
                raise PublicSurfaceValidationError(
                    f"invalid_jsonl_row:{line_number}:expected_object"
                )

            primitive = _normalize_primitive(decoded)
            validate_primitive(primitive)
            rows.append(primitive)

    return rows


def validate_domain_profile(record: Mapping[str, Any]) -> None:
    """Validate one domain profile record without mutating it."""
    profile = _normalize_domain_profile(record)
    _require_text(profile, "domain_id")
    _require_text(profile, "lifecycle_state")

    approval_class = _require_text(profile, "approval_class")
    _validate_approval_class(approval_class)


def validate_primitive(record: Mapping[str, Any]) -> None:
    """Validate one public-surface primitive record without mutating it."""
    primitive = _normalize_primitive(record)
    _require_text(primitive, "primitive_id")
    _require_non_empty_text_list(primitive, "invariant_refs")
    _require_non_empty_text_list(primitive, "compatible_domains")

    approval_class = primitive.get("approval_class")
    if approval_class is not None:
        if not isinstance(approval_class, str) or not approval_class.strip():
            raise PublicSurfaceValidationError("invalid_field:approval_class:expected_text")
        _validate_approval_class(approval_class.strip())


def is_domain_routable(profile: Mapping[str, Any]) -> bool:
    """
    Return whether a validated profile is eligible for later routing admission.

    This is a read-only classification helper. Candidate, held, quarantined, or
    otherwise unknown domain states fail closed.
    """
    normalized = _normalize_domain_profile(profile)
    validate_domain_profile(normalized)
    return (
        normalized["lifecycle_state"] in ROUTABLE_DOMAIN_STATES
        and normalized["approval_class"] != "quarantined"
    )


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as handle:
            decoded = yaml.safe_load(handle) or {}
    except yaml.YAMLError as exc:
        raise PublicSurfaceValidationError(f"invalid_domain_profiles_yaml:{exc}") from exc

    if not isinstance(decoded, Mapping):
        raise PublicSurfaceValidationError("invalid_domain_profiles_yaml:expected_mapping")
    return dict(decoded)


def _validate_config_approval_classes(classes: Any) -> None:
    if classes is None:
        return
    if not isinstance(classes, list):
        raise PublicSurfaceValidationError("invalid_approval_classes:expected_list")

    configured = set(_require_text_value(value, "approval_classes") for value in classes)
    unknown = sorted(configured - APPROVAL_CLASSES)
    if unknown:
        raise PublicSurfaceValidationError(f"unknown_approval_class:{unknown[0]}")


def _normalize_domain_profile(record: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(record)
    for canonical, alias in _DOMAIN_ALIAS_FIELDS.items():
        if canonical not in normalized and alias in normalized:
            normalized[canonical] = normalized[alias]
    return normalized


def _normalize_primitive(record: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(record)
    for canonical, alias in _PRIMITIVE_ALIAS_FIELDS.items():
        if canonical not in normalized and alias in normalized:
            normalized[canonical] = normalized[alias]
    return normalized


def _validate_approval_class(value: str) -> None:
    if value not in APPROVAL_CLASSES:
        raise PublicSurfaceValidationError(f"unknown_approval_class:{value}")


def _require_text(record: Mapping[str, Any], field: str) -> str:
    if field not in record:
        raise PublicSurfaceValidationError(f"missing_required_field:{field}")
    value = record[field]
    if not isinstance(value, str) or not value.strip():
        raise PublicSurfaceValidationError(f"invalid_field:{field}:expected_text")
    return value.strip()


def _require_text_value(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PublicSurfaceValidationError(f"invalid_field:{field}:expected_text")
    return value.strip()


def _require_non_empty_text_list(record: Mapping[str, Any], field: str) -> list[str]:
    if field not in record:
        raise PublicSurfaceValidationError(f"missing_required_field:{field}")
    value = record[field]
    if not isinstance(value, list) or not value:
        raise PublicSurfaceValidationError(f"invalid_field:{field}:expected_non_empty_list")

    normalized = [_require_text_value(item, field) for item in value]
    return normalized
