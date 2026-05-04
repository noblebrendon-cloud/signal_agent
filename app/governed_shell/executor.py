from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .errors import AuditLogError, SimulationError, SnapshotError
from .execution_plan import verify_execution_plan
from .logstore import append_audit_event, build_review_event, read_audit_events
from .proposal import dump_canonical_json
from .snapshot import build_snapshot_manifest, verify_snapshot_manifest, write_snapshot_manifest


@dataclass(frozen=True)
class SimulationVerificationResult:
    clean: bool
    issues: list[str]
    receipt_id: str | None
    receipt_hash: str | None
    recomputed_receipt_hash: str | None


def _canonical_receipt_json(receipt: dict) -> str:
    return dump_canonical_json(receipt)


def _deterministic_receipt_id(plan: dict) -> str:
    plan_hash = str(plan["plan_hash"])
    return f"receipt.{plan_hash.split(':', 1)[1][:12]}"


def _logical_snapshot_ref(snapshot: dict) -> str:
    return f"data/state/governed_shell/snapshots/{snapshot['snapshot_id']}.json"


def _logical_receipt_ref(plan: dict) -> str:
    return f"data/state/governed_shell/receipts/{_deterministic_receipt_id(plan)}.json"


def _next_event_index(audit_path: Path) -> int:
    if not audit_path.exists():
        return 0
    return len(read_audit_events(audit_path))


def _append_simulation_event(
    audit_path: Path,
    *,
    plan: dict,
    snapshot: dict,
    event_type: str,
    status: str,
    decision_code: str,
    details: dict,
) -> dict:
    event = build_review_event(
        session_id=str(plan["session_id"]),
        event_index=_next_event_index(audit_path),
        timestamp_utc=str(snapshot["created_at"]),
        proposal_id=str(plan["proposal_id"]),
        proposal_hash=str(plan["proposal_hash"]),
        policy_hash=str(plan["policy_hash"]),
        risk_level=str(plan["effective_risk"]),
        decision_code=decision_code,
        status=status,
        details=details,
        event_type=event_type,
        plan_id=str(plan["plan_id"]),
        plan_hash=str(plan["plan_hash"]),
        snapshot_ref=_logical_snapshot_ref(snapshot),
        receipt_ref=_logical_receipt_ref(plan),
    )
    return append_audit_event(audit_path, event)


def compute_receipt_hash(receipt_without_receipt_hash: dict) -> str:
    """Compute a stable simulation receipt hash excluding the receipt_hash field itself."""

    if type(receipt_without_receipt_hash) is not dict:
        raise SimulationError("Simulation receipt hash input must be a plain dict.")

    material = dict(receipt_without_receipt_hash)
    material.pop("receipt_hash", None)

    import hashlib

    canonical_json = _canonical_receipt_json(material)
    return f"sha256:{hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()}"


def build_simulation_receipt(plan: dict, snapshot: dict) -> dict:
    """Build a deterministic simulation-only receipt from a sealed plan and snapshot."""

    plan_verification = verify_execution_plan(plan)
    if not plan_verification.clean:
        raise SimulationError(
            f"Execution plan is not clean and cannot be simulated: {'; '.join(plan_verification.issues)}"
        )

    snapshot_verification = verify_snapshot_manifest(snapshot)
    if not snapshot_verification.clean:
        raise SimulationError(
            f"Snapshot manifest is not clean and cannot produce a receipt: {'; '.join(snapshot_verification.issues)}"
        )

    payload = {
        "schema_version": "simulation_receipt.v1",
        "receipt_id": _deterministic_receipt_id(plan),
        "created_at": str(snapshot["created_at"]),
        "mode": "simulation_only",
        "plan_id": str(plan["plan_id"]),
        "plan_hash": str(plan["plan_hash"]),
        "proposal_hash": str(plan["proposal_hash"]),
        "policy_hash": str(plan["policy_hash"]),
        "matched_binding_id": str(plan["matched_binding_id"]),
        "effective_risk": str(plan["effective_risk"]),
        "snapshot_hash": str(snapshot["snapshot_hash"]),
        "status": "simulated",
        "executed": False,
        "powershell_invoked": False,
        "network_accessed": False,
        "declared_reads": json.loads(dump_canonical_json({"value": plan["declared_reads"]}))["value"],
        "declared_writes": json.loads(dump_canonical_json({"value": plan["declared_writes"]}))["value"],
        "observed_writes": [],
        "receipt_hash": "sha256:" + ("0" * 64),
    }
    payload["receipt_hash"] = compute_receipt_hash(payload)
    receipt = json.loads(_canonical_receipt_json(payload))
    verification = verify_simulation_receipt(receipt)
    if not verification.clean:
        raise SimulationError(
            f"Simulation receipt verification failed after creation: {'; '.join(verification.issues)}"
        )
    return receipt


def verify_simulation_receipt(receipt: dict) -> SimulationVerificationResult:
    """Verify a simulation-only receipt by shape and recomputed hash."""

    if type(receipt) is not dict:
        return SimulationVerificationResult(
            clean=False,
            issues=["simulation receipt must be a plain dict."],
            receipt_id=None,
            receipt_hash=None,
            recomputed_receipt_hash=None,
        )

    issues: list[str] = []
    required_strings = (
        "schema_version",
        "receipt_id",
        "created_at",
        "mode",
        "plan_id",
        "plan_hash",
        "proposal_hash",
        "policy_hash",
        "matched_binding_id",
        "effective_risk",
        "snapshot_hash",
        "status",
        "receipt_hash",
    )
    for key in required_strings:
        if not isinstance(receipt.get(key), str):
            issues.append(f"{key} must be a string.")

    if receipt.get("schema_version") != "simulation_receipt.v1":
        issues.append("schema_version must be 'simulation_receipt.v1'.")
    if receipt.get("mode") != "simulation_only":
        issues.append("mode must be 'simulation_only'.")
    if receipt.get("status") != "simulated":
        issues.append("status must be 'simulated'.")
    if receipt.get("executed") is not False:
        issues.append("executed must be false.")
    if receipt.get("powershell_invoked") is not False:
        issues.append("powershell_invoked must be false.")
    if receipt.get("network_accessed") is not False:
        issues.append("network_accessed must be false.")
    if receipt.get("observed_writes") != []:
        issues.append("observed_writes must be an empty list in simulation-only mode.")
    if not isinstance(receipt.get("declared_reads"), list):
        issues.append("declared_reads must be a list.")
    if not isinstance(receipt.get("declared_writes"), list):
        issues.append("declared_writes must be a list.")

    recomputed_receipt_hash = compute_receipt_hash(receipt)
    receipt_hash = receipt.get("receipt_hash")
    if isinstance(receipt_hash, str):
        if receipt_hash != recomputed_receipt_hash:
            issues.append(
                f"receipt_hash_mismatch:expected={recomputed_receipt_hash}:actual={receipt_hash}"
            )
    else:
        issues.append("receipt_hash must be a string.")

    return SimulationVerificationResult(
        clean=not issues,
        issues=issues,
        receipt_id=receipt.get("receipt_id") if isinstance(receipt.get("receipt_id"), str) else None,
        receipt_hash=receipt_hash if isinstance(receipt_hash, str) else None,
        recomputed_receipt_hash=recomputed_receipt_hash,
    )


def simulate_plan(
    plan: dict,
    *,
    audit_path: Path | None = None,
    snapshot_dir: Path | None = None,
) -> dict:
    """Simulate a sealed plan without executing it or invoking any external runner."""

    plan_verification = verify_execution_plan(plan)
    if not plan_verification.clean:
        raise SimulationError(
            f"Execution plan is not clean and cannot be simulated: {'; '.join(plan_verification.issues)}"
        )

    snapshot_path: Path | None = None
    started_recorded = False

    try:
        state_root = Path(snapshot_dir).parent if snapshot_dir is not None else None
        snapshot = build_snapshot_manifest(plan, state_root=state_root)
        if snapshot_dir is not None:
            snapshot_path = Path(snapshot_dir) / f"{snapshot['snapshot_id']}.json"
            write_snapshot_manifest(snapshot_path, snapshot)

        if audit_path is not None:
            _append_simulation_event(
                Path(audit_path),
                plan=plan,
                snapshot=snapshot,
                event_type="simulation_started",
                status="started",
                decision_code="simulation_started",
                details={
                    "mode": "simulation_only",
                    "snapshot_hash": snapshot["snapshot_hash"],
                },
            )
            started_recorded = True

        receipt = build_simulation_receipt(plan, snapshot)

        if audit_path is not None:
            _append_simulation_event(
                Path(audit_path),
                plan=plan,
                snapshot=snapshot,
                event_type="simulation_finished",
                status="simulated",
                decision_code="simulation_finished",
                details={
                    "mode": "simulation_only",
                    "receipt_hash": receipt["receipt_hash"],
                    "snapshot_ref_written": str(snapshot_path is not None).lower(),
                },
            )

        return receipt
    except SnapshotError as exc:
        raise SimulationError(f"Simulation snapshot failed: {exc}") from exc
    except AuditLogError as exc:
        raise SimulationError(f"Simulation audit append failed: {exc}") from exc
    except SimulationError:
        raise
    except Exception as exc:
        if audit_path is not None and started_recorded:
            try:
                snapshot_for_failure = locals().get("snapshot")
                if isinstance(snapshot_for_failure, dict):
                    _append_simulation_event(
                        Path(audit_path),
                        plan=plan,
                        snapshot=snapshot_for_failure,
                        event_type="simulation_failed",
                        status="failed",
                        decision_code="simulation_failed",
                        details={
                            "mode": "simulation_only",
                            "error_type": exc.__class__.__name__,
                        },
                    )
            except AuditLogError as failure_audit_exc:
                raise SimulationError(
                    f"Simulation failed and failure audit append also failed: {failure_audit_exc}"
                ) from exc
        raise SimulationError(f"Simulation failed: {exc}") from exc
