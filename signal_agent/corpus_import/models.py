from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path


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
