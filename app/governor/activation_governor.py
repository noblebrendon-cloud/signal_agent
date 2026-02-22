from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

from app.utils.io_contract import append_jsonl_atomic, atomic_write_text

DEFAULT_STATE_PATH = Path("data/state/activation_governor.json")
DEFAULT_EVENT_LOG_PATH = Path("data/state/activation_events.jsonl")
REMEDIATION_HINT_INIT = "run governor.review --init"

_NON_MUTATING_SCOPES = {
    "governor.status",
    "governor.review",
    "governor.override",
    "capture.status",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _utc_now().isoformat().replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("invalid_utc_value")
    normalized = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _is_mutating_scope(scope: str) -> bool:
    return scope not in _NON_MUTATING_SCOPES


def _scope_matches(scope: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        if fnmatchcase(scope, pattern):
            return True
    return False


def _persist_state(state_path: Path, state: dict[str, Any]) -> None:
    payload = json.dumps(state, indent=2, sort_keys=True) + "\n"
    atomic_write_text(state_path, payload)


def load_state(path: Path) -> dict:
    payload = Path(path).read_text(encoding="utf-8")
    loaded = json.loads(payload)
    if not isinstance(loaded, dict):
        raise ValueError("state_root_must_be_object")
    return loaded


def validate_state(state: dict) -> None:
    if not isinstance(state, dict):
        raise ValueError("state_must_be_dict")

    if not isinstance(state.get("enforcement_enabled"), bool):
        raise ValueError("enforcement_enabled_required_bool")

    lock = state.get("lock")
    if not isinstance(lock, dict):
        raise ValueError("lock_required_dict")
    if not isinstance(lock.get("id"), str) or not lock["id"].strip():
        raise ValueError("lock.id_required")
    if not isinstance(lock.get("active"), bool):
        raise ValueError("lock.active_required_bool")
    if not isinstance(lock.get("authorized_scopes"), list) or any(
        not isinstance(item, str) or not item.strip() for item in lock["authorized_scopes"]
    ):
        raise ValueError("lock.authorized_scopes_required")
    lock_expiry = lock.get("expires_at_utc")
    if lock_expiry is not None:
        _parse_utc(lock_expiry)

    baseline = state.get("baseline")
    if not isinstance(baseline, dict):
        raise ValueError("baseline_required_dict")
    watch_roots = baseline.get("watch_roots")
    if not isinstance(watch_roots, list) or any(
        not isinstance(item, str) or not item.strip() for item in watch_roots
    ):
        raise ValueError("baseline.watch_roots_required")
    fingerprint = baseline.get("fingerprint")
    if not isinstance(fingerprint, str) or not fingerprint.startswith("sha256:"):
        raise ValueError("baseline.fingerprint_required")

    override = state.get("override")
    if override is not None:
        if not isinstance(override, dict):
            raise ValueError("override_must_be_dict_if_present")
        token_id = override.get("token_id")
        token_scope = override.get("scope")
        token_reason = override.get("reason")
        token_expires = override.get("expires_at_utc")
        token_used = override.get("used")
        required = (token_id, token_scope, token_reason, token_expires)
        if any(not isinstance(item, str) or not item.strip() for item in required):
            raise ValueError("override_fields_required")
        _parse_utc(token_expires)
        if not isinstance(token_used, bool):
            raise ValueError("override.used_required_bool")


def compute_fingerprint(watch_roots: list[str]) -> str:
    hasher = hashlib.sha256()
    for raw_root in watch_roots:
        root = Path(raw_root)
        root_token = str(root.as_posix())
        hasher.update(f"root:{root_token}\n".encode("utf-8"))

        if not root.exists():
            hasher.update(b"missing\n")
            continue

        files: list[Path] = []
        if root.is_file():
            files = [root]
        else:
            files = sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: p.as_posix())

        for file_path in files:
            if root.is_dir():
                rel = file_path.relative_to(root).as_posix()
            else:
                rel = file_path.name
            hasher.update(f"file:{rel}\n".encode("utf-8"))
            with file_path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(65536), b""):
                    hasher.update(chunk)
            hasher.update(b"\n")
    return f"sha256:{hasher.hexdigest()}"


def append_event(log_path: Path, event: dict) -> None:
    if not isinstance(event, dict):
        raise ValueError("event_must_be_dict")
    append_jsonl_atomic(jsonl_path=log_path, record=event)


def enforce(
    scope: str,
    state_path: Path = DEFAULT_STATE_PATH,
    event_log: Path = DEFAULT_EVENT_LOG_PATH,
) -> dict:
    mutating_scope = _is_mutating_scope(scope)
    base_decision = {
        "decision": "ALLOW",
        "reason": "allowed",
        "lock_id": "",
        "override_token_id": "",
        "drift_status": "unknown",
        "state_fingerprint": "",
        "remediation_hint": "",
    }

    try:
        state = load_state(state_path)
        validate_state(state)
    except Exception:
        if not mutating_scope:
            return {
                **base_decision,
                "decision": "ALLOW",
                "reason": "state_missing_or_invalid_non_mutating",
            }
        decision = {
            **base_decision,
            "decision": "BLOCK",
            "reason": "state_missing_or_invalid",
            "drift_status": "unknown",
            "remediation_hint": REMEDIATION_HINT_INIT,
        }
        append_event(
            event_log,
            {
                "timestamp_utc": _iso_now(),
                "event": "ENFORCE_BLOCKED",
                "scope": scope,
                "reason": decision["reason"],
                "remediation_hint": decision["remediation_hint"],
            },
        )
        return decision

    lock = state["lock"]
    baseline = state["baseline"]
    override = state.get("override")
    enforcement_enabled = state["enforcement_enabled"]
    watch_roots = baseline["watch_roots"]
    baseline_fingerprint = baseline["fingerprint"]
    state_fingerprint = compute_fingerprint(watch_roots)
    drift_status = "ok"

    lock_id = lock.get("id", "")
    override_token_id = ""
    if isinstance(override, dict):
        override_token_id = override.get("token_id", "")

    decision = {
        **base_decision,
        "lock_id": lock_id,
        "override_token_id": override_token_id,
        "drift_status": drift_status,
        "state_fingerprint": state_fingerprint,
    }

    if enforcement_enabled and baseline_fingerprint != state_fingerprint:
        decision["drift_status"] = "detected"
        append_event(
            event_log,
            {
                "timestamp_utc": _iso_now(),
                "event": "DRIFT_DETECTED",
                "scope": scope,
                "lock_id": lock_id,
                "expected_fingerprint": baseline_fingerprint,
                "observed_fingerprint": state_fingerprint,
                "watch_roots": watch_roots,
            },
        )
        if mutating_scope:
            decision["decision"] = "BLOCK"
            decision["reason"] = "drift_detected"
            return decision

    if not mutating_scope:
        decision["decision"] = "ALLOW"
        decision["reason"] = "non_mutating_scope"
        return decision

    if not enforcement_enabled:
        decision["decision"] = "ALLOW"
        decision["reason"] = "enforcement_disabled"
        return decision

    lock_active = bool(lock.get("active", False))
    lock_expires_raw = lock.get("expires_at_utc")
    if lock_active and lock_expires_raw:
        lock_active = _parse_utc(lock_expires_raw) > _utc_now()

    if not lock_active:
        decision["decision"] = "ALLOW"
        decision["reason"] = "lock_inactive_or_expired"
        return decision

    authorized_scopes = lock.get("authorized_scopes", [])
    if _scope_matches(scope, authorized_scopes):
        decision["decision"] = "ALLOW"
        decision["reason"] = "authorized_scope"
        return decision

    override_valid = False
    if isinstance(override, dict):
        token_scope = override.get("scope", "")
        token_expires = override.get("expires_at_utc", "")
        token_used = override.get("used", True)
        if (
            isinstance(token_scope, str)
            and token_scope
            and isinstance(token_expires, str)
            and isinstance(token_used, bool)
            and (not token_used)
            and _scope_matches(scope, [token_scope])
            and _parse_utc(token_expires) > _utc_now()
        ):
            override_valid = True

    if override_valid:
        override["used"] = True
        _persist_state(state_path, state)
        append_event(
            event_log,
            {
                "timestamp_utc": _iso_now(),
                "event": "OVERRIDE_USED",
                "scope": scope,
                "lock_id": lock_id,
                "override_token_id": override.get("token_id"),
                "override_reason": override.get("reason"),
            },
        )
        decision["decision"] = "ALLOW"
        decision["reason"] = "override_used"
        decision["override_token_id"] = override.get("token_id", "")
        return decision

    decision["decision"] = "BLOCK"
    decision["reason"] = "scope_not_authorized_during_lock"
    return decision
