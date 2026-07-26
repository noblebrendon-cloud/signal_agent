from __future__ import annotations


class CorpusImportError(Exception):
    """Base class for expected, operator-visible importer failures."""

    reason_code = "corpus_import_error"
    stage = "unknown"

    def __init__(self, message: str, *, context: dict | None = None) -> None:
        super().__init__(message)
        self.context = dict(context or {})


class SourceNotFoundError(CorpusImportError):
    reason_code = "source_not_found"
    stage = "validation"


class SourceTypeError(CorpusImportError):
    reason_code = "source_not_file"
    stage = "validation"


class UnreadableArchiveError(CorpusImportError):
    reason_code = "unreadable_archive"
    stage = "validation"


class MissingConversationDataError(CorpusImportError):
    reason_code = "missing_conversation_data"
    stage = "validation"


class RunCollisionError(CorpusImportError):
    reason_code = "run_collision"
    stage = "preservation_preflight"


class ProtectedFixtureError(CorpusImportError):
    reason_code = "protected_fixture_path"
    stage = "preservation_preflight"


class SourceChangedError(CorpusImportError):
    reason_code = "source_changed_during_operation"
    stage = "preservation"


class HashMismatchError(CorpusImportError):
    reason_code = "hash_mismatch"
    stage = "preservation"


class PreservationError(CorpusImportError):
    reason_code = "preservation_failed"
    stage = "preservation"


class ReceiptWriteError(CorpusImportError):
    reason_code = "receipt_write_failed"
    stage = "receipt"
