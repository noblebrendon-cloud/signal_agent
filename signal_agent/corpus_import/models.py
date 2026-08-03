from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ZipValidationResult:
    archive_entries: int
    conversation_json_files: int
    conversation_members: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "archive_entries": self.archive_entries,
            "conversation_json_files": self.conversation_json_files,
            "conversation_members": list(self.conversation_members),
        }


@dataclass(frozen=True)
class SourceIdentity:
    source_type: str
    sha256: str
    size_bytes: int
    observed_path: str
    preserved_path: str | None
    archive_entries: int
    conversation_json_files: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PreservationResult:
    preserved_path: Path
    hash_record_path: Path
    preserved_sha256: str
    size_bytes: int


@dataclass(frozen=True)
class Milestone1Result:
    success: bool
    receipt: dict
    receipt_path: Path | None

    @property
    def exit_code(self) -> int:
        return 0 if self.success else 1


@dataclass(frozen=True)
class ArchivePolicy:
    version: str = "chatgpt_export_archive_security_policy.v1"
    max_archive_members: int = 10_000
    max_declared_total_bytes: int = 4 * 1024**3
    max_actual_total_bytes: int = 4 * 1024**3
    max_member_bytes: int = 512 * 1024**2
    max_expansion_ratio: float = 100.0
    max_path_length: int = 1_024
    max_component_length: int = 255
    required_space_margin_bytes: int = 1024**3

    def limits_dict(self) -> dict[str, int | float]:
        return {
            "max_actual_total_bytes": self.max_actual_total_bytes,
            "max_archive_members": self.max_archive_members,
            "max_component_length": self.max_component_length,
            "max_declared_total_bytes": self.max_declared_total_bytes,
            "max_expansion_ratio": self.max_expansion_ratio,
            "max_member_bytes": self.max_member_bytes,
            "max_path_length": self.max_path_length,
            "required_space_margin_bytes": self.required_space_margin_bytes,
        }

    def to_dict(self) -> dict[str, Any]:
        return {"version": self.version, "limits": self.limits_dict()}


@dataclass(frozen=True)
class ArchiveEntry:
    archive_ordinal: int
    source_name: str
    normalized_path: str
    entry_type: str
    uncompressed_bytes: int
    compressed_bytes: int
    crc32: str
    compression_method: int
    flag_bits: int
    external_attr: int
    header_offset: int

    def inventory_dict(self) -> dict[str, Any]:
        return {
            "archive_ordinal": self.archive_ordinal,
            "path": self.normalized_path,
            "entry_type": self.entry_type,
            "uncompressed_bytes": self.uncompressed_bytes,
            "compressed_bytes": self.compressed_bytes,
            "crc32": self.crc32,
            "compression_method": self.compression_method,
        }


@dataclass(frozen=True)
class ArchivePlan:
    entries: tuple[ArchiveEntry, ...]
    archive_member_count: int
    archive_file_count: int
    archive_directory_count: int
    conversation_json_files: int
    declared_uncompressed_bytes: int
    declared_compressed_bytes: int
    required_free_bytes: int
    available_free_bytes: int


@dataclass(frozen=True)
class ExtractedFile:
    path: str
    size_bytes: int
    sha256: str
    archive_ordinal: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExtractionResult:
    files: tuple[ExtractedFile, ...]
    directories: tuple[str, ...]
    actual_bytes_written: int


@dataclass(frozen=True)
class InventoryArtifact:
    path: str
    sha256: str
    size_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InventoryResult:
    artifacts: tuple[InventoryArtifact, ...]
    extracted_tree_digest: str


@dataclass(frozen=True)
class ParentValidationContext:
    run_root: Path
    receipt_path: Path
    receipt: dict[str, Any]
    preserved_path: Path
    source_sha256: str
    source_size: int
    initial_stat: tuple[int, int, int, int]


@dataclass(frozen=True)
class Milestone2Result:
    success: bool
    payload: dict[str, Any]
    receipt_path: Path | None = None

    @property
    def exit_code(self) -> int:
        return 0 if self.success else 1
