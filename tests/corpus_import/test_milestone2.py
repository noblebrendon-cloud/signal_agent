from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import signal_agent.corpus_import.milestone2 as milestone2_module
from signal_agent.corpus_import.errors import (
    InventoryError,
    PromotionError,
    ReceiptWriteError,
)
from signal_agent.corpus_import.hashing import sha256_file
from signal_agent.corpus_import.milestone2 import plan_milestone2, run_milestone2
from signal_agent.corpus_import.models import ArchivePolicy
from signal_agent.corpus_import.receipts import verify_receipt_hash


def _ample_space(_path: Path) -> SimpleNamespace:
    return SimpleNamespace(free=10 * 1024**3)


def _tree_snapshot(root: Path) -> dict[str, bytes | None]:
    snapshot: dict[str, bytes | None] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        snapshot[relative] = None if path.is_dir() else path.read_bytes()
    return snapshot


def test_planning_is_strictly_read_only(completed_m1_run: Path) -> None:
    before = _tree_snapshot(completed_m1_run)

    result = plan_milestone2(
        completed_m1_run,
        disk_usage_provider=_ample_space,
    )

    assert result.success is True
    assert result.payload["status"] == "ready"
    assert result.payload["source"]["relative_path"] == "00_original/export.zip"
    assert result.payload["space"]["required_free_bytes"] == (
        result.payload["archive"]["declared_uncompressed_bytes"] + 1024**3
    )
    assert _tree_snapshot(completed_m1_run) == before


def test_happy_path_promotes_outputs_and_seals_receipt(
    completed_m1_run: Path,
) -> None:
    source = completed_m1_run / "00_original" / "export.zip"
    validation_receipt = completed_m1_run / "05_receipts" / "validation_receipt.json"
    source_hash_before = sha256_file(source)
    source_stat_before = source.stat()
    validation_before = validation_receipt.read_bytes()

    result = run_milestone2(
        completed_m1_run,
        disk_usage_provider=_ample_space,
        chunk_size=11,
    )

    assert result.success is True
    assert result.exit_code == 0
    assert result.receipt_path == (
        completed_m1_run / "05_receipts" / "extraction_receipt.json"
    )
    assert verify_receipt_hash(result.payload) is True
    assert result.payload["schema_version"] == "chatgpt_export_extraction_receipt.v1"
    assert result.payload["status"] == "completed"
    assert result.payload["milestone"] == 2
    assert result.payload["operation"] == "safe_extract_and_inventory"
    assert result.payload["safe_resume_point"] == "milestone_3"
    assert result.payload["overwrite_policy"] == "refuse"
    assert result.payload["publication_authorization"] == "none"
    assert result.payload["fixture_write_authorization"] == "none"
    assert result.payload["source"]["stat_stable"] is True
    assert result.payload["extraction"]["crc_result"] == "passed"
    assert result.payload["extraction"]["extracted_file_count"] == 2
    assert (completed_m1_run / "01_working_extract" / "conversations.json").exists()
    assert (completed_m1_run / "02_inventory" / "inventory_manifest.json").exists()
    assert not (completed_m1_run / ".m2_staging").exists()
    assert not (completed_m1_run / "03_logs").exists()
    assert not (completed_m1_run / "04_selected").exists()

    assert sha256_file(source) == source_hash_before
    source_stat_after = source.stat()
    assert source_stat_after.st_size == source_stat_before.st_size
    assert source_stat_after.st_mtime_ns == source_stat_before.st_mtime_ns
    assert validation_receipt.read_bytes() == validation_before

    inventory_artifacts = result.payload["inventory"]["artifacts"]
    assert len(inventory_artifacts) == 10
    for artifact in inventory_artifacts:
        filename = artifact["path"].rsplit("/", 1)[-1]
        path = completed_m1_run / "02_inventory" / filename
        assert artifact["sha256"] == sha256_file(path)


def test_parent_receipt_hash_failure_is_refused_without_writes(
    completed_m1_run: Path,
) -> None:
    receipt_path = completed_m1_run / "05_receipts" / "validation_receipt.json"
    receipt = json.loads(receipt_path.read_text("utf-8"))
    receipt["status"] = "tampered"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    before = _tree_snapshot(completed_m1_run)

    result = plan_milestone2(completed_m1_run, disk_usage_provider=_ample_space)

    assert result.success is False
    assert result.payload["errors"][0]["reason_code"] == "invalid_parent_receipt"
    assert _tree_snapshot(completed_m1_run) == before


@pytest.mark.parametrize("invalid_content", [None, b"not-json", b"[]"])
def test_missing_or_invalid_parent_receipt_is_refused(
    completed_m1_run: Path,
    invalid_content: bytes | None,
) -> None:
    receipt_path = completed_m1_run / "05_receipts" / "validation_receipt.json"
    receipt_path.unlink()
    if invalid_content is not None:
        receipt_path.write_bytes(invalid_content)

    result = plan_milestone2(completed_m1_run, disk_usage_provider=_ample_space)

    assert result.success is False
    assert result.payload["errors"][0]["reason_code"] == "invalid_parent_receipt"
    assert not (completed_m1_run / "01_working_extract").exists()


def test_source_hash_mismatch_is_refused(completed_m1_run: Path) -> None:
    source = completed_m1_run / "00_original" / "export.zip"
    source.write_bytes(source.read_bytes() + b"tamper")

    result = plan_milestone2(completed_m1_run, disk_usage_provider=_ample_space)

    assert result.success is False
    assert result.payload["errors"][0]["reason_code"] == "source_changed_during_extraction"
    assert not (completed_m1_run / ".m2_staging").exists()


def test_source_mutation_during_extraction_cleans_staging_and_promotes_nothing(
    completed_m1_run: Path,
    monkeypatch,
) -> None:
    original_extract = milestone2_module.extract_archive_to_staging

    def mutating_extract(*args, **kwargs):
        extraction_result = original_extract(*args, **kwargs)
        source = completed_m1_run / "00_original" / "export.zip"
        source.write_bytes(source.read_bytes() + b"mutated")
        return extraction_result

    monkeypatch.setattr(milestone2_module, "extract_archive_to_staging", mutating_extract)

    result = run_milestone2(completed_m1_run, disk_usage_provider=_ample_space)

    assert result.success is False
    assert result.payload["errors"][0]["reason_code"] == "source_changed_during_extraction"
    assert not (completed_m1_run / ".m2_staging").exists()
    assert not (completed_m1_run / "01_working_extract").exists()
    assert not (completed_m1_run / "02_inventory").exists()
    assert result.receipt_path == (
        completed_m1_run / "05_receipts" / "extraction_receipt.json"
    )
    assert verify_receipt_hash(result.payload) is True


@pytest.mark.parametrize(
    "relative_path",
    [
        ".m2_staging",
        "01_working_extract",
        "02_inventory",
        "05_receipts/extraction_receipt.json",
    ],
)
def test_existing_output_or_staging_path_is_refused_without_cleanup(
    synthetic_run_factory,
    relative_path: str,
) -> None:
    run_root = synthetic_run_factory.create([("conversations.json", "[]")])
    collision = run_root.joinpath(*relative_path.split("/"))
    if collision.suffix:
        collision.parent.mkdir(parents=True, exist_ok=True)
        collision.write_text("keep", encoding="utf-8")
    else:
        collision.mkdir(parents=True)
        (collision / "sentinel.txt").write_text("keep", encoding="utf-8")
    before = _tree_snapshot(run_root)

    result = run_milestone2(run_root, disk_usage_provider=_ample_space)

    assert result.success is False
    assert result.payload["errors"][0]["reason_code"] == "extraction_path_collision"
    assert result.receipt_path is None
    assert _tree_snapshot(run_root) == before


def test_insufficient_disk_is_refused_before_staging(completed_m1_run: Path) -> None:
    def no_space(_path: Path) -> SimpleNamespace:
        return SimpleNamespace(free=1)

    result = run_milestone2(completed_m1_run, disk_usage_provider=no_space)

    assert result.success is False
    assert result.payload["errors"][0]["reason_code"] == "insufficient_disk_space"
    assert not (completed_m1_run / ".m2_staging").exists()
    assert not (completed_m1_run / "05_receipts" / "extraction_receipt.json").exists()


def test_policy_v1_cannot_be_weakened(completed_m1_run: Path) -> None:
    result = plan_milestone2(
        completed_m1_run,
        policy=ArchivePolicy(max_archive_members=10_001),
        disk_usage_provider=_ample_space,
    )

    assert result.success is False
    assert result.payload["errors"][0]["reason_code"] == "archive_policy_violation"
    assert not (completed_m1_run / ".m2_staging").exists()


def test_actual_stream_limit_failure_cleans_staging(
    synthetic_run_factory,
) -> None:
    run_root = synthetic_run_factory.create([("conversations.json", b"x" * 20)])

    result = run_milestone2(
        run_root,
        policy=ArchivePolicy(max_actual_total_bytes=10),
        disk_usage_provider=_ample_space,
        chunk_size=4,
    )

    assert result.success is False
    assert result.payload["errors"][0]["reason_code"] == "archive_policy_violation"
    assert result.payload["cleanup_result"]["status"] == "completed"
    assert not (run_root / ".m2_staging").exists()
    assert not (run_root / "01_working_extract").exists()
    assert not (run_root / "02_inventory").exists()


def test_inventory_generation_failure_cleans_staging(
    completed_m1_run: Path,
    monkeypatch,
) -> None:
    def fail_inventory(*args, **kwargs):
        raise InventoryError("injected inventory failure")

    monkeypatch.setattr(milestone2_module, "write_inventories", fail_inventory)

    result = run_milestone2(completed_m1_run, disk_usage_provider=_ample_space)

    assert result.success is False
    assert result.payload["errors"][0]["reason_code"] == "inventory_failed"
    assert not (completed_m1_run / ".m2_staging").exists()
    assert not (completed_m1_run / "01_working_extract").exists()
    assert not (completed_m1_run / "02_inventory").exists()
    assert result.receipt_path is not None


def test_cleanup_failure_is_visible_and_leaves_unpromoted_staging(
    completed_m1_run: Path,
    monkeypatch,
) -> None:
    def fail_inventory(*args, **kwargs):
        raise InventoryError("injected inventory failure")

    def fail_cleanup(_path: Path) -> None:
        raise OSError("injected cleanup failure")

    monkeypatch.setattr(milestone2_module, "write_inventories", fail_inventory)
    monkeypatch.setattr(milestone2_module.shutil, "rmtree", fail_cleanup)

    result = run_milestone2(completed_m1_run, disk_usage_provider=_ample_space)

    assert result.success is False
    assert result.payload["cleanup_result"]["status"] == "failed"
    assert result.payload["cleanup_result"]["failed"]
    assert (completed_m1_run / ".m2_staging").exists()
    assert not (completed_m1_run / "01_working_extract").exists()
    assert not (completed_m1_run / "02_inventory").exists()


@pytest.mark.parametrize("fail_on_call", [1, 2])
def test_promotion_failure_rolls_back_only_attempt_outputs(
    synthetic_run_factory,
    monkeypatch,
    fail_on_call: int,
) -> None:
    run_root = synthetic_run_factory.create([("conversations.json", "[]")])
    original_promote = milestone2_module.promote_directory_no_replace
    calls = 0

    def failing_promote(source: Path, destination: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == fail_on_call:
            raise PromotionError("injected promotion failure")
        original_promote(source, destination)

    monkeypatch.setattr(milestone2_module, "promote_directory_no_replace", failing_promote)

    result = run_milestone2(run_root, disk_usage_provider=_ample_space)

    assert result.success is False
    assert result.payload["errors"][0]["reason_code"] == "promotion_failed"
    assert not (run_root / ".m2_staging").exists()
    assert not (run_root / "01_working_extract").exists()
    assert not (run_root / "02_inventory").exists()


def test_receipt_write_failure_rolls_back_promoted_directories(
    completed_m1_run: Path,
    monkeypatch,
) -> None:
    def fail_receipt(_path: Path, _receipt: dict) -> Path:
        raise ReceiptWriteError("injected receipt failure")

    monkeypatch.setattr(
        milestone2_module,
        "write_extraction_receipt_exclusive",
        fail_receipt,
    )

    result = run_milestone2(completed_m1_run, disk_usage_provider=_ample_space)

    assert result.success is False
    assert result.payload["errors"][0]["reason_code"] == "receipt_write_failed"
    assert result.receipt_path is None
    assert not (completed_m1_run / ".m2_staging").exists()
    assert not (completed_m1_run / "01_working_extract").exists()
    assert not (completed_m1_run / "02_inventory").exists()
    assert not (completed_m1_run / "05_receipts" / "extraction_receipt.json").exists()
