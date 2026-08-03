from __future__ import annotations

import ctypes
import errno
import hashlib
import os
import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath

from .errors import (
    CorpusImportError,
    ExtractionCollisionError,
    ExtractionError,
    ExtractionPolicyError,
    PromotionError,
    UnsafeArchivePathError,
)
from .hashing import DEFAULT_CHUNK_SIZE
from .models import ArchiveEntry, ArchivePlan, ArchivePolicy, ExtractedFile, ExtractionResult


MAX_STREAM_CHUNK_SIZE = 1024 * 1024


def _contained_destination(root: Path, relative_path: str) -> Path:
    root = Path(root).resolve(strict=False)
    destination = root.joinpath(*PurePosixPath(relative_path).parts)
    resolved_destination = destination.resolve(strict=False)
    try:
        resolved_destination.relative_to(root)
    except ValueError as exc:
        raise UnsafeArchivePathError(
            "Archive destination escapes the staging extraction root.",
            context={"normalized_path": relative_path, "staging_root": str(root)},
        ) from exc
    return destination


def _record_parent_directories(path: str, directories: set[str]) -> None:
    parent = PurePosixPath(path).parent
    while str(parent) not in {"", "."}:
        directories.add(parent.as_posix())
        parent = parent.parent


def _info_matches_entry(info: zipfile.ZipInfo, entry: ArchiveEntry) -> bool:
    return (
        info.filename == entry.source_name
        and info.file_size == entry.uncompressed_bytes
        and info.compress_size == entry.compressed_bytes
        and f"{info.CRC:08x}" == entry.crc32
        and info.compress_type == entry.compression_method
        and info.flag_bits == entry.flag_bits
        and info.external_attr == entry.external_attr
        and info.header_offset == entry.header_offset
    )


def _enforce_actual_limits(
    *,
    entry: ArchiveEntry,
    member_bytes: int,
    total_bytes: int,
    policy: ArchivePolicy,
) -> None:
    if member_bytes > policy.max_member_bytes:
        raise ExtractionPolicyError(
            "Extracted member exceeded the configured actual single-member limit.",
            context={
                "archive_member": entry.source_name,
                "actual_bytes": member_bytes,
                "configured_limit": policy.max_member_bytes,
                "policy_field": "max_member_bytes",
            },
        )
    if total_bytes > policy.max_actual_total_bytes:
        raise ExtractionPolicyError(
            "Extraction exceeded the configured actual total-size limit.",
            context={
                "actual_bytes": total_bytes,
                "configured_limit": policy.max_actual_total_bytes,
                "policy_field": "max_actual_total_bytes",
            },
        )
    if member_bytes:
        actual_ratio = (
            float("inf") if entry.compressed_bytes == 0 else member_bytes / entry.compressed_bytes
        )
        if actual_ratio > policy.max_expansion_ratio:
            raise ExtractionPolicyError(
                "Extracted member exceeded the configured actual expansion-ratio limit.",
                context={
                    "archive_member": entry.source_name,
                    "actual_ratio": actual_ratio,
                    "configured_limit": policy.max_expansion_ratio,
                    "policy_field": "max_expansion_ratio",
                },
            )


def extract_archive_to_staging(
    source: Path,
    plan: ArchivePlan,
    extraction_root: Path,
    *,
    policy: ArchivePolicy,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> ExtractionResult:
    """Stream a preflighted archive into a new staging tree."""

    if chunk_size <= 0 or chunk_size > MAX_STREAM_CHUNK_SIZE:
        raise ValueError(f"chunk_size must be between 1 and {MAX_STREAM_CHUNK_SIZE} bytes")

    extraction_root = Path(extraction_root)
    if extraction_root.exists():
        raise ExtractionCollisionError(
            f"Staging extraction directory already exists: {extraction_root}"
        )
    extraction_root.mkdir(parents=True, exist_ok=False)

    extracted_files: list[ExtractedFile] = []
    directories: set[str] = set()
    total_bytes = 0

    try:
        with zipfile.ZipFile(source, mode="r") as archive:
            infos = archive.infolist()
            if len(infos) != len(plan.entries):
                raise ExtractionError(
                    "Archive central directory changed after preflight.",
                    context={
                        "planned_members": len(plan.entries),
                        "observed_members": len(infos),
                    },
                )

            for entry in plan.entries:
                info = infos[entry.archive_ordinal]
                if not _info_matches_entry(info, entry):
                    raise ExtractionError(
                        "Archive member metadata changed after preflight.",
                        context={
                            "archive_member": entry.source_name,
                            "archive_ordinal": entry.archive_ordinal,
                        },
                    )

                destination = _contained_destination(extraction_root, entry.normalized_path)
                if entry.entry_type == "directory":
                    destination.mkdir(parents=True, exist_ok=True)
                    directories.add(entry.normalized_path)
                    _record_parent_directories(entry.normalized_path, directories)
                    continue

                destination.parent.mkdir(parents=True, exist_ok=True)
                _record_parent_directories(entry.normalized_path, directories)
                digest = hashlib.sha256()
                member_bytes = 0

                try:
                    with archive.open(info, mode="r") as source_handle:
                        with destination.open("xb") as destination_handle:
                            while True:
                                chunk = source_handle.read(chunk_size)
                                if not chunk:
                                    break
                                member_bytes += len(chunk)
                                total_bytes += len(chunk)
                                _enforce_actual_limits(
                                    entry=entry,
                                    member_bytes=member_bytes,
                                    total_bytes=total_bytes,
                                    policy=policy,
                                )
                                written = destination_handle.write(chunk)
                                if written != len(chunk):
                                    raise ExtractionError(
                                        "Short write while extracting archive member.",
                                        context={
                                            "archive_member": entry.source_name,
                                            "requested_bytes": len(chunk),
                                            "written_bytes": written,
                                        },
                                    )
                                digest.update(chunk)
                            destination_handle.flush()
                            os.fsync(destination_handle.fileno())
                except FileExistsError as exc:
                    raise ExtractionCollisionError(
                        f"Refusing to overwrite staged extraction file: {destination}"
                    ) from exc

                if member_bytes != entry.uncompressed_bytes:
                    raise ExtractionError(
                        "Extracted byte count does not match central-directory metadata.",
                        context={
                            "archive_member": entry.source_name,
                            "actual_bytes": member_bytes,
                            "declared_bytes": entry.uncompressed_bytes,
                        },
                    )
                extracted_files.append(
                    ExtractedFile(
                        path=entry.normalized_path,
                        size_bytes=member_bytes,
                        sha256=digest.hexdigest(),
                        archive_ordinal=entry.archive_ordinal,
                    )
                )
    except CorpusImportError as exc:
        exc.context.setdefault("actual_bytes_written", total_bytes)
        exc.context.setdefault("extracted_file_count", len(extracted_files))
        exc.context.setdefault("extracted_directory_count", len(directories))
        raise
    except (
        OSError,
        EOFError,
        RuntimeError,
        NotImplementedError,
        zipfile.BadZipFile,
        zipfile.LargeZipFile,
    ) as exc:
        raise ExtractionError(
            f"Unable to safely extract preserved ZIP: {exc}",
            context={
                "actual_bytes_written": total_bytes,
                "extracted_directory_count": len(directories),
                "extracted_file_count": len(extracted_files),
            },
        ) from exc

    return ExtractionResult(
        files=tuple(sorted(extracted_files, key=lambda item: item.path)),
        directories=tuple(sorted(directories)),
        actual_bytes_written=total_bytes,
    )


def _linux_rename_no_replace(source: Path, destination: Path) -> None:
    at_fdcwd = -100
    rename_noreplace = 1
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise PromotionError("This platform does not provide atomic no-replace directory promotion.")
    renameat2.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameat2.restype = ctypes.c_int
    result = renameat2(
        at_fdcwd,
        os.fsencode(source),
        at_fdcwd,
        os.fsencode(destination),
        rename_noreplace,
    )
    if result != 0:
        error_number = ctypes.get_errno()
        if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
            raise ExtractionCollisionError(
                f"Refusing to replace existing promotion target: {destination}"
            )
        raise PromotionError(
            f"Unable to promote staged directory '{source}' to '{destination}': "
            f"{os.strerror(error_number)}"
        )


def promote_directory_no_replace(source: Path, destination: Path) -> None:
    """Promote a same-volume staged directory without replacing any target."""

    source = Path(source)
    destination = Path(destination)
    if destination.exists():
        raise ExtractionCollisionError(
            f"Refusing to replace existing promotion target: {destination}"
        )
    if not source.is_dir():
        raise PromotionError(f"Staged promotion source is not a directory: {source}")
    try:
        if source.parent.stat().st_dev != destination.parent.stat().st_dev:
            raise PromotionError("Staging and final output directories are not on the same volume.")
        if os.name == "nt":
            os.rename(source, destination)
        elif sys.platform.startswith("linux"):
            _linux_rename_no_replace(source, destination)
        else:
            raise PromotionError(
                "Atomic no-replace directory promotion is unsupported on this platform."
            )
    except CorpusImportError:
        raise
    except FileExistsError as exc:
        raise ExtractionCollisionError(
            f"Refusing to replace existing promotion target: {destination}"
        ) from exc
    except OSError as exc:
        raise PromotionError(
            f"Unable to promote staged directory '{source}' to '{destination}': {exc}"
        ) from exc


def is_regular_file(path: Path) -> bool:
    """Return true only for a regular file without following a final symlink."""

    try:
        return stat.S_ISREG(Path(path).lstat().st_mode)
    except OSError:
        return False
