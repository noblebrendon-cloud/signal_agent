from __future__ import annotations

import fnmatch
import re
import stat
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath

from .errors import (
    ArchiveMemberCollisionError,
    ArchivePolicyError,
    CorpusImportError,
    InsufficientDiskSpaceError,
    UnreadableArchiveError,
    UnsafeArchivePathError,
    UnsupportedArchiveMemberError,
)
from .models import ArchiveEntry, ArchivePlan, ArchivePolicy


SUPPORTED_COMPRESSION_METHODS = frozenset(
    {
        zipfile.ZIP_STORED,
        zipfile.ZIP_DEFLATED,
        zipfile.ZIP_BZIP2,
        zipfile.ZIP_LZMA,
    }
)
_DRIVE_PATH = re.compile(r"^[A-Za-z]:")
_WINDOWS_RESERVED = {
    "AUX",
    "CLOCK$",
    "CON",
    "CONIN$",
    "CONOUT$",
    "NUL",
    "PRN",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}
_WINDOWS_INVALID_CHARACTERS = frozenset('<>"|?*')


def _raise_unsafe(name: str, check: str, message: str) -> None:
    raise UnsafeArchivePathError(
        message,
        context={"archive_member": name, "security_check": check},
    )


def normalize_member_path(name: str) -> tuple[str, bool]:
    """Return a safe NFC-normalized POSIX path and whether it is a directory."""

    if not isinstance(name, str) or not name:
        _raise_unsafe(str(name), "malformed_name", "Archive member has an empty or invalid name.")
    if "\x00" in name:
        _raise_unsafe(name, "nul_character", "Archive member name contains a NUL character.")
    if any(ord(character) < 32 or ord(character) == 127 for character in name):
        _raise_unsafe(name, "control_character", "Archive member name contains a control character.")
    if name.startswith("//"):
        _raise_unsafe(name, "unc_path", "UNC archive member paths are not permitted.")
    if name.startswith("/"):
        _raise_unsafe(name, "posix_absolute_path", "Absolute archive member paths are not permitted.")
    if _DRIVE_PATH.match(name):
        _raise_unsafe(name, "drive_qualified_path", "Drive-qualified archive member paths are not permitted.")
    if "\\" in name:
        check = "root_relative_windows_path" if name.startswith("\\") else "ambiguous_backslash_mapping"
        _raise_unsafe(name, check, "Backslashes in archive member paths are not permitted.")

    is_directory = name.endswith("/")
    untrimmed = name[:-1] if is_directory else name
    if not untrimmed:
        _raise_unsafe(name, "empty_path", "Archive member does not name a relative path.")

    components: list[str] = []
    for component in untrimmed.split("/"):
        if component == "":
            continue
        if component in {".", ".."}:
            check = "path_traversal" if component == ".." else "ambiguous_dot_component"
            _raise_unsafe(name, check, "Dot path components are not permitted in archive members.")

        normalized = unicodedata.normalize("NFC", component)
        if normalized.endswith((".", " ")):
            _raise_unsafe(name, "trailing_dot_or_space", "Path components may not end in a dot or space.")
        if ":" in normalized:
            _raise_unsafe(name, "alternate_data_stream", "Colons are not permitted in archive member paths.")
        if any(character in _WINDOWS_INVALID_CHARACTERS for character in normalized):
            _raise_unsafe(name, "windows_invalid_character", "Archive member uses an invalid Windows filename.")

        reserved_candidate = normalized.split(".", 1)[0].upper()
        if reserved_candidate in _WINDOWS_RESERVED:
            _raise_unsafe(name, "windows_reserved_name", "Archive member uses a reserved Windows filename.")
        components.append(normalized)

    if not components:
        _raise_unsafe(name, "empty_path", "Archive member normalizes to an empty path.")
    return "/".join(components), is_directory


def _validate_path_lengths(entry: ArchiveEntry, policy: ArchivePolicy) -> None:
    if len(entry.normalized_path) > policy.max_path_length:
        raise ArchivePolicyError(
            "Archive member path exceeds the configured maximum length.",
            context={
                "archive_member": entry.source_name,
                "configured_limit": policy.max_path_length,
                "observed_length": len(entry.normalized_path),
                "policy_field": "max_path_length",
            },
        )
    for component in PurePosixPath(entry.normalized_path).parts:
        if len(component) > policy.max_component_length:
            raise ArchivePolicyError(
                "Archive member path component exceeds the configured maximum length.",
                context={
                    "archive_member": entry.source_name,
                    "component": component,
                    "configured_limit": policy.max_component_length,
                    "observed_length": len(component),
                    "policy_field": "max_component_length",
                },
            )


def _entry_type(info: zipfile.ZipInfo) -> str:
    if info.flag_bits & 0x1:
        raise UnsupportedArchiveMemberError(
            "Encrypted archive members are not permitted.",
            context={"archive_member": info.filename, "member_type": "encrypted"},
        )
    if info.compress_type not in SUPPORTED_COMPRESSION_METHODS:
        raise UnsupportedArchiveMemberError(
            "Archive member uses an unsupported compression method.",
            context={
                "archive_member": info.filename,
                "compression_method": info.compress_type,
            },
        )

    mode = (info.external_attr >> 16) & 0xFFFF
    filesystem_type = stat.S_IFMT(mode)
    named_directory = info.is_dir() or info.filename.endswith("/")
    if named_directory:
        if info.file_size != 0 or info.compress_size != 0:
            raise UnsupportedArchiveMemberError(
                "Directory archive members must not contain file data.",
                context={
                    "archive_member": info.filename,
                    "compressed_bytes": info.compress_size,
                    "uncompressed_bytes": info.file_size,
                },
            )
        if filesystem_type not in {0, stat.S_IFDIR}:
            raise UnsupportedArchiveMemberError(
                "Directory-named archive member has a non-directory filesystem type.",
                context={"archive_member": info.filename, "unix_mode": mode},
            )
        return "directory"
    if filesystem_type not in {0, stat.S_IFREG}:
        member_types = {
            stat.S_IFLNK: "symlink",
            stat.S_IFCHR: "character_device",
            stat.S_IFBLK: "block_device",
            stat.S_IFIFO: "fifo",
            stat.S_IFSOCK: "socket",
            stat.S_IFDIR: "directory",
        }
        raise UnsupportedArchiveMemberError(
            "Only regular files and directories may be extracted.",
            context={
                "archive_member": info.filename,
                "member_type": member_types.get(filesystem_type, "nonregular"),
                "unix_mode": mode,
            },
        )
    return "file"


def _validate_member_limits(entry: ArchiveEntry, policy: ArchivePolicy) -> None:
    if entry.uncompressed_bytes > policy.max_member_bytes:
        raise ArchivePolicyError(
            "Archive member exceeds the configured declared-size limit.",
            context={
                "archive_member": entry.source_name,
                "configured_limit": policy.max_member_bytes,
                "declared_bytes": entry.uncompressed_bytes,
                "policy_field": "max_member_bytes",
            },
        )
    if entry.entry_type == "file" and entry.uncompressed_bytes:
        ratio = (
            float("inf")
            if entry.compressed_bytes == 0
            else entry.uncompressed_bytes / entry.compressed_bytes
        )
        if ratio > policy.max_expansion_ratio:
            raise ArchivePolicyError(
                "Archive member exceeds the configured expansion-ratio limit.",
                context={
                    "archive_member": entry.source_name,
                    "configured_limit": policy.max_expansion_ratio,
                    "declared_ratio": ratio,
                    "policy_field": "max_expansion_ratio",
                },
            )


def _check_collisions(entries: list[ArchiveEntry]) -> None:
    source_names: set[str] = set()
    normalized_names: dict[str, ArchiveEntry] = {}
    normalization_targets: dict[str, str] = {}
    target_keys: dict[str, tuple[str, str]] = {}

    for entry in entries:
        if entry.source_name in source_names:
            raise ArchiveMemberCollisionError(
                "Archive contains an exact duplicate member.",
                context={
                    "archive_member": entry.source_name,
                    "collision_type": "exact_duplicate",
                },
            )
        source_names.add(entry.source_name)

        prior = normalized_names.get(entry.normalized_path)
        if prior is not None:
            prior_nfc = unicodedata.normalize("NFC", prior.source_name.rstrip("/"))
            current_nfc = unicodedata.normalize("NFC", entry.source_name.rstrip("/"))
            if prior.entry_type != entry.entry_type:
                collision_type = "file_directory_conflict"
            elif prior_nfc == current_nfc and prior.source_name != entry.source_name:
                collision_type = "unicode_normalization_collision"
            else:
                collision_type = "normalized_duplicate"
            raise ArchiveMemberCollisionError(
                "Archive members resolve to the same normalized output path.",
                context={
                    "archive_member": entry.source_name,
                    "conflicting_member": prior.source_name,
                    "collision_type": collision_type,
                    "normalized_path": entry.normalized_path,
                },
            )
        normalized_names[entry.normalized_path] = entry

        parts = PurePosixPath(entry.normalized_path).parts
        source_parts = tuple(
            component
            for component in entry.source_name.rstrip("/").split("/")
            if component
        )
        for index in range(1, len(parts) + 1):
            target_path = "/".join(parts[:index])
            source_prefix = "/".join(source_parts[:index])
            target_type = entry.entry_type if index == len(parts) else "directory"
            prior_source_prefix = normalization_targets.get(target_path)
            if (
                prior_source_prefix is not None
                and prior_source_prefix != source_prefix
                and unicodedata.normalize("NFC", prior_source_prefix)
                == unicodedata.normalize("NFC", source_prefix)
            ):
                raise ArchiveMemberCollisionError(
                    "Archive contains a Unicode-normalization collision.",
                    context={
                        "archive_member": entry.source_name,
                        "collision_type": "unicode_normalization_collision",
                        "conflicting_path": prior_source_prefix,
                        "normalized_path": target_path,
                    },
                )
            normalization_targets.setdefault(target_path, source_prefix)
            key = target_path.casefold()
            prior_target = target_keys.get(key)
            if prior_target is not None:
                prior_path, prior_type = prior_target
                if prior_path != target_path:
                    raise ArchiveMemberCollisionError(
                        "Archive contains a case-fold or Unicode case collision.",
                        context={
                            "archive_member": entry.source_name,
                            "collision_type": "casefold_collision",
                            "conflicting_path": prior_path,
                            "normalized_path": target_path,
                        },
                    )
                if prior_type != target_type:
                    raise ArchiveMemberCollisionError(
                        "Archive contains a file/directory prefix conflict.",
                        context={
                            "archive_member": entry.source_name,
                            "collision_type": "file_directory_conflict",
                            "normalized_path": target_path,
                        },
                    )
            else:
                target_keys[key] = (target_path, target_type)


def _is_conversation_path(path: str) -> bool:
    return fnmatch.fnmatchcase(PurePosixPath(path).name.lower(), "conversations*.json")


def scan_archive(
    source: Path,
    *,
    policy: ArchivePolicy,
    available_free_bytes: int,
) -> ArchivePlan:
    """Validate the entire central directory and return a write-free extraction plan."""

    source = Path(source)
    try:
        with zipfile.ZipFile(source, mode="r") as archive:
            infos = archive.infolist()
            if len(infos) > policy.max_archive_members:
                raise ArchivePolicyError(
                    "Archive contains more members than the configured maximum.",
                    context={
                        "archive_members": len(infos),
                        "configured_limit": policy.max_archive_members,
                        "policy_field": "max_archive_members",
                    },
                )

            entries: list[ArchiveEntry] = []
            for ordinal, info in enumerate(infos):
                normalized_path, named_directory = normalize_member_path(info.filename)
                entry_type = _entry_type(info)
                if named_directory != (entry_type == "directory"):
                    raise UnsupportedArchiveMemberError(
                        "Archive member name and filesystem type disagree.",
                        context={"archive_member": info.filename},
                    )
                entry = ArchiveEntry(
                    archive_ordinal=ordinal,
                    source_name=info.filename,
                    normalized_path=normalized_path,
                    entry_type=entry_type,
                    uncompressed_bytes=info.file_size,
                    compressed_bytes=info.compress_size,
                    crc32=f"{info.CRC:08x}",
                    compression_method=info.compress_type,
                    flag_bits=info.flag_bits,
                    external_attr=info.external_attr,
                    header_offset=info.header_offset,
                )
                _validate_path_lengths(entry, policy)
                _validate_member_limits(entry, policy)
                entries.append(entry)
    except CorpusImportError:
        raise
    except (OSError, RuntimeError, UnicodeError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise UnreadableArchiveError(f"Unable to scan preserved ZIP '{source}': {exc}") from exc

    _check_collisions(entries)
    declared_total = sum(entry.uncompressed_bytes for entry in entries if entry.entry_type == "file")
    if declared_total > policy.max_declared_total_bytes:
        raise ArchivePolicyError(
            "Archive exceeds the configured declared total-size limit.",
            context={
                "configured_limit": policy.max_declared_total_bytes,
                "declared_bytes": declared_total,
                "policy_field": "max_declared_total_bytes",
            },
        )

    required_free = declared_total + policy.required_space_margin_bytes
    if available_free_bytes < required_free:
        raise InsufficientDiskSpaceError(
            "Insufficient free space for bounded extraction.",
            context={
                "available_free_bytes": available_free_bytes,
                "declared_uncompressed_bytes": declared_total,
                "required_free_bytes": required_free,
            },
        )

    return ArchivePlan(
        entries=tuple(entries),
        archive_member_count=len(entries),
        archive_file_count=sum(entry.entry_type == "file" for entry in entries),
        archive_directory_count=sum(entry.entry_type == "directory" for entry in entries),
        conversation_json_files=sum(
            entry.entry_type == "file" and _is_conversation_path(entry.normalized_path)
            for entry in entries
        ),
        declared_uncompressed_bytes=declared_total,
        declared_compressed_bytes=sum(
            entry.compressed_bytes for entry in entries if entry.entry_type == "file"
        ),
        required_free_bytes=required_free,
        available_free_bytes=available_free_bytes,
    )
