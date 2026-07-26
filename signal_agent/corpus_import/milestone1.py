from __future__ import annotations

from pathlib import Path

from .errors import (
    CorpusImportError,
    PreservationError,
    SourceNotFoundError,
    UnreadableArchiveError,
)
from .hashing import sha256_file
from .models import Milestone1Result
from .preservation import prepare_run_root, preserve_source_zip
from .receipts import SCHEMA_VERSION, seal_receipt, utc_now_iso, write_receipt_exclusive
from .zip_validation import validate_chatgpt_export_zip


VALIDATION_RECEIPT_RELATIVE_PATH = Path("05_receipts") / "validation_receipt.json"


def _base_receipt(*, source: Path, run_root: Path) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "receipt_id": "validation.unidentified",
        "created_at": utc_now_iso(),
        "status": "failed",
        "milestone": 1,
        "operation": "validate_hash_preserve",
        "source": {
            "source_type": "chatgpt_export_zip",
            "sha256": None,
            "size_bytes": None,
            "observed_path": str(Path(source).expanduser().resolve(strict=False)),
            "preserved_path": None,
            "archive_entries": None,
            "conversation_json_files": None,
        },
        "run_root": str(Path(run_root).expanduser().resolve(strict=False)),
        "validation": {
            "source_exists": False,
            "archive_opened": False,
            "conversation_data_present": False,
            "conversation_members": [],
        },
        "original_preserved": False,
        "hash_verified": False,
        "source_stat_stable": None,
        "overwrite_policy": "refuse",
        "completed_stages": [],
        "failed_stage": None,
        "safe_resume_point": "validation",
        "observed_writes": [],
        "warnings": [],
        "errors": [],
        "fixture_write_authorization": "none",
        "publication_authorization": "none",
    }


def _record_error(receipt: dict, exc: CorpusImportError) -> None:
    receipt["status"] = "failed"
    receipt["failed_stage"] = exc.stage
    receipt["safe_resume_point"] = exc.stage
    receipt["errors"].append(
        {
            "type": type(exc).__name__,
            "reason_code": exc.reason_code,
            "stage": exc.stage,
            "message": str(exc),
            "context": dict(exc.context),
        }
    )


def _try_persist_failure_receipt(receipt: dict, run_root: Path) -> tuple[Path | None, dict]:
    receipt_path = Path(run_root) / VALIDATION_RECEIPT_RELATIVE_PATH
    if receipt_path.exists():
        return None, seal_receipt(receipt)

    receipt["observed_writes"].append(str(receipt_path))
    sealed = seal_receipt(receipt)
    try:
        write_receipt_exclusive(receipt_path, sealed)
        return receipt_path, sealed
    except CorpusImportError as write_exc:
        receipt["observed_writes"] = [
            path for path in receipt["observed_writes"] if path != str(receipt_path)
        ]
        receipt["warnings"].append(
            {
                "type": type(write_exc).__name__,
                "reason_code": write_exc.reason_code,
                "message": str(write_exc),
            }
        )
        return None, seal_receipt(receipt)


def run_milestone1(source: Path | str, run_root: Path | str) -> Milestone1Result:
    """Run only validation, SHA-256 identity, source preservation, and receipt emission."""

    source_path = Path(source)
    requested_run_root = Path(run_root)
    receipt = _base_receipt(source=source_path, run_root=requested_run_root)
    prepared_run_root: Path | None = None

    try:
        try:
            source_stat = source_path.stat()
        except FileNotFoundError as exc:
            raise SourceNotFoundError(f"Source ZIP does not exist: {source_path}") from exc
        except OSError as exc:
            raise UnreadableArchiveError(
                f"Unable to inspect source ZIP '{source_path}': {exc}"
            ) from exc

        receipt["validation"]["source_exists"] = True
        validation = validate_chatgpt_export_zip(source_path)
        receipt["validation"].update(
            {
                "archive_opened": True,
                "conversation_data_present": True,
                "conversation_members": list(validation.conversation_members),
            }
        )
        receipt["source"]["archive_entries"] = validation.archive_entries
        receipt["source"]["conversation_json_files"] = validation.conversation_json_files
        receipt["completed_stages"].append("validation_completed")

        source_sha256 = sha256_file(source_path)
        source_size = source_path.stat().st_size
        receipt["source"]["sha256"] = source_sha256
        receipt["source"]["size_bytes"] = source_size
        receipt["receipt_id"] = f"validation.{source_sha256[:12]}"
        receipt["completed_stages"].append("source_identity_computed")

        prepared_run_root = prepare_run_root(requested_run_root)
        preservation = preserve_source_zip(
            source_path,
            prepared_run_root,
            expected_sha256=source_sha256,
            expected_stat=source_stat,
        )
        receipt["source"]["preserved_path"] = str(preservation.preserved_path)
        receipt["original_preserved"] = True
        receipt["hash_verified"] = preservation.preserved_sha256 == source_sha256
        receipt["source_stat_stable"] = True
        receipt["observed_writes"].extend(
            [
                str(preservation.preserved_path),
                str(preservation.hash_record_path),
            ]
        )
        receipt["completed_stages"].append("source_preserved")

        receipt["status"] = "completed"
        receipt["failed_stage"] = None
        receipt["safe_resume_point"] = "milestone_2"
        receipt_path = prepared_run_root / VALIDATION_RECEIPT_RELATIVE_PATH
        receipt["observed_writes"].append(str(receipt_path))
        sealed = seal_receipt(receipt)
        write_receipt_exclusive(receipt_path, sealed)
        return Milestone1Result(success=True, receipt=sealed, receipt_path=receipt_path)

    except CorpusImportError as exc:
        _record_error(receipt, exc)
    except OSError as exc:
        typed_exc = PreservationError(f"Filesystem operation failed: {exc}")
        _record_error(receipt, typed_exc)
    except Exception as exc:  # defensive boundary for an explicit failed receipt
        typed_exc = CorpusImportError(f"Unexpected importer failure: {exc}")
        _record_error(receipt, typed_exc)

    primary_reason = receipt["errors"][0]["reason_code"] if receipt["errors"] else None
    if prepared_run_root is None and primary_reason not in {"run_collision", "protected_fixture_path"}:
        try:
            prepared_run_root = prepare_run_root(requested_run_root)
        except CorpusImportError as write_preflight_exc:
            receipt["warnings"].append(
                {
                    "type": type(write_preflight_exc).__name__,
                    "reason_code": write_preflight_exc.reason_code,
                    "message": "Failure receipt was not persisted: " + str(write_preflight_exc),
                }
            )

    if prepared_run_root is not None:
        receipt_path, sealed_failure = _try_persist_failure_receipt(receipt, prepared_run_root)
    else:
        receipt_path, sealed_failure = None, seal_receipt(receipt)
    return Milestone1Result(success=False, receipt=sealed_failure, receipt_path=receipt_path)
