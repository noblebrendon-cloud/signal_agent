from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.utils.io_contract import atomic_write_text

from .errors import SnapshotError
from .execution_plan import verify_execution_plan
from .proposal import dump_canonical_json


@dataclass(frozen=True)
class SnapshotVerificationResult:
    clean: bool
    issues: list[str]
    snapshot_id: str | None
    snapshot_hash: str | None
    recomputed_snapshot_hash: str | None


def _snapshot_root(state_root: Path | None) -> Path:
    return Path(state_root) if state_root is not None else Path.cwd()


def _deterministic_snapshot_id(plan: dict) -> str:
    plan_hash = str(plan["plan_hash"])
    return f"snapshot.{plan_hash.split(':', 1)[1][:12]}"


def _path_parts(relative_path: str) -> list[str]:
    if relative_path in {"", "."}:
        return []
    return [part for part in relative_path.split("/") if part]


def _collect_targets(plan: dict) -> list[dict]:
    targets: list[dict] = []
    for access_kind, field_name in (("read", "declared_reads"), ("write", "declared_writes")):
        surfaces = plan.get(field_name)
        if not isinstance(surfaces, list):
            raise SnapshotError(f"Execution plan field {field_name!r} must be a list.")
        for surface in surfaces:
            if type(surface) is not dict:
                raise SnapshotError(f"Execution plan field {field_name!r} must contain only objects.")
            target: dict[str, object] = {
                "access": access_kind,
            }
            for key in ("binding_id", "parameter", "path_ref_id", "root_id", "relative_path"):
                value = surface.get(key)
                if not isinstance(value, str):
                    raise SnapshotError(f"Execution plan surface is missing string field {key!r}.")
                target[key] = value
            targets.append(target)
    return json.loads(dump_canonical_json({"targets": targets}))["targets"]


def _resolved_target_path(target: dict, *, state_root: Path) -> Path:
    root_id = str(target["root_id"])
    relative_path = str(target["relative_path"])
    resolved = state_root / root_id
    for part in _path_parts(relative_path):
        resolved = resolved / part
    return resolved


def _stat_mtime_utc(stat_result: object) -> str | None:
    mtime = getattr(stat_result, "st_mtime", None)
    if not isinstance(mtime, (int, float)):
        return None
    return datetime.fromtimestamp(float(mtime), timezone.utc).isoformat().replace("+00:00", "Z")


def _observe_target(target: dict, *, target_index: int, state_root: Path) -> dict:
    resolved = _resolved_target_path(target, state_root=state_root)
    exists = resolved.exists()
    path_type = "missing"
    size_bytes = None
    mtime_utc = None

    if exists:
        if resolved.is_file():
            path_type = "file"
        elif resolved.is_dir():
            path_type = "directory"
        else:
            raise SnapshotError(f"Unsupported filesystem object type for snapshot target: {resolved}")

        try:
            stat_result = resolved.stat()
        except OSError as exc:
            raise SnapshotError(f"Unable to stat snapshot target {resolved}: {exc}") from exc

        if path_type == "file":
            size_bytes = int(stat_result.st_size)
        mtime_utc = _stat_mtime_utc(stat_result)

    return {
        "target_index": target_index,
        "access": str(target["access"]),
        "binding_id": str(target["binding_id"]),
        "parameter": str(target["parameter"]),
        "path_ref_id": str(target["path_ref_id"]),
        "root_id": str(target["root_id"]),
        "relative_path": str(target["relative_path"]),
        "exists": exists,
        "path_type": path_type,
        "size_bytes": size_bytes,
        "mtime_utc": mtime_utc,
    }


def _canonical_snapshot_json(snapshot: dict) -> str:
    return dump_canonical_json(snapshot)


def compute_snapshot_hash(snapshot: dict) -> str:
    """Compute a stable snapshot hash excluding the snapshot_hash field itself."""

    if type(snapshot) is not dict:
        raise SnapshotError("Snapshot hash input must be a plain dict.")

    material = dict(snapshot)
    material.pop("snapshot_hash", None)

    import hashlib

    canonical_json = _canonical_snapshot_json(material)
    return f"sha256:{hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()}"


def build_snapshot_manifest(plan: dict, *, state_root: Path | None = None) -> dict:
    """Build a metadata-only snapshot manifest from a verified sealed plan."""

    verification = verify_execution_plan(plan)
    if not verification.clean:
        raise SnapshotError(
            f"Execution plan is not clean and cannot be snapshotted: {'; '.join(verification.issues)}"
        )

    targets = _collect_targets(plan)
    resolved_state_root = _snapshot_root(state_root)
    observations = [
        _observe_target(target, target_index=index, state_root=resolved_state_root)
        for index, target in enumerate(targets)
    ]

    payload = {
        "schema_version": "snapshot_manifest.v1",
        "snapshot_id": _deterministic_snapshot_id(plan),
        "created_at": str(plan["created_at"]),
        "plan_id": str(plan["plan_id"]),
        "plan_hash": str(plan["plan_hash"]),
        "proposal_hash": str(plan["proposal_hash"]),
        "snapshot_mode": "metadata_only",
        "targets": targets,
        "filesystem_observations": observations,
        "snapshot_hash": "sha256:" + ("0" * 64),
    }
    payload["snapshot_hash"] = compute_snapshot_hash(payload)
    snapshot = json.loads(_canonical_snapshot_json(payload))
    verification_result = verify_snapshot_manifest(snapshot)
    if not verification_result.clean:
        raise SnapshotError(
            f"Snapshot manifest verification failed after creation: {'; '.join(verification_result.issues)}"
        )
    return snapshot


def verify_snapshot_manifest(snapshot: dict) -> SnapshotVerificationResult:
    """Verify a metadata-only snapshot manifest by shape and recomputed hash."""

    if type(snapshot) is not dict:
        return SnapshotVerificationResult(
            clean=False,
            issues=["snapshot manifest must be a plain dict."],
            snapshot_id=None,
            snapshot_hash=None,
            recomputed_snapshot_hash=None,
        )

    issues: list[str] = []
    required_strings = (
        "schema_version",
        "snapshot_id",
        "created_at",
        "plan_id",
        "plan_hash",
        "proposal_hash",
        "snapshot_mode",
        "snapshot_hash",
    )
    for key in required_strings:
        if not isinstance(snapshot.get(key), str):
            issues.append(f"{key} must be a string.")

    if snapshot.get("schema_version") != "snapshot_manifest.v1":
        issues.append("schema_version must be 'snapshot_manifest.v1'.")
    if snapshot.get("snapshot_mode") != "metadata_only":
        issues.append("snapshot_mode must be 'metadata_only'.")

    targets = snapshot.get("targets")
    observations = snapshot.get("filesystem_observations")
    if not isinstance(targets, list):
        issues.append("targets must be a list.")
        targets = []
    if not isinstance(observations, list):
        issues.append("filesystem_observations must be a list.")
        observations = []

    if isinstance(targets, list):
        for index, target in enumerate(targets):
            if type(target) is not dict:
                issues.append(f"targets[{index}] must be an object.")
                continue
            for key in ("access", "binding_id", "parameter", "path_ref_id", "root_id", "relative_path"):
                if not isinstance(target.get(key), str):
                    issues.append(f"targets[{index}].{key} must be a string.")
            if target.get("access") not in {"read", "write"}:
                issues.append(f"targets[{index}].access must be 'read' or 'write'.")

    if isinstance(observations, list):
        for index, observation in enumerate(observations):
            if type(observation) is not dict:
                issues.append(f"filesystem_observations[{index}] must be an object.")
                continue
            if observation.get("target_index") != index:
                issues.append(
                    f"filesystem_observations[{index}].target_index must equal {index}."
                )
            for key in ("access", "binding_id", "parameter", "path_ref_id", "root_id", "relative_path"):
                if not isinstance(observation.get(key), str):
                    issues.append(f"filesystem_observations[{index}].{key} must be a string.")
            if not isinstance(observation.get("exists"), bool):
                issues.append(f"filesystem_observations[{index}].exists must be a boolean.")
            if observation.get("path_type") not in {"file", "directory", "missing"}:
                issues.append(
                    f"filesystem_observations[{index}].path_type must be file, directory, or missing."
                )

    if len(targets) != len(observations):
        issues.append("targets and filesystem_observations must have matching lengths.")

    recomputed_snapshot_hash = compute_snapshot_hash(snapshot)
    snapshot_hash = snapshot.get("snapshot_hash")
    if isinstance(snapshot_hash, str):
        if snapshot_hash != recomputed_snapshot_hash:
            issues.append(
                f"snapshot_hash_mismatch:expected={recomputed_snapshot_hash}:actual={snapshot_hash}"
            )
    else:
        issues.append("snapshot_hash must be a string.")

    return SnapshotVerificationResult(
        clean=not issues,
        issues=issues,
        snapshot_id=snapshot.get("snapshot_id") if isinstance(snapshot.get("snapshot_id"), str) else None,
        snapshot_hash=snapshot_hash if isinstance(snapshot_hash, str) else None,
        recomputed_snapshot_hash=recomputed_snapshot_hash,
    )


def write_snapshot_manifest(path: Path, snapshot: dict) -> Path:
    """Write a verified snapshot manifest atomically without executing anything."""

    verification = verify_snapshot_manifest(snapshot)
    if not verification.clean:
        raise SnapshotError(
            f"Snapshot manifest is not clean and cannot be written: {'; '.join(verification.issues)}"
        )

    try:
        atomic_write_text(Path(path), _canonical_snapshot_json(snapshot))
    except OSError as exc:
        raise SnapshotError(f"Unable to write snapshot manifest: {exc}") from exc
    return Path(path)
