from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, TypeAlias


JsonScalar: TypeAlias = str | int | float | bool | None
ImmutableMetadata: TypeAlias = tuple[tuple[str, JsonScalar], ...]

_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PREFIXED_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


def _require_relative_path(value: str, field_name: str) -> None:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "\\" in value:
        raise ValueError(f"{field_name}_must_be_safe_relative_posix_path")


def _require_immutable_metadata(value: ImmutableMetadata, field_name: str) -> None:
    keys = [key for key, _item in value]
    if keys != sorted(keys) or len(keys) != len(set(keys)):
        raise ValueError(f"{field_name}_keys_must_be_unique_and_sorted")
    if any(not isinstance(key, str) or not key for key in keys):
        raise ValueError(f"{field_name}_keys_must_be_nonempty_strings")
    if any(
        not isinstance(item, (str, int, float, bool, type(None)))
        for _key, item in value
    ):
        raise ValueError(f"{field_name}_values_must_be_json_scalars")


@dataclass(frozen=True)
class SourceReceiptDescriptor:
    """Opaque downstream reference to an adapter-owned persisted receipt."""

    receipt_id: str
    receipt_hash: str
    source_sha256: str
    persisted_relative_path: str
    schema_version: str
    protection_metadata: ImmutableMetadata = ()

    def __post_init__(self) -> None:
        if not self.receipt_id or not self.schema_version:
            raise ValueError("source_receipt_identity_required")
        if not _PREFIXED_SHA256.fullmatch(self.receipt_hash):
            raise ValueError("source_receipt_hash_invalid")
        if not _HEX_SHA256.fullmatch(self.source_sha256):
            raise ValueError("source_sha256_invalid")
        _require_relative_path(self.persisted_relative_path, "source_receipt_path")
        _require_immutable_metadata(self.protection_metadata, "protection_metadata")

    def protection_dict(self) -> dict[str, JsonScalar]:
        return dict(self.protection_metadata)


@dataclass(frozen=True)
class PreservedEvidence:
    """Neutral immutable result of source preservation."""

    source_sha256: str
    preserved_relative_path: str
    source_receipt: SourceReceiptDescriptor
    provenance_metadata: ImmutableMetadata = ()

    def __post_init__(self) -> None:
        if not _HEX_SHA256.fullmatch(self.source_sha256):
            raise ValueError("source_sha256_invalid")
        if self.source_sha256 != self.source_receipt.source_sha256:
            raise ValueError("preserved_source_receipt_sha256_mismatch")
        _require_relative_path(self.preserved_relative_path, "preserved_source_path")
        _require_immutable_metadata(self.provenance_metadata, "provenance_metadata")


@dataclass(frozen=True)
class NormalizedRelationshipBatch:
    """Relationship-only normalization boundary consumed by Signal Agent."""

    preserved: PreservedEvidence
    records: tuple[dict[str, Any], ...]
    unresolved_matches: dict[str, Any]
