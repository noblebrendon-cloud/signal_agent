from __future__ import annotations

import csv
import fnmatch
import io
import os
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from .errors import CorpusImportError, ExtractionCollisionError, InventoryError
from .hashing import canonical_json, sha256_canonical_json, sha256_file
from .models import (
    ArchivePlan,
    ExtractedFile,
    ExtractionResult,
    InventoryArtifact,
    InventoryResult,
)


ARCHIVE_ENTRY_FIELDS = (
    "archive_ordinal",
    "path",
    "entry_type",
    "uncompressed_bytes",
    "compressed_bytes",
    "crc32",
    "compression_method",
)
EXTRACTED_FILE_FIELDS = ("path", "size_bytes", "sha256", "archive_ordinal")
EXTENSION_FIELDS = ("extension", "file_count", "total_bytes")
LARGEST_FILE_FIELDS = ("path", "size_bytes", "sha256")
TOP_LEVEL_FIELDS = ("name", "entry_type", "file_count", "total_bytes")
CONVERSATION_FILE_FIELDS = ("path", "size_bytes", "sha256")


def _write_bytes_exclusive(path: Path, payload: bytes) -> None:
    try:
        with Path(path).open("xb") as handle:
            written = handle.write(payload)
            if written != len(payload):
                raise InventoryError(
                    "Short write while creating inventory artifact.",
                    context={
                        "path": path.name,
                        "requested_bytes": len(payload),
                        "written_bytes": written,
                    },
                )
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise ExtractionCollisionError(f"Refusing to overwrite inventory artifact: {path}") from exc
    except CorpusImportError:
        raise
    except OSError as exc:
        raise InventoryError(f"Unable to write inventory artifact '{path.name}': {exc}") from exc


def _write_json(path: Path, payload: Any) -> None:
    _write_bytes_exclusive(path, (canonical_json(payload) + "\n").encode("utf-8"))


def _csv_bytes(fieldnames: Iterable[str], rows: Iterable[dict[str, Any]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=list(fieldnames),
        extrasaction="raise",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def _extension_rows(files: tuple[ExtractedFile, ...]) -> list[dict[str, Any]]:
    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    counts[""]
    for item in files:
        extension = PurePosixPath(item.path).suffix.lower()
        counts[extension][0] += 1
        counts[extension][1] += item.size_bytes
    return [
        {"extension": extension, "file_count": values[0], "total_bytes": values[1]}
        for extension, values in sorted(counts.items())
    ]


def _top_level_rows(
    files: tuple[ExtractedFile, ...],
    directories: tuple[str, ...],
) -> list[dict[str, Any]]:
    top_level: dict[str, dict[str, Any]] = {}
    directory_roots = {PurePosixPath(path).parts[0] for path in directories}
    for item in files:
        parts = PurePosixPath(item.path).parts
        name = parts[0]
        row = top_level.setdefault(
            name,
            {
                "name": name,
                "entry_type": "directory" if len(parts) > 1 or name in directory_roots else "file",
                "file_count": 0,
                "total_bytes": 0,
            },
        )
        if len(parts) > 1:
            row["entry_type"] = "directory"
        row["file_count"] += 1
        row["total_bytes"] += item.size_bytes
    for name in directory_roots:
        top_level.setdefault(
            name,
            {
                "name": name,
                "entry_type": "directory",
                "file_count": 0,
                "total_bytes": 0,
            },
        )
    return [top_level[name] for name in sorted(top_level)]


def _is_conversation_file(path: str) -> bool:
    return fnmatch.fnmatchcase(PurePosixPath(path).name.lower(), "conversations*.json")


def compute_extracted_tree_digest(files: tuple[ExtractedFile, ...]) -> str:
    material = [
        {"path": item.path, "sha256": item.sha256, "size_bytes": item.size_bytes}
        for item in sorted(files, key=lambda candidate: candidate.path)
    ]
    return f"sha256:{sha256_canonical_json(material)}"


def _artifact_record(inventory_root: Path, filename: str) -> InventoryArtifact:
    path = inventory_root / filename
    return InventoryArtifact(
        path=f"02_inventory/{filename}",
        sha256=sha256_file(path),
        size_bytes=path.stat().st_size,
    )


def write_inventories(
    inventory_root: Path,
    *,
    archive_plan: ArchivePlan,
    extraction_result: ExtractionResult,
) -> InventoryResult:
    """Write all deterministic Milestone 2 inventory artifacts exclusively."""

    inventory_root = Path(inventory_root)
    if inventory_root.exists():
        raise ExtractionCollisionError(f"Inventory staging directory already exists: {inventory_root}")
    inventory_root.mkdir(parents=True, exist_ok=False)

    archive_rows = [
        entry.inventory_dict()
        for entry in sorted(
            archive_plan.entries,
            key=lambda candidate: (candidate.normalized_path, candidate.archive_ordinal),
        )
    ]
    extracted_rows = [
        item.to_dict() for item in sorted(extraction_result.files, key=lambda candidate: candidate.path)
    ]
    extension_rows = _extension_rows(extraction_result.files)
    largest_rows = [
        {"path": item.path, "size_bytes": item.size_bytes, "sha256": item.sha256}
        for item in sorted(
            extraction_result.files,
            key=lambda candidate: (-candidate.size_bytes, candidate.path),
        )[:100]
    ]
    top_level_rows = _top_level_rows(extraction_result.files, extraction_result.directories)
    conversation_rows = [
        {"path": item.path, "size_bytes": item.size_bytes, "sha256": item.sha256}
        for item in extraction_result.files
        if _is_conversation_file(item.path)
    ]
    tree_digest = compute_extracted_tree_digest(extraction_result.files)

    deterministic_payloads: list[tuple[str, bytes]] = [
        (
            "archive_entries.csv",
            _csv_bytes(ARCHIVE_ENTRY_FIELDS, archive_rows),
        ),
        (
            "archive_entries.json",
            (
                canonical_json(
                    {
                        "entries": archive_rows,
                        "schema_version": "chatgpt_export_archive_inventory.v1",
                    }
                )
                + "\n"
            ).encode("utf-8"),
        ),
        (
            "extracted_files.csv",
            _csv_bytes(EXTRACTED_FILE_FIELDS, extracted_rows),
        ),
        (
            "extracted_files.json",
            (
                canonical_json(
                    {
                        "files": extracted_rows,
                        "schema_version": "chatgpt_export_extracted_file_inventory.v1",
                    }
                )
                + "\n"
            ).encode("utf-8"),
        ),
        (
            "file_counts_by_extension.csv",
            _csv_bytes(EXTENSION_FIELDS, extension_rows),
        ),
        (
            "largest_100_files.csv",
            _csv_bytes(LARGEST_FILE_FIELDS, largest_rows),
        ),
        (
            "top_level_contents.csv",
            _csv_bytes(TOP_LEVEL_FIELDS, top_level_rows),
        ),
        (
            "conversation_json_files.csv",
            _csv_bytes(CONVERSATION_FILE_FIELDS, conversation_rows),
        ),
    ]
    for filename, payload in deterministic_payloads:
        _write_bytes_exclusive(inventory_root / filename, payload)

    summary = {
        "actual_bytes_written": extraction_result.actual_bytes_written,
        "archive_directory_count": archive_plan.archive_directory_count,
        "archive_file_count": archive_plan.archive_file_count,
        "archive_member_count": archive_plan.archive_member_count,
        "conversation_json_files": archive_plan.conversation_json_files,
        "declared_uncompressed_bytes": archive_plan.declared_uncompressed_bytes,
        "extracted_directory_count": len(extraction_result.directories),
        "extracted_file_count": len(extraction_result.files),
        "extracted_tree_digest": tree_digest,
        "schema_version": "chatgpt_export_extraction_summary.v1",
    }
    _write_json(inventory_root / "extraction_summary.json", summary)

    artifact_names = [
        "archive_entries.csv",
        "archive_entries.json",
        "conversation_json_files.csv",
        "extracted_files.csv",
        "extracted_files.json",
        "extraction_summary.json",
        "file_counts_by_extension.csv",
        "largest_100_files.csv",
        "top_level_contents.csv",
    ]
    pre_manifest_artifacts = tuple(
        _artifact_record(inventory_root, filename) for filename in sorted(artifact_names)
    )
    manifest = {
        "artifacts": [artifact.to_dict() for artifact in pre_manifest_artifacts],
        "extracted_tree_digest": tree_digest,
        "schema_version": "chatgpt_export_inventory_manifest.v1",
    }
    _write_json(inventory_root / "inventory_manifest.json", manifest)
    all_artifacts = pre_manifest_artifacts + (
        _artifact_record(inventory_root, "inventory_manifest.json"),
    )
    return InventoryResult(
        artifacts=tuple(sorted(all_artifacts, key=lambda artifact: artifact.path)),
        extracted_tree_digest=tree_digest,
    )
