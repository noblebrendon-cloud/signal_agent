from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from signal_agent.corpus_import.errors import (
    MissingConversationDataError,
    SourceNotFoundError,
    SourceTypeError,
    UnreadableArchiveError,
)
from signal_agent.corpus_import.zip_validation import validate_chatgpt_export_zip


def test_valid_archive_counts_entries_and_conversation_files(valid_export_zip: Path) -> None:
    result = validate_chatgpt_export_zip(valid_export_zip)

    assert result.archive_entries == 2
    assert result.conversation_json_files == 1
    assert result.conversation_members == ("conversations.json",)


def test_nested_and_sharded_conversation_names_are_detected(tmp_path: Path) -> None:
    source = tmp_path / "export.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("nested/Conversations-000.json", "[]")
        archive.writestr("nested/conversations-001.JSON", "[]")

    result = validate_chatgpt_export_zip(source)

    assert result.conversation_json_files == 2


def test_missing_source_raises_typed_error(tmp_path: Path) -> None:
    with pytest.raises(SourceNotFoundError):
        validate_chatgpt_export_zip(tmp_path / "missing.zip")


def test_directory_source_raises_typed_error(tmp_path: Path) -> None:
    with pytest.raises(SourceTypeError):
        validate_chatgpt_export_zip(tmp_path)


def test_corrupt_archive_raises_typed_error(tmp_path: Path) -> None:
    source = tmp_path / "bad.zip"
    source.write_bytes(b"not-a-zip")

    with pytest.raises(UnreadableArchiveError):
        validate_chatgpt_export_zip(source)


def test_archive_without_conversations_raises_typed_error(tmp_path: Path) -> None:
    source = tmp_path / "export.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("user.json", "{}")

    with pytest.raises(MissingConversationDataError):
        validate_chatgpt_export_zip(source)
