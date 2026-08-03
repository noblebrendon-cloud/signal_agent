from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path
from typing import Callable

import pytest

from signal_agent.corpus_import.hashing import canonical_json, sha256_file
from signal_agent.corpus_import.milestone1 import run_milestone1
from signal_agent.corpus_import.receipts import SCHEMA_VERSION, seal_receipt


@pytest.fixture
def valid_export_zip(tmp_path: Path) -> Path:
    source = tmp_path / "chatgpt-export.zip"
    with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("conversations.json", json.dumps([{"id": "c1", "title": "Fixture"}]))
        archive.writestr("user.json", json.dumps({"id": "u1"}))
    return source


@pytest.fixture
def completed_m1_run(valid_export_zip: Path, tmp_path: Path) -> Path:
    run_root = tmp_path / "completed-m1-run"
    result = run_milestone1(valid_export_zip, run_root)
    assert result.success is True
    return run_root


class SyntheticRunFactory:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.counter = 0

    def create(
        self,
        members: list[tuple[str, bytes | str]],
        *,
        compression: int = zipfile.ZIP_DEFLATED,
    ) -> Path:
        source = self.root / f"synthetic-source-{self.counter}.zip"
        with zipfile.ZipFile(source, "w", compression=compression) as archive:
            for name, content in members:
                archive.writestr(name, content)
        return self.freeze(source)

    def create_with_writer(self, writer: Callable[[zipfile.ZipFile], None]) -> Path:
        source = self.root / f"synthetic-source-{self.counter}.zip"
        with zipfile.ZipFile(source, "w") as archive:
            writer(archive)
        return self.freeze(source)

    def freeze(self, source: Path) -> Path:
        self.counter += 1
        run_root = self.root / f"synthetic-run-{self.counter}"
        original_dir = run_root / "00_original"
        receipt_dir = run_root / "05_receipts"
        original_dir.mkdir(parents=True)
        receipt_dir.mkdir()
        preserved = original_dir / "export.zip"
        shutil.copyfile(source, preserved)
        source_sha256 = sha256_file(preserved)
        (original_dir / "export.zip.sha256.txt").write_text(
            f"{source_sha256}  export.zip\n",
            encoding="utf-8",
            newline="\n",
        )
        with zipfile.ZipFile(preserved) as archive:
            infos = archive.infolist()
        conversation_members = sorted(
            info.filename
            for info in infos
            if Path(info.filename.replace("\\", "/")).name.lower().startswith("conversations")
            and Path(info.filename.replace("\\", "/")).suffix.lower() == ".json"
        )
        receipt = seal_receipt(
            {
                "schema_version": SCHEMA_VERSION,
                "receipt_id": f"validation.{source_sha256[:12]}",
                "created_at": "2026-01-01T00:00:00Z",
                "status": "completed",
                "milestone": 1,
                "operation": "validate_hash_preserve",
                "source": {
                    "source_type": "chatgpt_export_zip",
                    "sha256": source_sha256,
                    "size_bytes": preserved.stat().st_size,
                    "observed_path": str(source.resolve()),
                    "preserved_path": str(preserved.resolve()),
                    "archive_entries": len(infos),
                    "conversation_json_files": len(conversation_members),
                },
                "run_root": str(run_root.resolve()),
                "validation": {
                    "source_exists": True,
                    "archive_opened": True,
                    "conversation_data_present": bool(conversation_members),
                    "conversation_members": conversation_members,
                },
                "original_preserved": True,
                "hash_verified": True,
                "source_stat_stable": True,
                "overwrite_policy": "refuse",
                "completed_stages": [
                    "validation_completed",
                    "source_identity_computed",
                    "source_preserved",
                ],
                "failed_stage": None,
                "safe_resume_point": "milestone_2",
                "observed_writes": [
                    str(preserved.resolve()),
                    str((original_dir / "export.zip.sha256.txt").resolve()),
                    str((receipt_dir / "validation_receipt.json").resolve()),
                ],
                "warnings": [],
                "errors": [],
                "fixture_write_authorization": "none",
                "publication_authorization": "none",
            }
        )
        (receipt_dir / "validation_receipt.json").write_text(
            canonical_json(receipt) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        return run_root


@pytest.fixture
def synthetic_run_factory(tmp_path: Path) -> SyntheticRunFactory:
    return SyntheticRunFactory(tmp_path)
