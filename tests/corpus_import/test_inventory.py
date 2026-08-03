from __future__ import annotations

import csv
import json
from pathlib import Path

from signal_agent.corpus_import.archive_safety import scan_archive
from signal_agent.corpus_import.extraction import extract_archive_to_staging
from signal_agent.corpus_import.hashing import sha256_file
from signal_agent.corpus_import.inventory import write_inventories
from signal_agent.corpus_import.models import ArchivePolicy


EXPECTED_INVENTORY_FILES = {
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
}


def _extract_fixture(run_root: Path, output_root: Path):
    policy = ArchivePolicy()
    source = run_root / "00_original" / "export.zip"
    plan = scan_archive(source, policy=policy, available_free_bytes=10 * 1024**3)
    extraction = extract_archive_to_staging(
        source,
        plan,
        output_root,
        policy=policy,
        chunk_size=7,
    )
    return plan, extraction


def test_inventory_artifacts_are_complete_and_correct(
    synthetic_run_factory,
    tmp_path: Path,
) -> None:
    run_root = synthetic_run_factory.create(
        [
            ("conversations-001.json", "[]"),
            ("nested/no_extension", "abc"),
            ("nested/alpha.txt", "12345"),
            ("nested/beta.txt", "67890"),
            ("top.bin", b"\x00\x01"),
        ]
    )
    plan, extraction = _extract_fixture(run_root, tmp_path / "extract")
    inventory_root = tmp_path / "inventory"

    result = write_inventories(
        inventory_root,
        archive_plan=plan,
        extraction_result=extraction,
    )

    assert {path.name for path in inventory_root.iterdir()} == EXPECTED_INVENTORY_FILES
    assert {artifact.path for artifact in result.artifacts} == {
        f"02_inventory/{name}" for name in EXPECTED_INVENTORY_FILES
    }

    archive_csv = (inventory_root / "archive_entries.csv").read_text(encoding="utf-8")
    assert archive_csv.splitlines()[0] == (
        "archive_ordinal,path,entry_type,uncompressed_bytes,"
        "compressed_bytes,crc32,compression_method"
    )
    assert "\r\n" not in archive_csv

    archive_json = json.loads((inventory_root / "archive_entries.json").read_text("utf-8"))
    paths = [entry["path"] for entry in archive_json["entries"]]
    assert paths == sorted(paths)

    with (inventory_root / "file_counts_by_extension.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        extension_rows = list(csv.DictReader(handle))
    empty_extension = next(row for row in extension_rows if row["extension"] == "")
    assert empty_extension["file_count"] == "1"

    with (inventory_root / "largest_100_files.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        largest_rows = list(csv.DictReader(handle))
    tied_text_paths = [
        row["path"]
        for row in largest_rows
        if row["size_bytes"] == "5"
    ]
    assert tied_text_paths == ["nested/alpha.txt", "nested/beta.txt"]

    with (inventory_root / "conversation_json_files.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        conversation_rows = list(csv.DictReader(handle))
    assert [row["path"] for row in conversation_rows] == ["conversations-001.json"]


def test_inventories_are_byte_identical_across_different_roots(
    synthetic_run_factory,
    tmp_path: Path,
) -> None:
    run_root = synthetic_run_factory.create(
        [
            ("conversations.json", '[{"id":"one"}]'),
            ("nested/data.bin", bytes(range(32))),
        ]
    )
    plan_one, extraction_one = _extract_fixture(run_root, tmp_path / "extract-one")
    plan_two, extraction_two = _extract_fixture(run_root, tmp_path / "extract-two")

    first_root = tmp_path / "inventory-one"
    second_root = tmp_path / "inventory-two"
    write_inventories(first_root, archive_plan=plan_one, extraction_result=extraction_one)
    write_inventories(second_root, archive_plan=plan_two, extraction_result=extraction_two)

    for name in EXPECTED_INVENTORY_FILES:
        assert (first_root / name).read_bytes() == (second_root / name).read_bytes()
        assert str(tmp_path).encode() not in (first_root / name).read_bytes()


def test_inventory_manifest_hashes_every_other_inventory_artifact(
    synthetic_run_factory,
    tmp_path: Path,
) -> None:
    run_root = synthetic_run_factory.create([("conversations.json", "[]")])
    plan, extraction = _extract_fixture(run_root, tmp_path / "extract")
    inventory_root = tmp_path / "inventory"

    result = write_inventories(
        inventory_root,
        archive_plan=plan,
        extraction_result=extraction,
    )
    manifest = json.loads((inventory_root / "inventory_manifest.json").read_text("utf-8"))

    assert {item["path"] for item in manifest["artifacts"]} == {
        f"02_inventory/{name}"
        for name in EXPECTED_INVENTORY_FILES
        if name != "inventory_manifest.json"
    }
    for item in manifest["artifacts"]:
        filename = item["path"].rsplit("/", 1)[-1]
        assert item["sha256"] == sha256_file(inventory_root / filename)
        assert item["size_bytes"] == (inventory_root / filename).stat().st_size
    assert manifest["extracted_tree_digest"] == result.extracted_tree_digest
    assert result.extracted_tree_digest.startswith("sha256:")
