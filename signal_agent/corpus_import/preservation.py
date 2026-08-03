from __future__ import annotations

import os
from pathlib import Path

from .errors import (
    HashMismatchError,
    PreservationError,
    ProtectedFixtureError,
    RunCollisionError,
    SourceChangedError,
)
from .hashing import sha256_file
from .models import PreservationResult


PRESERVED_FILENAME = "export.zip"
HASH_RECORD_FILENAME = "export.zip.sha256.txt"


def _resolved_for_comparison(path: Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def _looks_like_fixture_path(path: Path) -> bool:
    protected_parts = {"fixtures", "manual_calibration_v1"}
    return any(part.lower() in protected_parts for part in _resolved_for_comparison(path).parts)


def prepare_run_root(run_root: Path) -> Path:
    """Create or accept an empty run root; refuse fixtures and any existing content."""

    run_root = _resolved_for_comparison(Path(run_root))
    if _looks_like_fixture_path(run_root):
        raise ProtectedFixtureError(f"Run root is inside a protected fixture path: {run_root}")

    if run_root.exists():
        if not run_root.is_dir():
            raise RunCollisionError(f"Run root exists and is not a directory: {run_root}")
        if any(run_root.iterdir()):
            raise RunCollisionError(f"Run root already exists and is nonempty: {run_root}")
    else:
        run_root.mkdir(parents=True, exist_ok=False)

    return run_root


def _write_text_exclusive(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise RunCollisionError(f"Refusing to overwrite existing file: {path}") from exc


def preserve_source_zip(
    source: Path,
    run_root: Path,
    *,
    expected_sha256: str,
    expected_stat: os.stat_result,
    chunk_size: int = 1024 * 1024,
) -> PreservationResult:
    """Copy the source into 00_original with exclusive creation and hash verification."""

    return preserve_source_file(
        source,
        run_root,
        expected_sha256=expected_sha256,
        expected_stat=expected_stat,
        preserved_filename=PRESERVED_FILENAME,
        hash_record_filename=HASH_RECORD_FILENAME,
        chunk_size=chunk_size,
    )


def preserve_source_file(
    source: Path,
    run_root: Path,
    *,
    expected_sha256: str,
    expected_stat: os.stat_result,
    preserved_filename: str,
    hash_record_filename: str,
    chunk_size: int = 1024 * 1024,
) -> PreservationResult:
    """Copy one source file into ``00_original`` without replacing any path."""

    source = _resolved_for_comparison(Path(source))
    run_root = _resolved_for_comparison(Path(run_root))
    original_dir = run_root / "00_original"
    if Path(preserved_filename).name != preserved_filename or not preserved_filename:
        raise PreservationError("Preserved filename must be one safe path component.")
    if Path(hash_record_filename).name != hash_record_filename or not hash_record_filename:
        raise PreservationError("Hash-record filename must be one safe path component.")
    preserved_path = original_dir / preserved_filename
    hash_record_path = original_dir / hash_record_filename

    if source == preserved_path:
        raise PreservationError("Source and preserved destination resolve to the same path.")
    if preserved_path.exists() or hash_record_path.exists():
        raise RunCollisionError(f"Preservation target already exists under: {original_dir}")

    original_dir.mkdir(parents=True, exist_ok=True)
    created_preserved = False
    try:
        with source.open("rb") as source_handle:
            with preserved_path.open("xb") as destination_handle:
                created_preserved = True
                for chunk in iter(lambda: source_handle.read(chunk_size), b""):
                    destination_handle.write(chunk)
                destination_handle.flush()
                os.fsync(destination_handle.fileno())
    except FileExistsError as exc:
        raise RunCollisionError(f"Refusing to overwrite preserved source: {preserved_path}") from exc
    except OSError as exc:
        if created_preserved:
            preserved_path.unlink(missing_ok=True)
        raise PreservationError(f"Unable to preserve source ZIP: {exc}") from exc

    try:
        observed_stat = source.stat()
        if (
            observed_stat.st_size != expected_stat.st_size
            or observed_stat.st_mtime_ns != expected_stat.st_mtime_ns
        ):
            preserved_path.unlink(missing_ok=True)
            raise SourceChangedError(
                "Source ZIP changed while validation and preservation were running.",
                context={
                    "expected_size_bytes": expected_stat.st_size,
                    "observed_size_bytes": observed_stat.st_size,
                    "expected_mtime_ns": expected_stat.st_mtime_ns,
                    "observed_mtime_ns": observed_stat.st_mtime_ns,
                },
            )

        preserved_sha256 = sha256_file(preserved_path)
        if preserved_sha256 != expected_sha256:
            preserved_path.unlink(missing_ok=True)
            raise HashMismatchError(
                "Preserved ZIP hash does not match source identity.",
                context={
                    "expected_sha256": expected_sha256,
                    "preserved_sha256": preserved_sha256,
                },
            )

        _write_text_exclusive(
            hash_record_path,
            f"{preserved_sha256}  {preserved_filename}\n",
        )
    except Exception:
        if not hash_record_path.exists():
            preserved_path.unlink(missing_ok=True)
        raise

    return PreservationResult(
        preserved_path=preserved_path,
        hash_record_path=hash_record_path,
        preserved_sha256=preserved_sha256,
        size_bytes=preserved_path.stat().st_size,
    )
