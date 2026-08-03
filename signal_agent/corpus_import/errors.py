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


class ParentReceiptError(CorpusImportError):
    reason_code = "invalid_parent_receipt"
    stage = "lineage_validation"


class ExtractionCollisionError(CorpusImportError):
    reason_code = "extraction_path_collision"
    stage = "extraction_preflight"


class UnsafeArchivePathError(CorpusImportError):
    reason_code = "unsafe_archive_path"
    stage = "archive_preflight"


class ArchiveMemberCollisionError(CorpusImportError):
    reason_code = "archive_member_collision"
    stage = "archive_preflight"


class UnsupportedArchiveMemberError(CorpusImportError):
    reason_code = "unsupported_archive_member"
    stage = "archive_preflight"


class ArchivePolicyError(CorpusImportError):
    reason_code = "archive_policy_violation"
    stage = "archive_preflight"


class ExtractionPolicyError(ArchivePolicyError):
    stage = "extraction"


class InsufficientDiskSpaceError(CorpusImportError):
    reason_code = "insufficient_disk_space"
    stage = "disk_preflight"


class ExtractionError(CorpusImportError):
    reason_code = "extraction_failed"
    stage = "extraction"


class ExtractionSourceChangedError(CorpusImportError):
    reason_code = "source_changed_during_extraction"
    stage = "source_revalidation"


class InventoryError(CorpusImportError):
    reason_code = "inventory_failed"
    stage = "inventory"


class PromotionError(CorpusImportError):
    reason_code = "promotion_failed"
    stage = "promotion"
