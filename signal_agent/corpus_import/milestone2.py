from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from .archive_safety import scan_archive
from .errors import (
    ArchivePolicyError,
    CorpusImportError,
    ExtractionCollisionError,
    ExtractionError,
    ExtractionSourceChangedError,
    InventoryError,
    ParentReceiptError,
    ProtectedFixtureError,
    ReceiptWriteError,
)
from .extraction import extract_archive_to_staging, is_regular_file, promote_directory_no_replace
from .extraction_receipts import (
    EXTRACTION_RECEIPT_SCHEMA_VERSION,
    write_extraction_receipt_exclusive,
)
from .hashing import sha256_canonical_json, sha256_file
from .inventory import compute_extracted_tree_digest, write_inventories
from .models import (
    ArchivePlan,
    ArchivePolicy,
    ExtractionResult,
    InventoryResult,
    Milestone2Result,
    ParentValidationContext,
)
from .receipts import (
    SCHEMA_VERSION as VALIDATION_RECEIPT_SCHEMA_VERSION,
    seal_receipt,
    utc_now_iso,
    verify_receipt_hash,
)


PRESERVED_ZIP_RELATIVE_PATH = Path("00_original") / "export.zip"
HASH_RECORD_RELATIVE_PATH = Path("00_original") / "export.zip.sha256.txt"
VALIDATION_RECEIPT_RELATIVE_PATH = Path("05_receipts") / "validation_receipt.json"
EXTRACTION_RECEIPT_RELATIVE_PATH = Path("05_receipts") / "extraction_receipt.json"
EXTRACTION_RELATIVE_PATH = Path("01_working_extract")
INVENTORY_RELATIVE_PATH = Path("02_inventory")
STAGING_RELATIVE_PATH = Path(".m2_staging")
INVENTORY_FILENAMES = (
    "archive_entries.csv",
    "archive_entries.json",
    "conversation_json_files.csv",
    "extracted_files.csv",
    "extracted_files.json",
    "extraction_summary.json",
    "file_counts_by_extension.csv",
    "inventory_manifest.json",
    "largest_100_files.csv",
    "top_level_contents.csv",
)


DiskUsageProvider = Callable[[Path], Any]


def _stat_signature(path: Path) -> tuple[int, int, int, int]:
    observed = Path(path).stat()
    return (
        int(observed.st_dev),
        int(observed.st_ino),
        int(observed.st_size),
        int(observed.st_mtime_ns),
    )


def _owned_directory_identity(path: Path) -> tuple[int, int]:
    observed = Path(path).lstat()
    if not Path(path).is_dir() or Path(path).is_symlink():
        raise ExtractionError(f"Attempt-owned path is not a real directory: {path}")
    return int(observed.st_dev), int(observed.st_ino)


def _error_dict(exc: CorpusImportError) -> dict[str, Any]:
    return {
        "context": dict(exc.context),
        "message": str(exc),
        "reason_code": exc.reason_code,
        "stage": exc.stage,
        "type": type(exc).__name__,
    }


def _resolved_run_root(run_root: Path | str) -> Path:
    resolved = Path(run_root).expanduser().resolve(strict=False)
    protected_parts = {"fixtures", "manual_calibration_v1"}
    if any(part.casefold() in protected_parts for part in resolved.parts):
        raise ProtectedFixtureError(f"Run root is inside a protected fixture path: {resolved}")
    if not resolved.exists():
        raise ParentReceiptError(f"Milestone 1 run root does not exist: {resolved}")
    if not resolved.is_dir():
        raise ParentReceiptError(f"Milestone 1 run root is not a directory: {resolved}")
    return resolved


def _require_regular_input(path: Path, label: str) -> None:
    if not path.exists():
        raise ParentReceiptError(f"Required {label} is missing: {path}")
    if path.is_symlink() or not is_regular_file(path):
        raise ParentReceiptError(f"Required {label} is not a regular file: {path}")


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ParentReceiptError(f"Unable to read {label} '{path}': {exc}") from exc
    if not isinstance(payload, dict):
        raise ParentReceiptError(f"{label.capitalize()} must contain one JSON object: {path}")
    return payload


def _validate_policy(policy: ArchivePolicy) -> None:
    baseline = ArchivePolicy()
    if policy.version != baseline.version:
        raise ArchivePolicyError(
            "Only archive security policy v1 is permitted.",
            context={"configured_version": policy.version, "required_version": baseline.version},
        )
    max_fields = (
        "max_archive_members",
        "max_declared_total_bytes",
        "max_actual_total_bytes",
        "max_member_bytes",
        "max_expansion_ratio",
        "max_path_length",
        "max_component_length",
    )
    for field_name in max_fields:
        configured = getattr(policy, field_name)
        default = getattr(baseline, field_name)
        if configured <= 0:
            raise ArchivePolicyError(
                "Archive policy limits must be positive.",
                context={"policy_field": field_name, "configured_limit": configured},
            )
        if configured > default:
            raise ArchivePolicyError(
                "Archive policy override would weaken policy v1.",
                context={
                    "policy_field": field_name,
                    "configured_limit": configured,
                    "policy_v1_limit": default,
                },
            )
    if policy.required_space_margin_bytes < baseline.required_space_margin_bytes:
        raise ArchivePolicyError(
            "Required-space override would weaken policy v1.",
            context={
                "policy_field": "required_space_margin_bytes",
                "configured_limit": policy.required_space_margin_bytes,
                "policy_v1_limit": baseline.required_space_margin_bytes,
            },
        )


def policy_hash(policy: ArchivePolicy) -> str:
    return f"sha256:{sha256_canonical_json(policy.to_dict())}"


def _verify_source_hash_and_stat(
    path: Path,
    *,
    expected_sha256: str,
    expected_stat: tuple[int, int, int, int] | None = None,
) -> tuple[int, int, int, int]:
    before = _stat_signature(path)
    observed_hash = sha256_file(path)
    after = _stat_signature(path)
    if before != after or (expected_stat is not None and after != expected_stat):
        raise ExtractionSourceChangedError(
            "Preserved ZIP stat identity changed during Milestone 2.",
            context={
                "expected_stat": list(expected_stat) if expected_stat is not None else None,
                "before_stat": list(before),
                "after_stat": list(after),
            },
        )
    if observed_hash != expected_sha256:
        raise ExtractionSourceChangedError(
            "Preserved ZIP SHA-256 does not match the Milestone 1 receipt.",
            context={"expected_sha256": expected_sha256, "observed_sha256": observed_hash},
        )
    return after


def load_parent_validation_context(run_root: Path | str) -> ParentValidationContext:
    """Verify the completed Milestone 1 receipt and its run-local preserved source."""

    resolved_run_root = _resolved_run_root(run_root)
    receipt_path = resolved_run_root / VALIDATION_RECEIPT_RELATIVE_PATH
    preserved_path = resolved_run_root / PRESERVED_ZIP_RELATIVE_PATH
    hash_record_path = resolved_run_root / HASH_RECORD_RELATIVE_PATH
    _require_regular_input(receipt_path, "Milestone 1 validation receipt")
    _require_regular_input(preserved_path, "run-local preserved ZIP")
    _require_regular_input(hash_record_path, "preserved ZIP hash record")

    receipt = _load_json_object(receipt_path, "Milestone 1 validation receipt")
    required_values = {
        "schema_version": VALIDATION_RECEIPT_SCHEMA_VERSION,
        "status": "completed",
        "safe_resume_point": "milestone_2",
        "hash_verified": True,
        "original_preserved": True,
        "overwrite_policy": "refuse",
        "publication_authorization": "none",
    }
    for field_name, expected_value in required_values.items():
        if receipt.get(field_name) != expected_value:
            raise ParentReceiptError(
                f"Milestone 1 validation receipt has invalid '{field_name}'.",
                context={
                    "field": field_name,
                    "expected": expected_value,
                    "observed": receipt.get(field_name),
                },
            )
    if not verify_receipt_hash(receipt):
        raise ParentReceiptError("Milestone 1 validation receipt hash verification failed.")

    recorded_run_root = receipt.get("run_root")
    if not isinstance(recorded_run_root, str) or Path(recorded_run_root).resolve(
        strict=False
    ) != resolved_run_root:
        raise ParentReceiptError(
            "Milestone 1 receipt run root does not match the requested run root."
        )
    source = receipt.get("source")
    if not isinstance(source, dict):
        raise ParentReceiptError("Milestone 1 receipt is missing its source identity object.")
    recorded_preserved_path = source.get("preserved_path")
    if not isinstance(recorded_preserved_path, str) or Path(recorded_preserved_path).resolve(
        strict=False
    ) != preserved_path:
        raise ParentReceiptError(
            "Milestone 1 receipt does not identify the required run-local preserved ZIP."
        )
    source_sha256 = source.get("sha256")
    if (
        not isinstance(source_sha256, str)
        or len(source_sha256) != 64
        or any(character not in "0123456789abcdef" for character in source_sha256)
    ):
        raise ParentReceiptError("Milestone 1 receipt contains an invalid source SHA-256.")
    source_size = source.get("size_bytes")
    if not isinstance(source_size, int) or source_size < 0:
        raise ParentReceiptError("Milestone 1 receipt contains an invalid source size.")

    try:
        hash_record = hash_record_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ParentReceiptError(f"Unable to read preserved ZIP hash record: {exc}") from exc
    if hash_record != f"{source_sha256}  export.zip\n":
        raise ParentReceiptError(
            "Preserved ZIP hash record does not match the Milestone 1 source identity."
        )
    initial_stat = _verify_source_hash_and_stat(
        preserved_path,
        expected_sha256=source_sha256,
    )
    if initial_stat[2] != source_size:
        raise ParentReceiptError(
            "Preserved ZIP size does not match the Milestone 1 receipt.",
            context={"expected_size": source_size, "observed_size": initial_stat[2]},
        )
    return ParentValidationContext(
        run_root=resolved_run_root,
        receipt_path=receipt_path,
        receipt=receipt,
        preserved_path=preserved_path,
        source_sha256=source_sha256,
        source_size=source_size,
        initial_stat=initial_stat,
    )


def _output_paths(run_root: Path) -> tuple[Path, ...]:
    return (
        run_root / STAGING_RELATIVE_PATH,
        run_root / EXTRACTION_RELATIVE_PATH,
        run_root / INVENTORY_RELATIVE_PATH,
        run_root / EXTRACTION_RECEIPT_RELATIVE_PATH,
    )


def _refuse_collisions(run_root: Path) -> None:
    collisions = [path for path in _output_paths(run_root) if os.path.lexists(path)]
    if collisions:
        raise ExtractionCollisionError(
            "Milestone 2 requires all staging and final output paths to be absent.",
            context={
                "existing_paths": [
                    path.relative_to(run_root).as_posix() for path in sorted(collisions)
                ]
            },
        )


def _archive_properties(plan: ArchivePlan) -> dict[str, Any]:
    return {
        "archive_directory_count": plan.archive_directory_count,
        "archive_file_count": plan.archive_file_count,
        "archive_member_count": plan.archive_member_count,
        "conversation_json_files": plan.conversation_json_files,
        "declared_compressed_bytes": plan.declared_compressed_bytes,
        "declared_uncompressed_bytes": plan.declared_uncompressed_bytes,
    }


def _security_checks(*, source_stat_stable: bool | None = None) -> dict[str, Any]:
    return {
        "actual_decompression_limits": "pending",
        "archive_member_collisions": "passed",
        "central_directory_scan": "passed",
        "crc_validation": "pending",
        "declared_decompression_limits": "passed",
        "destination_containment": "pending",
        "disk_space": "passed",
        "member_types": "passed",
        "path_safety": "passed",
        "source_stat_stable": source_stat_stable,
    }


def _intended_writes() -> list[str]:
    return [
        STAGING_RELATIVE_PATH.as_posix(),
        EXTRACTION_RELATIVE_PATH.as_posix(),
        INVENTORY_RELATIVE_PATH.as_posix(),
        *[
            (INVENTORY_RELATIVE_PATH / filename).as_posix()
            for filename in INVENTORY_FILENAMES
        ],
        EXTRACTION_RECEIPT_RELATIVE_PATH.as_posix(),
    ]


def _plan_payload(
    context: ParentValidationContext,
    plan: ArchivePlan,
    policy: ArchivePolicy,
) -> dict[str, Any]:
    return {
        "archive": _archive_properties(plan),
        "clean": True,
        "errors": [],
        "fixture_write_authorization": "none",
        "intended_writes": _intended_writes(),
        "milestone": 2,
        "operation": "plan_safe_extraction",
        "overwrite_policy": "refuse",
        "parent_validation_receipt": {
            "path": VALIDATION_RECEIPT_RELATIVE_PATH.as_posix(),
            "receipt_hash": context.receipt["receipt_hash"],
            "receipt_id": context.receipt["receipt_id"],
            "schema_version": context.receipt["schema_version"],
        },
        "policy": {
            **policy.to_dict(),
            "policy_hash": policy_hash(policy),
        },
        "publication_authorization": "none",
        "run_root": str(context.run_root),
        "security_checks": _security_checks(source_stat_stable=True),
        "source": {
            "relative_path": PRESERVED_ZIP_RELATIVE_PATH.as_posix(),
            "sha256": context.source_sha256,
            "size_bytes": context.source_size,
            "stat_stable": True,
        },
        "space": {
            "available_free_bytes": plan.available_free_bytes,
            "required_free_bytes": plan.required_free_bytes,
        },
        "status": "ready",
    }


def _plan_failure(run_root: Path | str, exc: CorpusImportError) -> dict[str, Any]:
    return {
        "clean": False,
        "errors": [_error_dict(exc)],
        "fixture_write_authorization": "none",
        "intended_writes": [],
        "milestone": 2,
        "operation": "plan_safe_extraction",
        "overwrite_policy": "refuse",
        "publication_authorization": "none",
        "run_root": str(Path(run_root).expanduser().resolve(strict=False)),
        "status": "refused",
    }


def _prepare_milestone2(
    run_root: Path | str,
    *,
    policy: ArchivePolicy,
    disk_usage_provider: DiskUsageProvider,
) -> tuple[ParentValidationContext, ArchivePlan, dict[str, Any]]:
    _validate_policy(policy)
    context = load_parent_validation_context(run_root)
    _refuse_collisions(context.run_root)
    try:
        available_free_bytes = int(disk_usage_provider(context.run_root).free)
    except (AttributeError, OSError, TypeError, ValueError) as exc:
        raise ArchivePolicyError(f"Unable to determine available extraction space: {exc}") from exc
    plan = scan_archive(
        context.preserved_path,
        policy=policy,
        available_free_bytes=available_free_bytes,
    )
    parent_source = context.receipt["source"]
    expected_members = parent_source.get("archive_entries")
    expected_conversations = parent_source.get("conversation_json_files")
    if plan.archive_member_count != expected_members:
        raise ParentReceiptError(
            "Archive member count does not match the Milestone 1 receipt.",
            context={
                "expected_archive_members": expected_members,
                "observed_archive_members": plan.archive_member_count,
            },
        )
    if plan.conversation_json_files != expected_conversations:
        raise ParentReceiptError(
            "Conversation shard count does not match the Milestone 1 receipt.",
            context={
                "expected_conversation_json_files": expected_conversations,
                "observed_conversation_json_files": plan.conversation_json_files,
            },
        )
    return context, plan, _plan_payload(context, plan, policy)


def plan_milestone2(
    run_root: Path | str,
    *,
    policy: ArchivePolicy | None = None,
    disk_usage_provider: DiskUsageProvider = shutil.disk_usage,
) -> Milestone2Result:
    """Perform the complete Milestone 2 preflight without writing anything."""

    effective_policy = policy or ArchivePolicy()
    try:
        _, _, payload = _prepare_milestone2(
            run_root,
            policy=effective_policy,
            disk_usage_provider=disk_usage_provider,
        )
        return Milestone2Result(success=True, payload=payload)
    except CorpusImportError as exc:
        return Milestone2Result(success=False, payload=_plan_failure(run_root, exc))
    except Exception as exc:
        typed = ParentReceiptError(f"Unexpected extraction planning failure: {exc}")
        return Milestone2Result(success=False, payload=_plan_failure(run_root, typed))


def _base_extraction_receipt(
    *,
    context: ParentValidationContext,
    plan: ArchivePlan,
    policy: ArchivePolicy,
) -> dict[str, Any]:
    effective_policy_hash = policy_hash(policy)
    return {
        "archive": _archive_properties(plan),
        "cleanup_result": {"failed": [], "removed": [], "status": "not_required"},
        "completed_stages": [
            "lineage_validated",
            "archive_preflight_completed",
            "disk_preflight_completed",
        ],
        "created_at": utc_now_iso(),
        "errors": [],
        "extraction": {
            "actual_bytes_written": None,
            "crc_result": None,
            "duration_seconds": None,
            "extracted_directory_count": None,
            "extracted_file_count": None,
        },
        "failed_stage": None,
        "fixture_write_authorization": "none",
        "inventory": {
            "artifacts": [],
            "extracted_tree_digest": None,
        },
        "milestone": 2,
        "observed_writes": [],
        "operation": "safe_extract_and_inventory",
        "overwrite_policy": "refuse",
        "parent_validation_receipt": {
            "path": VALIDATION_RECEIPT_RELATIVE_PATH.as_posix(),
            "receipt_hash": context.receipt["receipt_hash"],
            "receipt_id": context.receipt["receipt_id"],
            "schema_version": context.receipt["schema_version"],
        },
        "policy": {
            **policy.to_dict(),
            "policy_hash": effective_policy_hash,
        },
        "publication_authorization": "none",
        "receipt_id": (
            f"extraction.{context.source_sha256[:12]}."
            f"{effective_policy_hash.removeprefix('sha256:')[:12]}"
        ),
        "safe_resume_point": "milestone_2",
        "schema_version": EXTRACTION_RECEIPT_SCHEMA_VERSION,
        "security_checks": _security_checks(source_stat_stable=None),
        "source": {
            "relative_path": PRESERVED_ZIP_RELATIVE_PATH.as_posix(),
            "sha256": context.source_sha256,
            "size_bytes": context.source_size,
            "stat_stable": None,
        },
        "space": {
            "available_free_bytes": plan.available_free_bytes,
            "required_free_bytes": plan.required_free_bytes,
        },
        "status": "in_progress",
    }


def _verify_staged_outputs(
    extraction_root: Path,
    inventory_root: Path,
    *,
    plan: ArchivePlan,
    extraction_result: ExtractionResult,
    inventory_result: InventoryResult,
) -> None:
    if len(extraction_result.files) != plan.archive_file_count:
        raise InventoryError(
            "Extracted file count does not match the archive plan.",
            context={
                "planned_files": plan.archive_file_count,
                "extracted_files": len(extraction_result.files),
            },
        )
    if extraction_result.actual_bytes_written != plan.declared_uncompressed_bytes:
        raise InventoryError(
            "Actual extracted bytes do not match the archive plan.",
            context={
                "declared_bytes": plan.declared_uncompressed_bytes,
                "actual_bytes": extraction_result.actual_bytes_written,
            },
        )
    for item in extraction_result.files:
        path = extraction_root.joinpath(*item.path.split("/"))
        if not is_regular_file(path):
            raise InventoryError(
                "Extracted inventory refers to a missing or nonregular file.",
                context={"path": item.path},
            )
        if path.stat().st_size != item.size_bytes or sha256_file(path) != item.sha256:
            raise InventoryError(
                "Extracted file identity verification failed.",
                context={"path": item.path},
            )
    if compute_extracted_tree_digest(extraction_result.files) != inventory_result.extracted_tree_digest:
        raise InventoryError("Extracted-tree digest verification failed.")

    artifact_by_path = {artifact.path: artifact for artifact in inventory_result.artifacts}
    expected_paths = {f"02_inventory/{name}" for name in INVENTORY_FILENAMES}
    if set(artifact_by_path) != expected_paths:
        raise InventoryError(
            "Inventory artifact set is incomplete.",
            context={
                "expected_paths": sorted(expected_paths),
                "observed_paths": sorted(artifact_by_path),
            },
        )
    for relative_path, artifact in artifact_by_path.items():
        filename = PurePosixPath(relative_path).name
        path = inventory_root / filename
        if not is_regular_file(path):
            raise InventoryError(
                "Inventory artifact is missing or nonregular.",
                context={"path": relative_path},
            )
        if path.stat().st_size != artifact.size_bytes or sha256_file(path) != artifact.sha256:
            raise InventoryError(
                "Inventory artifact hash verification failed.",
                context={"path": relative_path},
            )

    manifest_path = inventory_root / "inventory_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InventoryError(f"Unable to verify inventory manifest: {exc}") from exc
    expected_manifest_artifacts = [
        artifact.to_dict()
        for artifact in inventory_result.artifacts
        if artifact.path != "02_inventory/inventory_manifest.json"
    ]
    if (
        manifest.get("artifacts") != expected_manifest_artifacts
        or manifest.get("extracted_tree_digest") != inventory_result.extracted_tree_digest
    ):
        raise InventoryError("Inventory manifest content verification failed.")

def _cleanup_attempt_paths(
    run_root: Path,
    *,
    staging_root: Path,
    staging_identity: tuple[int, int],
    promoted_paths: list[tuple[Path, tuple[int, int]]],
) -> dict[str, Any]:
    removed: list[str] = []
    failed: list[dict[str, str]] = []
    for path, expected_identity in reversed(promoted_paths):
        try:
            if os.path.lexists(path):
                observed_identity = _owned_directory_identity(path)
                if observed_identity != expected_identity:
                    raise OSError("attempt ownership identity no longer matches")
                shutil.rmtree(path)
                removed.append(path.relative_to(run_root).as_posix())
        except (CorpusImportError, OSError) as exc:
            failed.append(
                {"path": path.relative_to(run_root).as_posix(), "message": str(exc)}
            )
    try:
        if os.path.lexists(staging_root):
            observed_identity = _owned_directory_identity(staging_root)
            if observed_identity != staging_identity:
                raise OSError("attempt staging ownership identity no longer matches")
            shutil.rmtree(staging_root)
            removed.append(staging_root.relative_to(run_root).as_posix())
    except (CorpusImportError, OSError) as exc:
        failed.append(
            {"path": staging_root.relative_to(run_root).as_posix(), "message": str(exc)}
        )
    return {
        "failed": failed,
        "removed": sorted(removed),
        "status": "failed" if failed else "completed",
    }


def _unexpected_as_typed(exc: Exception) -> CorpusImportError:
    if isinstance(exc, OSError):
        return ExtractionError(f"Milestone 2 filesystem operation failed: {exc}")
    return ExtractionError(f"Unexpected Milestone 2 failure: {exc}")


def run_milestone2(
    run_root: Path | str,
    *,
    policy: ArchivePolicy | None = None,
    disk_usage_provider: DiskUsageProvider = shutil.disk_usage,
    chunk_size: int = 1024 * 1024,
) -> Milestone2Result:
    """Safely extract and inventory only a completed Milestone 1 preserved ZIP."""

    effective_policy = policy or ArchivePolicy()
    started = time.monotonic()
    context: ParentValidationContext | None = None
    plan: ArchivePlan | None = None
    receipt: dict[str, Any] | None = None
    staging_created = False
    staging_identity: tuple[int, int] | None = None
    promoted_paths: list[tuple[Path, tuple[int, int]]] = []
    receipt_path: Path | None = None
    extraction_started_at: float | None = None

    try:
        context, plan, _ = _prepare_milestone2(
            run_root,
            policy=effective_policy,
            disk_usage_provider=disk_usage_provider,
        )
        receipt = _base_extraction_receipt(context=context, plan=plan, policy=effective_policy)
        staging_root = context.run_root / STAGING_RELATIVE_PATH
        try:
            staging_root.mkdir(exist_ok=False)
        except FileExistsError as exc:
            raise ExtractionCollisionError(
                f"Milestone 2 staging path already exists: {staging_root}"
            ) from exc
        staging_created = True
        staging_identity = _owned_directory_identity(staging_root)
        receipt["observed_writes"].append(STAGING_RELATIVE_PATH.as_posix())
        receipt["completed_stages"].append("staging_created")

        extraction_started_at = time.monotonic()
        staged_extraction = staging_root / EXTRACTION_RELATIVE_PATH
        extraction_result = extract_archive_to_staging(
            context.preserved_path,
            plan,
            staged_extraction,
            policy=effective_policy,
            chunk_size=chunk_size,
        )
        extraction_duration = time.monotonic() - extraction_started_at
        receipt["extraction"].update(
            {
                "actual_bytes_written": extraction_result.actual_bytes_written,
                "crc_result": "passed",
                "duration_seconds": round(extraction_duration, 6),
                "extracted_directory_count": len(extraction_result.directories),
                "extracted_file_count": len(extraction_result.files),
            }
        )
        receipt["security_checks"]["actual_decompression_limits"] = "passed"
        receipt["security_checks"]["crc_validation"] = "passed"
        receipt["security_checks"]["destination_containment"] = "passed"
        receipt["completed_stages"].append("extraction_completed")

        staged_inventory = staging_root / INVENTORY_RELATIVE_PATH
        inventory_result = write_inventories(
            staged_inventory,
            archive_plan=plan,
            extraction_result=extraction_result,
        )
        _verify_staged_outputs(
            staged_extraction,
            staged_inventory,
            plan=plan,
            extraction_result=extraction_result,
            inventory_result=inventory_result,
        )
        receipt["completed_stages"].append("inventory_completed")

        _verify_source_hash_and_stat(
            context.preserved_path,
            expected_sha256=context.source_sha256,
            expected_stat=context.initial_stat,
        )
        receipt["source"]["stat_stable"] = True
        receipt["security_checks"]["source_stat_stable"] = True
        receipt["completed_stages"].append("source_revalidated")

        final_extraction = context.run_root / EXTRACTION_RELATIVE_PATH
        final_inventory = context.run_root / INVENTORY_RELATIVE_PATH
        promote_directory_no_replace(staged_extraction, final_extraction)
        promoted_paths.append(
            (final_extraction, _owned_directory_identity(final_extraction))
        )
        promote_directory_no_replace(staged_inventory, final_inventory)
        promoted_paths.append((final_inventory, _owned_directory_identity(final_inventory)))
        staging_root.rmdir()
        receipt["observed_writes"].extend(
            [EXTRACTION_RELATIVE_PATH.as_posix(), INVENTORY_RELATIVE_PATH.as_posix()]
        )
        receipt["completed_stages"].append("outputs_promoted")

        receipt["inventory"] = {
            "artifacts": [artifact.to_dict() for artifact in inventory_result.artifacts],
            "extracted_tree_digest": inventory_result.extracted_tree_digest,
        }
        receipt["cleanup_result"] = {
            "failed": [],
            "removed": [STAGING_RELATIVE_PATH.as_posix()],
            "status": "completed",
        }
        receipt["status"] = "completed"
        receipt["safe_resume_point"] = "milestone_3"
        receipt["completed_stages"].append("receipt_sealed")
        receipt["observed_writes"].append(EXTRACTION_RECEIPT_RELATIVE_PATH.as_posix())
        sealed = seal_receipt(receipt)
        completed_receipt_path = context.run_root / EXTRACTION_RECEIPT_RELATIVE_PATH
        write_extraction_receipt_exclusive(completed_receipt_path, sealed)
        receipt_path = completed_receipt_path
        return Milestone2Result(success=True, payload=sealed, receipt_path=receipt_path)

    except CorpusImportError as exc:
        typed_exc = exc
    except Exception as exc:
        typed_exc = _unexpected_as_typed(exc)

    if (
        not staging_created
        or staging_identity is None
        or context is None
        or plan is None
        or receipt is None
    ):
        refusal = _plan_failure(run_root, typed_exc)
        refusal["operation"] = "safe_extract_and_inventory"
        return Milestone2Result(success=False, payload=refusal)

    staging_root = context.run_root / STAGING_RELATIVE_PATH
    cleanup_result = _cleanup_attempt_paths(
        context.run_root,
        staging_root=staging_root,
        staging_identity=staging_identity,
        promoted_paths=promoted_paths,
    )
    receipt["status"] = "failed"
    receipt["failed_stage"] = typed_exc.stage
    receipt["safe_resume_point"] = "milestone_2"
    receipt["errors"].append(_error_dict(typed_exc))
    receipt["cleanup_result"] = cleanup_result
    if receipt["extraction"]["duration_seconds"] is None:
        duration_start = extraction_started_at if extraction_started_at is not None else started
        receipt["extraction"]["duration_seconds"] = round(time.monotonic() - duration_start, 6)
    for field_name in (
        "actual_bytes_written",
        "extracted_directory_count",
        "extracted_file_count",
    ):
        observed_value = typed_exc.context.get(field_name)
        if receipt["extraction"][field_name] is None and isinstance(observed_value, int):
            receipt["extraction"][field_name] = observed_value
    if typed_exc.stage == "extraction":
        receipt["extraction"]["crc_result"] = "failed_or_incomplete"
        receipt["security_checks"]["actual_decompression_limits"] = "failed_or_incomplete"
        receipt["security_checks"]["crc_validation"] = "failed_or_incomplete"
    if isinstance(typed_exc, ExtractionSourceChangedError):
        receipt["source"]["stat_stable"] = False
        receipt["security_checks"]["source_stat_stable"] = False
    sealed_failure = seal_receipt(receipt)
    failure_receipt_path = context.run_root / EXTRACTION_RECEIPT_RELATIVE_PATH
    if not isinstance(typed_exc, ReceiptWriteError) and not os.path.lexists(failure_receipt_path):
        try:
            receipt["observed_writes"].append(EXTRACTION_RECEIPT_RELATIVE_PATH.as_posix())
            sealed_failure = seal_receipt(receipt)
            write_extraction_receipt_exclusive(failure_receipt_path, sealed_failure)
            receipt_path = failure_receipt_path
        except CorpusImportError as receipt_exc:
            receipt["observed_writes"] = [
                path
                for path in receipt["observed_writes"]
                if path != EXTRACTION_RECEIPT_RELATIVE_PATH.as_posix()
            ]
            receipt.setdefault("warnings", []).append(_error_dict(receipt_exc))
            sealed_failure = seal_receipt(receipt)
    return Milestone2Result(
        success=False,
        payload=sealed_failure,
        receipt_path=receipt_path,
    )
