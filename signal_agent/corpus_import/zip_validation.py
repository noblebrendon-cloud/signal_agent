from __future__ import annotations

import fnmatch
import zipfile
from pathlib import Path, PurePosixPath

from .errors import (
    MissingConversationDataError,
    SourceNotFoundError,
    SourceTypeError,
    UnreadableArchiveError,
)
from .models import ZipValidationResult


def _is_conversation_member(member_name: str) -> bool:
    normalized = member_name.replace("\\", "/")
    basename = PurePosixPath(normalized).name.lower()
    return fnmatch.fnmatchcase(basename, "conversations*.json")


def validate_chatgpt_export_zip(source: Path) -> ZipValidationResult:
    """Validate a ChatGPT export archive without extracting any member."""

    source = Path(source)
    if not source.exists():
        raise SourceNotFoundError(f"Source ZIP does not exist: {source}")
    if not source.is_file():
        raise SourceTypeError(f"Source path is not a file: {source}")

    try:
        with zipfile.ZipFile(source, mode="r") as archive:
            entries = archive.infolist()
            first_bad_member = archive.testzip()
            if first_bad_member is not None:
                raise UnreadableArchiveError(
                    f"Archive CRC validation failed for member: {first_bad_member}",
                    context={"bad_member": first_bad_member},
                )
            conversation_members = tuple(
                sorted(info.filename for info in entries if _is_conversation_member(info.filename))
            )
    except UnreadableArchiveError:
        raise
    except (OSError, RuntimeError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise UnreadableArchiveError(f"Unable to read source ZIP '{source}': {exc}") from exc

    if not conversation_members:
        raise MissingConversationDataError(
            "Archive contains no conversations*.json file.",
            context={"archive_entries": len(entries)},
        )

    return ZipValidationResult(
        archive_entries=len(entries),
        conversation_json_files=len(conversation_members),
        conversation_members=conversation_members,
    )
