from __future__ import annotations

from pathlib import Path

import pytest

from signal_agent.corpus_import.errors import ProtectedFixtureError, RunCollisionError
from signal_agent.corpus_import.hashing import sha256_file
from signal_agent.corpus_import.milestone1 import run_milestone1
from signal_agent.corpus_import.preservation import prepare_run_root


def test_milestone1_preserves_identical_source_without_modifying_input(
    valid_export_zip: Path,
    tmp_path: Path,
) -> None:
    before_hash = sha256_file(valid_export_zip)
    before_stat = valid_export_zip.stat()
    run_root = tmp_path / "run-001"

    result = run_milestone1(valid_export_zip, run_root)

    preserved = run_root / "00_original" / "export.zip"
    hash_record = run_root / "00_original" / "export.zip.sha256.txt"
    assert result.success is True
    assert preserved.exists() is True
    assert sha256_file(preserved) == before_hash
    assert hash_record.read_text(encoding="utf-8") == f"{before_hash}  export.zip\n"
    assert sha256_file(valid_export_zip) == before_hash
    after_stat = valid_export_zip.stat()
    assert after_stat.st_size == before_stat.st_size
    assert after_stat.st_mtime_ns == before_stat.st_mtime_ns


def test_nonempty_run_root_is_refused_without_overwrite(valid_export_zip: Path, tmp_path: Path) -> None:
    run_root = tmp_path / "run-001"
    run_root.mkdir()
    sentinel = run_root / "sentinel.txt"
    sentinel.write_text("keep", encoding="utf-8")

    result = run_milestone1(valid_export_zip, run_root)

    assert result.success is False
    assert result.receipt["errors"][0]["reason_code"] == "run_collision"
    assert sentinel.read_text(encoding="utf-8") == "keep"
    assert list(run_root.iterdir()) == [sentinel]


def test_second_run_refuses_silent_overwrite(valid_export_zip: Path, tmp_path: Path) -> None:
    run_root = tmp_path / "run-001"
    first = run_milestone1(valid_export_zip, run_root)
    preserved = run_root / "00_original" / "export.zip"
    first_hash = sha256_file(preserved)

    second = run_milestone1(valid_export_zip, run_root)

    assert first.success is True
    assert second.success is False
    assert second.receipt["errors"][0]["reason_code"] == "run_collision"
    assert sha256_file(preserved) == first_hash


def test_fixture_paths_are_rejected(tmp_path: Path) -> None:
    fixture_run = tmp_path / "fixtures" / "manual_calibration_v1" / "run"

    with pytest.raises(ProtectedFixtureError):
        prepare_run_root(fixture_run)

    assert fixture_run.exists() is False
