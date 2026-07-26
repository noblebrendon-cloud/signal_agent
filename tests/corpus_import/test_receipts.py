from __future__ import annotations

import json
from pathlib import Path

from signal_agent.corpus_import.milestone1 import run_milestone1
from signal_agent.corpus_import.receipts import verify_receipt_hash


def test_success_receipt_is_persisted_and_hash_verifies(valid_export_zip: Path, tmp_path: Path) -> None:
    run_root = tmp_path / "run-001"

    result = run_milestone1(valid_export_zip, run_root)

    receipt_path = run_root / "05_receipts" / "validation_receipt.json"
    persisted = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert result.success is True
    assert result.receipt_path == receipt_path
    assert persisted == result.receipt
    assert persisted["status"] == "completed"
    assert persisted["publication_authorization"] == "none"
    assert persisted["fixture_write_authorization"] == "none"
    assert persisted["original_preserved"] is True
    assert persisted["hash_verified"] is True
    assert persisted["safe_resume_point"] == "milestone_2"
    assert verify_receipt_hash(persisted) is True


def test_invalid_archive_persists_failed_validation_receipt(tmp_path: Path) -> None:
    source = tmp_path / "bad.zip"
    source.write_bytes(b"bad")
    run_root = tmp_path / "run-001"

    result = run_milestone1(source, run_root)

    assert result.success is False
    assert result.receipt_path == run_root / "05_receipts" / "validation_receipt.json"
    assert result.receipt["status"] == "failed"
    assert result.receipt["failed_stage"] == "validation"
    assert result.receipt["publication_authorization"] == "none"
    assert verify_receipt_hash(result.receipt) is True
    assert result.receipt_path.exists() is True
    assert not (run_root / "00_original").exists()
