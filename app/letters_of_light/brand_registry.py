"""
app/letters_of_light/brand_registry.py - Multi-brand profile registry.

Brand configs are repo-local public configuration. Runtime credentials and token
files stay outside the repo and are resolved only through credential profile
keys inside publisher code. API/UI helpers in this module deliberately omit
credential, token, and secret fields.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional


DEFAULT_BRAND_ID = "letters_of_light"
VALID_STATUSES = {"active", "quarantined", "internal_only"}
PUBLIC_TARGETS = ("site", "youtube", "facebook", "instagram", "x", "linkedin", "threads", "substack")
DESTINATION_SURFACE_STATUSES = {
    "draft_only",
    "configured_manual_publish",
    "configured_uncredentialed",
    "credentialed_unverified",
    "publish_enabled",
    "disabled",
    "provisioning_required",
}
DESTINATION_SURFACE_SECRET_KEYS = {
    "access_token",
    "api_key",
    "client_secret",
    "oauth_token",
    "password",
    "refresh_token",
    "secret",
    "token",
}
REQUIRED_FIELDS = {
    "brand_id",
    "display_name",
    "status",
    "description",
    "primary_domain",
    "website_route_prefix",
    "release_templates",
    "allowed_output_types",
    "required_review_fields",
    "available_release_targets",
    "credential_profile_key",
    "visual",
    "source_evidence_requirements",
    "created_at",
    "updated_at",
}


class BrandConfigError(ValueError):
    """Raised when a brand profile is missing or invalid."""


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _runtime_root() -> Path:
    override = os.environ.get("SIGNAL_AGENT_ROOT")
    if override:
        return Path(override)
    return _repo_root()


def brand_config_dir() -> Path:
    runtime_dir = _runtime_root() / "config" / "brands"
    if runtime_dir.exists() and any(runtime_dir.glob("*.json")):
        return runtime_dir
    return _repo_root() / "config" / "brands"


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BrandConfigError(f"invalid brand JSON: {path}") from exc
    if not isinstance(data, dict):
        raise BrandConfigError(f"brand config must be an object: {path}")
    return data


def _validate_brand_id(value: str) -> None:
    if not re.fullmatch(r"[a-z0-9_]+", value or ""):
        raise BrandConfigError(f"invalid brand_id: {value}")


def _normalize_review_fields(value: Any) -> List[Dict[str, str]]:
    if not isinstance(value, list):
        raise BrandConfigError("required_review_fields must be a list")
    normalized: List[Dict[str, str]] = []
    for item in value:
        if isinstance(item, str):
            field = item.strip()
            label = field.replace("_", " ").title()
            description = ""
        elif isinstance(item, dict):
            field = str(item.get("field") or "").strip()
            label = str(item.get("label") or field.replace("_", " ").title()).strip()
            description = str(item.get("description") or "").strip()
        else:
            raise BrandConfigError("required_review_fields entries must be objects or strings")
        if not field:
            raise BrandConfigError("required review field is missing field")
        normalized.append({"field": field, "label": label or field, "description": description})
    return normalized


def _normalize_string_list(value: Any, field: str) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise BrandConfigError(f"{field} must be a list")
    return [str(item).strip() for item in value if str(item).strip()]


def _normalize_destination_surfaces(value: Any, brand_id: str) -> Dict[str, Dict[str, Any]]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise BrandConfigError(f"{brand_id} destination_surfaces must be an object")

    normalized: Dict[str, Dict[str, Any]] = {}
    for key, raw in value.items():
        surface_key = str(key or "").strip()
        if not re.fullmatch(r"[a-z0-9_]+", surface_key):
            raise BrandConfigError(f"{brand_id} invalid destination surface key: {surface_key}")
        if not isinstance(raw, dict):
            raise BrandConfigError(f"{brand_id} destination surface {surface_key} must be an object")
        forbidden = sorted(DESTINATION_SURFACE_SECRET_KEYS & {str(item).lower() for item in raw})
        if forbidden:
            raise BrandConfigError(
                f"{brand_id} destination surface {surface_key} contains secret-bearing fields: {', '.join(forbidden)}"
            )

        surface_ref = str(raw.get("surface_ref") or surface_key).strip()
        if surface_ref != surface_key:
            raise BrandConfigError(f"{brand_id} destination surface {surface_key} surface_ref must match its key")

        status = str(raw.get("status") or "").strip()
        if status not in DESTINATION_SURFACE_STATUSES:
            raise BrandConfigError(
                f"{brand_id} destination surface {surface_key} status must be one of {sorted(DESTINATION_SURFACE_STATUSES)}"
            )

        direct_allowed = bool(raw.get("direct_system_publication_allowed", False))
        if direct_allowed and status != "publish_enabled":
            raise BrandConfigError(
                f"{brand_id} destination surface {surface_key} cannot allow direct publication unless status is publish_enabled"
            )

        credentials_exist = bool(raw.get("credentials_exist", False))
        credential_state = str(raw.get("credential_state") or "none").strip() or "none"
        if credentials_exist and credential_state in {"none", "missing", "not_required"}:
            raise BrandConfigError(
                f"{brand_id} destination surface {surface_key} has credentials_exist=true with credential_state={credential_state}"
            )

        normalized[surface_key] = {
            "surface_ref": surface_ref,
            "display_name": str(raw.get("display_name") or surface_ref.replace("_", " ").title()).strip(),
            "platform": str(raw.get("platform") or surface_ref).strip(),
            "status": status,
            "public_url": str(raw.get("public_url") or "").strip(),
            "platform_account_id": str(raw.get("platform_account_id") or "").strip(),
            "adapter_ref": str(raw.get("adapter_ref") or "").strip(),
            "adapter_exists": bool(raw.get("adapter_exists", False)),
            "credential_state": credential_state,
            "credentials_exist": credentials_exist,
            "manual_publication_possible": bool(raw.get("manual_publication_possible", False)),
            "direct_system_publication_allowed": direct_allowed,
            "content_constraints": _normalize_string_list(raw.get("content_constraints"), "content_constraints"),
            "next_operator_action": str(raw.get("next_operator_action") or "").strip(),
            "notes": _normalize_string_list(raw.get("notes"), "notes"),
        }
    return normalized


def _validate_brand(data: Dict[str, Any], path: Path) -> Dict[str, Any]:
    missing = sorted(REQUIRED_FIELDS - set(data))
    if missing:
        raise BrandConfigError(f"{path} missing required fields: {', '.join(missing)}")

    brand_id = str(data.get("brand_id") or "").strip()
    _validate_brand_id(brand_id)
    if path.stem != brand_id:
        raise BrandConfigError(f"{path} filename must match brand_id {brand_id}")

    status = str(data.get("status") or "").strip()
    if status not in VALID_STATUSES:
        raise BrandConfigError(f"{brand_id} status must be one of {sorted(VALID_STATUSES)}")

    if not isinstance(data.get("release_templates"), list):
        raise BrandConfigError(f"{brand_id} release_templates must be a list")
    if not isinstance(data.get("allowed_output_types"), list):
        raise BrandConfigError(f"{brand_id} allowed_output_types must be a list")
    if not isinstance(data.get("available_release_targets"), dict):
        raise BrandConfigError(f"{brand_id} available_release_targets must be an object")
    if not isinstance(data.get("visual"), dict):
        raise BrandConfigError(f"{brand_id} visual must be an object")
    if not isinstance(data.get("source_evidence_requirements"), dict):
        raise BrandConfigError(f"{brand_id} source_evidence_requirements must be an object")

    targets = {target: bool(data["available_release_targets"].get(target, False)) for target in PUBLIC_TARGETS}
    normalized = dict(data)
    normalized["version"] = str(data.get("version") or "1")
    normalized["required_review_fields"] = _normalize_review_fields(data.get("required_review_fields"))
    normalized["available_release_targets"] = targets
    normalized["destination_surfaces"] = _normalize_destination_surfaces(
        data.get("destination_surfaces"),
        brand_id,
    )
    normalized["allowed_output_types"] = [str(item) for item in data.get("allowed_output_types") or []]
    normalized["config_path"] = str(path)
    return normalized


def load_brand_configs() -> Dict[str, Dict[str, Any]]:
    root = brand_config_dir()
    if not root.exists():
        raise BrandConfigError(f"brand config directory not found: {root}")

    brands: Dict[str, Dict[str, Any]] = {}
    for path in sorted(root.glob("*.json")):
        data = _validate_brand(_read_json(path), path)
        brands[str(data["brand_id"])] = data

    if DEFAULT_BRAND_ID not in brands:
        raise BrandConfigError(f"default brand missing: {DEFAULT_BRAND_ID}")
    return brands


def list_brands() -> List[Dict[str, Any]]:
    return sorted(load_brand_configs().values(), key=lambda item: str(item.get("display_name") or ""))


def get_brand(brand_id: Optional[str] = None) -> Dict[str, Any]:
    normalized = str(brand_id or DEFAULT_BRAND_ID).strip() or DEFAULT_BRAND_ID
    brands = load_brand_configs()
    if normalized not in brands:
        raise BrandConfigError(f"unknown brand_id: {normalized}")
    return brands[normalized]


def brand_version(brand_id: Optional[str] = None) -> str:
    return str(get_brand(brand_id).get("version") or "1")


def _safe_templates(templates: Any) -> List[Dict[str, str]]:
    safe: List[Dict[str, str]] = []
    if not isinstance(templates, list):
        return safe
    for item in templates:
        if not isinstance(item, dict):
            continue
        safe.append(
            {
                "template_id": str(item.get("template_id") or ""),
                "display_name": str(item.get("display_name") or item.get("template_id") or ""),
                "output_type": str(item.get("output_type") or ""),
            }
        )
    return safe


def safe_brand_metadata(brand: Mapping[str, Any] | str | None) -> Dict[str, Any]:
    if isinstance(brand, str) or brand is None:
        brand = get_brand(brand)
    return {
        "brand_id": brand.get("brand_id"),
        "version": brand.get("version") or "1",
        "display_name": brand.get("display_name"),
        "status": brand.get("status"),
        "description": brand.get("description"),
        "primary_domain": brand.get("primary_domain"),
        "website_route_prefix": brand.get("website_route_prefix"),
        "release_tone": brand.get("release_tone", ""),
        "default_caption_style": brand.get("default_caption_style", ""),
        "release_templates": _safe_templates(brand.get("release_templates")),
        "allowed_output_types": list(brand.get("allowed_output_types") or []),
        "required_review_fields": list(brand.get("required_review_fields") or []),
        "available_release_targets": dict(brand.get("available_release_targets") or {}),
        "destination_surfaces": dict(brand.get("destination_surfaces") or {}),
        "visual": dict(brand.get("visual") or {}),
        "theme_defaults": dict(brand.get("theme_defaults") or {}),
        "source_evidence_requirements": dict(brand.get("source_evidence_requirements") or {}),
        "approval_rules": {
            key: value
            for key, value in dict(brand.get("approval_rules") or {}).items()
            if key != "credential_profile_key"
        },
        "moderation_risk_boundary": brand.get("moderation_risk_boundary", ""),
    }


def safe_brand_list() -> List[Dict[str, Any]]:
    return [safe_brand_metadata(brand) for brand in list_brands()]


def status_release_disabled_reason(brand: Mapping[str, Any]) -> str:
    status = str(brand.get("status") or "")
    if status == "quarantined":
        return (
            f"{brand.get('display_name')} is quarantined until purpose, tone, "
            "moderation, and release policy are explicitly mapped."
        )
    if status == "internal_only":
        return f"{brand.get('display_name')} is internal only and cannot create public release jobs."
    if not dict(brand.get("approval_rules") or {}).get("allow_public_publish", True):
        return f"{brand.get('display_name')} is not approved for public release."
    return ""


def required_review_field_keys(brand: Mapping[str, Any]) -> List[str]:
    fields = brand.get("required_review_fields") or []
    return [str(item.get("field") or "") for item in fields if isinstance(item, dict) and item.get("field")]


def missing_review_fields(brand: Mapping[str, Any], review_fields: Optional[Mapping[str, Any]]) -> List[str]:
    values = review_fields if isinstance(review_fields, Mapping) else {}
    missing: List[str] = []
    for field in required_review_field_keys(brand):
        value = values.get(field)
        if value is None or not str(value).strip():
            missing.append(field)
    return missing


def release_blockers(
    brand: Mapping[str, Any] | str | None,
    *,
    review_fields: Optional[Mapping[str, Any]] = None,
    target: Optional[str] = None,
    output_type: str = "project_render",
) -> List[str]:
    config = get_brand(brand) if isinstance(brand, str) or brand is None else dict(brand)
    blockers: List[str] = []

    status_reason = status_release_disabled_reason(config)
    if status_reason:
        blockers.append(status_reason)

    allowed_outputs = {str(item) for item in config.get("allowed_output_types") or []}
    if output_type and output_type not in allowed_outputs:
        blockers.append(f"{config.get('display_name')} does not allow {output_type} public releases.")

    if target:
        targets = dict(config.get("available_release_targets") or {})
        if not bool(targets.get(target, False)):
            blockers.append(f"{config.get('display_name')} does not allow {target} releases.")

    for field in missing_review_fields(config, review_fields):
        label = field.replace("_", " ").title()
        for field_config in config.get("required_review_fields") or []:
            if field_config.get("field") == field:
                label = str(field_config.get("label") or label)
                break
        blockers.append(f"{label} is required before public release.")

    return blockers


def release_requirements_payload(
    brand: Mapping[str, Any] | str | None,
    *,
    review_fields: Optional[Mapping[str, Any]] = None,
    output_type: str = "project_render",
) -> Dict[str, Any]:
    config = get_brand(brand) if isinstance(brand, str) or brand is None else dict(brand)
    blockers = release_blockers(config, review_fields=review_fields, output_type=output_type)
    return {
        "release_enabled": not blockers,
        "disabled_reasons": blockers,
        "required_review_fields": list(config.get("required_review_fields") or []),
        "missing_review_fields": missing_review_fields(config, review_fields),
        "available_release_targets": dict(config.get("available_release_targets") or {}),
        "destination_surfaces": dict(config.get("destination_surfaces") or {}),
    }


def credential_profile_key(brand_id: Optional[str]) -> str:
    return str(get_brand(brand_id).get("credential_profile_key") or "")
