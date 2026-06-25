from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.retention.dispatch import plan_dispatch
from app.retention.identity import sha256_hex
from app.retention.jsonl_store import stable_json_dumps
from app.retention.transitions import load_latest_contact_snapshot

from . import core


APPROVED_RELEASE_STATES = {"exported", "published"}
NO_SEND_ADAPTER = "local-noop"
NO_SEND_STATUS = "prepared_no_send"
DELIVERY_CANDIDATE_RECORD_TYPE = "letters_of_light_delivery_candidate"
DELIVERY_PREPARATION_RECORD_TYPE = "letters_of_light_delivery_preparation"


class DeliveryPreparationError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _repo_root() -> Path:
    override = os.environ.get("SIGNAL_AGENT_ROOT")
    if override:
        return Path(override).expanduser().resolve(strict=False)
    return Path(__file__).resolve().parents[3]


def _letters_root(repo_root: Path) -> Path:
    return repo_root / "data" / "state" / "letters_of_light"


def _safe_letter_id(letter_id: str) -> str:
    normalized = str(letter_id or "").strip()
    if not normalized or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for char in normalized):
        raise DeliveryPreparationError("release_input_invalid")
    return normalized


def _read_json(path: Path, *, missing_code: str, malformed_code: str) -> dict[str, Any]:
    if not path.exists():
        raise DeliveryPreparationError(missing_code)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise DeliveryPreparationError(malformed_code) from exc
    if not isinstance(payload, dict):
        raise DeliveryPreparationError(malformed_code)
    return payload


def _safe_release_view(release: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    letter_id = str(release["letter_id"])
    campaign_id = str(release.get("campaign_id") or manifest.get("campaign_id") or "")
    canonical_url = str(release.get("canonical_url") or manifest.get("canonical_url") or "")
    release_id = campaign_id or f"letters_of_light:{letter_id}"
    release_state = str(release.get("release_state") or "")
    content_reference = f"letters_of_light:{letter_id}"
    return {
        "letter_id": letter_id,
        "release_id": release_id,
        "campaign_id": campaign_id or None,
        "release_state": release_state,
        "canonical_url": canonical_url or None,
        "content_reference": content_reference,
        "title": str(release.get("title") or ""),
    }


def resolve_approved_release(
    letter_id: str,
    *,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    safe_letter_id = _safe_letter_id(letter_id)
    root = (repo_root or _repo_root()).resolve(strict=False)
    release_dir = _letters_root(root) / safe_letter_id
    release = _read_json(
        release_dir / "release.json",
        missing_code="release_input_missing",
        malformed_code="release_input_malformed",
    )
    manifest = _read_json(
        release_dir / "release_export" / "asset_manifest.json",
        missing_code="release_export_missing",
        malformed_code="release_export_malformed",
    )

    if str(release.get("letter_id") or "") != safe_letter_id:
        raise DeliveryPreparationError("release_input_ambiguous")
    if manifest.get("letter_id") and str(manifest.get("letter_id")) != safe_letter_id:
        raise DeliveryPreparationError("release_input_ambiguous")
    if release.get("campaign_id") and manifest.get("campaign_id") and release.get("campaign_id") != manifest.get("campaign_id"):
        raise DeliveryPreparationError("release_input_ambiguous")
    if release.get("approved") is not True:
        raise DeliveryPreparationError("release_not_approved")

    release_state = str(release.get("release_state") or "")
    if release_state not in APPROVED_RELEASE_STATES:
        raise DeliveryPreparationError("release_not_exported")

    safe_release = _safe_release_view(release, manifest)
    safe_release["release_basis_hash"] = f"sha256:{sha256_hex(stable_json_dumps(safe_release))}"
    return safe_release


def _no_send_guard() -> dict[str, Any]:
    guard = {
        "adapter": NO_SEND_ADAPTER,
        "sent": False,
        "no_network": True,
        "external_action_allowed": False,
        "provider_payload_created": False,
    }
    if guard["adapter"] != NO_SEND_ADAPTER or guard["sent"] is not False or guard["no_network"] is not True:
        raise DeliveryPreparationError("no_send_boundary_violated")
    return guard


def _candidate_id(
    *,
    release_id: str,
    contact_id: str,
    contact_version: int,
    content_reference: str,
) -> str:
    material = "|".join([release_id, contact_id, str(contact_version), content_reference, NO_SEND_ADAPTER])
    return f"dpc_{sha256_hex(material)[:16]}"


def _queue_id(
    *,
    release_id: str,
    contact_id: str,
    contact_version: int,
    source_dispatch_id: str,
) -> str:
    material = "|".join([release_id, contact_id, str(contact_version), source_dispatch_id, NO_SEND_ADAPTER])
    return f"que_lol_{sha256_hex(material)[:16]}"


def _iter_subscribers(config: core.SubscriberConfig | None) -> list[dict[str, Any]]:
    with core._connect(config) as conn:
        rows = conn.execute(
            """
            SELECT
                contact_id,
                status,
                consent_version
            FROM subscribers
            ORDER BY contact_id
            """
        ).fetchall()
    return [
        {
            "contact_id": str(row["contact_id"] or ""),
            "status": str(row["status"] or ""),
            "consent_version": int(row["consent_version"] or 0),
        }
        for row in rows
    ]


def _exclude(
    *,
    contact_id: str | None,
    reason_code: str,
    current_state: str | None = None,
    consent_status: str | None = None,
    dispatch_reason_codes: list[str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "contact_id": contact_id or None,
        "result": "excluded",
        "reason_code": reason_code,
    }
    if current_state:
        payload["current_state"] = current_state
    if consent_status:
        payload["consent_status"] = consent_status
    if dispatch_reason_codes:
        payload["dispatch_reason_codes"] = list(dispatch_reason_codes)
    return payload


def _candidate_from_snapshot(
    *,
    release: dict[str, Any],
    contact_id: str,
    contact_snapshot: dict[str, Any],
    dispatch_plan: dict[str, Any],
) -> dict[str, Any]:
    contact_version = int(contact_snapshot.get("contact_version", 0) or 0)
    source_dispatch_id = str(dispatch_plan.get("dispatch_id") or "")
    content_reference = str(release["content_reference"])
    guard = _no_send_guard()
    candidate = {
        "record_type": DELIVERY_CANDIDATE_RECORD_TYPE,
        "schema_version": "1.0",
        "candidate_id": _candidate_id(
            release_id=str(release["release_id"]),
            contact_id=contact_id,
            contact_version=contact_version,
            content_reference=content_reference,
        ),
        "queue_id": _queue_id(
            release_id=str(release["release_id"]),
            contact_id=contact_id,
            contact_version=contact_version,
            source_dispatch_id=source_dispatch_id,
        ),
        "release_id": release["release_id"],
        "letter_id": release["letter_id"],
        "campaign_id": release["campaign_id"],
        "content_reference": content_reference,
        "canonical_url": release["canonical_url"],
        "contact_id": contact_id,
        "contact_version": contact_version,
        "source_dispatch_id": source_dispatch_id,
        "retention_dispatch": {
            "decision": dispatch_plan.get("decision"),
            "dispatch_type": dispatch_plan.get("dispatch_type"),
            "channel": dispatch_plan.get("channel"),
            "template_key": dispatch_plan.get("template_key"),
            "reason_codes": list(dispatch_plan.get("reason_codes") or []),
        },
        "consent_basis": {
            "channel": "email",
            "email_marketing_status": str(contact_snapshot.get("consent", {}).get("email_marketing_status") or ""),
            "rule": "existing_retention_dispatch_gate",
        },
        "status": NO_SEND_STATUS,
        **guard,
    }
    candidate["candidate_hash"] = f"sha256:{sha256_hex(stable_json_dumps(candidate))}"
    return candidate


def _preparation_basis_hash(payload: dict[str, Any]) -> str:
    material = {
        key: value
        for key, value in payload.items()
        if key not in {"preparation_basis_hash"}
    }
    return f"sha256:{sha256_hex(stable_json_dumps(material))}"


def prepare_release_delivery(
    letter_id: str,
    *,
    subscriber_config: core.SubscriberConfig | None = None,
    retention_repo_root: Path | None = None,
    release_repo_root: Path | None = None,
) -> dict[str, Any]:
    release_root = (release_repo_root or retention_repo_root or _repo_root()).resolve(strict=False)
    retention_root = (retention_repo_root or release_root).resolve(strict=False)
    release = resolve_approved_release(letter_id, repo_root=release_root)

    try:
        subscribers = _iter_subscribers(subscriber_config)
    except core.SubscriberCoreError as exc:
        raise DeliveryPreparationError("subscriber_storage_unverified") from exc

    candidates: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    confirmed_private_count = 0

    for subscriber in subscribers:
        contact_id = subscriber["contact_id"]
        status = subscriber["status"]
        if status != "confirmed":
            exclusions.append(
                _exclude(
                    contact_id=contact_id,
                    reason_code="private_status_not_confirmed",
                )
            )
            continue

        confirmed_private_count += 1
        if not contact_id:
            exclusions.append(_exclude(contact_id=None, reason_code="private_contact_missing"))
            continue

        try:
            contact_snapshot = load_latest_contact_snapshot(contact_id, repo_root=retention_root)
        except Exception as exc:
            raise DeliveryPreparationError("retention_state_unverified") from exc
        if not contact_snapshot:
            exclusions.append(_exclude(contact_id=contact_id, reason_code="retention_snapshot_missing"))
            continue

        try:
            dispatch_plan = plan_dispatch(contact_snapshot, contact_id=contact_id)
        except Exception as exc:
            raise DeliveryPreparationError("retention_dispatch_unverified") from exc
        current_state = str(contact_snapshot.get("current_state") or "")
        consent_status = str(contact_snapshot.get("consent", {}).get("email_marketing_status") or "")
        if dispatch_plan.get("decision") != "planned" or dispatch_plan.get("channel") != "email":
            exclusions.append(
                _exclude(
                    contact_id=contact_id,
                    reason_code="retention_dispatch_ineligible",
                    current_state=current_state,
                    consent_status=consent_status,
                    dispatch_reason_codes=list(dispatch_plan.get("reason_codes") or []),
                )
            )
            continue

        candidates.append(
            _candidate_from_snapshot(
                release=release,
                contact_id=contact_id,
                contact_snapshot=contact_snapshot,
                dispatch_plan=dispatch_plan,
            )
        )

    candidates = sorted(candidates, key=lambda item: (str(item["contact_id"]), str(item["candidate_id"])))
    exclusions = sorted(exclusions, key=lambda item: (str(item.get("contact_id") or ""), str(item.get("reason_code") or "")))

    result = {
        "record_type": DELIVERY_PREPARATION_RECORD_TYPE,
        "schema_version": "1.0",
        "clean": True,
        "release": release,
        "adapter": NO_SEND_ADAPTER,
        "status": NO_SEND_STATUS,
        "sent": False,
        "no_network": True,
        "external_action_allowed": False,
        "provider_payload_created": False,
        "total_private_count": len(subscribers),
        "confirmed_private_count": confirmed_private_count,
        "candidate_count": len(candidates),
        "excluded_count": len(exclusions),
        "candidates": candidates,
        "exclusions": exclusions,
    }
    result["preparation_basis_hash"] = _preparation_basis_hash(result)
    return result
