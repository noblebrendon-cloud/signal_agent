from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

from app.utils.io_contract import atomic_write_text

from .confirm import ConfirmationResult
from .errors import ExecutionPlanError
from .normalize import NormalizedProposal
from .policy import PolicyDecision
from .proposal import dump_canonical_json


EXECUTION_PLAN_SCHEMA_PATH = Path(__file__).resolve().parent / "schemas" / "execution_plan.v1.json"


@dataclass(frozen=True)
class PlanVerificationResult:
    clean: bool
    issues: list[str]
    plan_id: str | None
    plan_hash: str | None
    recomputed_plan_hash: str | None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _default_session_id(normalized: NormalizedProposal) -> str:
    return f"session.{normalized.proposal_hash.split(':', 1)[1][:12]}"


def _default_plan_id(normalized: NormalizedProposal, session_id: str) -> str:
    hash_suffix = normalized.proposal_hash.split(":", 1)[1][:12]
    session_suffix = session_id.split(".", 1)[-1][:24]
    return f"plan.{session_suffix}.{hash_suffix}"


@lru_cache(maxsize=1)
def _execution_plan_validator() -> Draft202012Validator:
    try:
        schema = json.loads(EXECUTION_PLAN_SCHEMA_PATH.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ExecutionPlanError(f"Unable to read execution plan schema: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ExecutionPlanError(f"Execution plan schema is malformed JSON: {exc}") from exc

    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        raise ExecutionPlanError(f"Execution plan schema is invalid: {exc}") from exc

    return Draft202012Validator(schema)


def _format_error_path(parts: tuple[object, ...]) -> str:
    if not parts:
        return "$"
    rendered: list[str] = ["$"]
    for part in parts:
        if isinstance(part, int):
            rendered.append(f"[{part}]")
        else:
            rendered.append(f".{part}")
    return "".join(rendered)


def _validate_plan_shape(plan: dict) -> list[str]:
    validator = _execution_plan_validator()
    errors = sorted(validator.iter_errors(plan), key=lambda err: list(err.absolute_path))
    return [
        f"{_format_error_path(tuple(error.absolute_path))}: {error.message}"
        for error in errors
    ]


def _decision_allows_plan(policy_decision: PolicyDecision) -> bool:
    return policy_decision.decision in {"allow", "require_confirmation"}


def _confirmation_allows_plan(
    policy_decision: PolicyDecision,
    confirmation_result: ConfirmationResult,
) -> tuple[bool, list[str]]:
    issues: list[str] = []
    if confirmation_result.proposal_hash != policy_decision.proposal_hash:
        issues.append("confirmation_result proposal_hash does not match policy decision proposal_hash.")

    if policy_decision.confirmation_required != confirmation_result.required:
        issues.append("confirmation_result.required does not match policy decision confirmation_required.")

    if policy_decision.confirmation_mode != confirmation_result.mode:
        issues.append("confirmation_result.mode does not match policy decision confirmation_mode.")

    if policy_decision.confirmation_required and not confirmation_result.clean:
        issues.append("policy requires clean exact-hash confirmation before plan creation.")

    return (not issues, issues)


def _build_operations(normalized: NormalizedProposal) -> list[dict]:
    operations = normalized.proposal.get("operations", [])
    if not isinstance(operations, list):
        raise ExecutionPlanError("Normalized proposal operations must be a list.")
    return json.loads(dump_canonical_json({"operations": operations}))["operations"]


def canonical_plan_json(plan: dict) -> str:
    """Render execution plans with deterministic JSON formatting."""

    return dump_canonical_json(plan)


def compute_plan_hash(plan_without_plan_hash: dict) -> str:
    """Compute a stable plan hash excluding the plan_hash field itself."""

    if type(plan_without_plan_hash) is not dict:
        raise ExecutionPlanError("Execution plan hash input must be a plain dict.")

    material = dict(plan_without_plan_hash)
    material.pop("plan_hash", None)

    import hashlib

    canonical_json = canonical_plan_json(material)
    return f"sha256:{hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()}"


def seal_execution_plan(plan: dict) -> dict:
    """Return a sealed execution plan with a deterministic plan_hash."""

    if type(plan) is not dict:
        raise ExecutionPlanError("Execution plan payload must be a plain dict.")

    payload = dict(plan)
    payload["plan_hash"] = compute_plan_hash(payload)
    sealed_plan = json.loads(canonical_plan_json(payload))
    issues = _validate_plan_shape(sealed_plan)
    if issues:
        raise ExecutionPlanError(
            f"Execution plan schema validation failed: {'; '.join(issues)}"
        )
    return sealed_plan


def build_execution_plan(
    normalized: NormalizedProposal,
    policy_decision: PolicyDecision,
    confirmation_result: ConfirmationResult,
    *,
    session_id: str | None = None,
) -> dict:
    """Build a sealed execution plan from normalized input, policy, and confirmation."""

    if not normalized.path_validation.clean:
        raise ExecutionPlanError(
            f"Normalized proposal path validation is not clean: {'; '.join(normalized.path_validation.errors)}"
        )
    if not policy_decision.clean:
        raise ExecutionPlanError(
            f"Policy decision is not clean: {policy_decision.reason_code}: {'; '.join(policy_decision.issues)}"
        )
    if not _decision_allows_plan(policy_decision):
        raise ExecutionPlanError(
            f"Policy decision does not allow plan creation: {policy_decision.reason_code}"
        )

    confirmation_ok, confirmation_issues = _confirmation_allows_plan(
        policy_decision,
        confirmation_result,
    )
    if not confirmation_ok:
        raise ExecutionPlanError(
            f"Confirmation is not valid for plan creation: {'; '.join(confirmation_issues)}"
        )

    resolved_session_id = session_id or _default_session_id(normalized)
    plan = {
        "schema_version": "execution_plan.v1",
        "plan_id": _default_plan_id(normalized, resolved_session_id),
        "created_at": _utc_now_iso(),
        "session_id": resolved_session_id,
        "proposal_id": str(normalized.proposal["proposal_id"]),
        "proposal_hash": normalized.proposal_hash,
        "proposal_canonical": normalized.canonical_json,
        "policy_hash": policy_decision.policy_hash,
        "decision": policy_decision.decision,
        "matched_binding_id": policy_decision.matched_binding_id,
        "effective_risk": policy_decision.effective_risk,
        "confirmation": {
            "required": confirmation_result.required,
            "mode": confirmation_result.mode,
            "proposal_hash": confirmation_result.proposal_hash,
            "supplied_hash": confirmation_result.supplied_hash,
            "matched": confirmation_result.matched,
            "reason_code": confirmation_result.reason_code,
            "issues": list(confirmation_result.issues),
        },
        "network_allowed": policy_decision.network_allowed,
        "privilege_escalation_allowed": policy_decision.privilege_escalation_allowed,
        "declared_reads": list(policy_decision.declared_reads),
        "declared_writes": list(policy_decision.declared_writes),
        "operations": _build_operations(normalized),
        "plan_hash": "sha256:" + ("0" * 64),
    }
    return seal_execution_plan(plan)


def verify_execution_plan(plan: dict) -> PlanVerificationResult:
    """Verify a sealed execution plan by schema and recomputed plan_hash."""

    if type(plan) is not dict:
        return PlanVerificationResult(
            clean=False,
            issues=["execution plan must be a plain dict."],
            plan_id=None,
            plan_hash=None,
            recomputed_plan_hash=None,
        )

    issues = _validate_plan_shape(plan)
    recomputed_plan_hash = compute_plan_hash(plan)
    actual_plan_hash = plan.get("plan_hash")
    if not isinstance(actual_plan_hash, str):
        issues.append("$.plan_hash: plan_hash must be a string.")
    elif actual_plan_hash != recomputed_plan_hash:
        issues.append(
            f"plan_hash_mismatch:expected={recomputed_plan_hash}:actual={actual_plan_hash}"
        )

    return PlanVerificationResult(
        clean=not issues,
        issues=issues,
        plan_id=plan.get("plan_id") if isinstance(plan.get("plan_id"), str) else None,
        plan_hash=actual_plan_hash if isinstance(actual_plan_hash, str) else None,
        recomputed_plan_hash=recomputed_plan_hash,
    )


def write_sealed_plan(path: Path, plan: dict) -> Path:
    """Write a sealed plan JSON file atomically without executing anything."""

    verification = verify_execution_plan(plan)
    if not verification.clean:
        raise ExecutionPlanError(
            f"Execution plan is not clean and cannot be written: {'; '.join(verification.issues)}"
        )

    try:
        atomic_write_text(Path(path), canonical_plan_json(plan))
    except OSError as exc:
        raise ExecutionPlanError(f"Unable to write sealed execution plan: {exc}") from exc
    return Path(path)
