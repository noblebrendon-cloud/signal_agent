from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from signal_agent.corpus_import.preservation import prepare_run_root
from signal_agent.corpus_import.receipts import write_receipt_exclusive
from signal_agent.evidence_sources.contracts import Clock
from signal_agent.evidence_sources.models import (
    NormalizedRelationshipBatch,
    PreservedEvidence,
    SourceReceiptDescriptor,
)

from .importer import (
    PRESERVED_RELATIVE_PATH,
    SOURCE_RECEIPT_RELATIVE_PATH,
    SOURCE_TYPE,
    InteractionEventImportError,
    InteractionEventImportPlan,
    build_interaction_event_import_plan,
    preserve_interaction_event_source,
)
from .key import (
    InteractionEventKeyContext,
    load_interaction_event_key,
    validate_interaction_event_key,
)


@dataclass(frozen=True)
class InteractionEventPreparedEvidence:
    import_plan: InteractionEventImportPlan = field(repr=False)
    key_context: InteractionEventKeyContext = field(repr=False)
    repository_root: Path
    created_at: str


@dataclass(frozen=True)
class InteractionEventEvidenceAdapter:
    hmac_key_file: Path
    hmac_key_id: str
    source_type: str = SOURCE_TYPE

    def prepare(
        self,
        source: str | Path,
        *,
        repository_root: Path,
        clock: Clock,
    ) -> InteractionEventPreparedEvidence:
        repository = Path(repository_root).expanduser().resolve(strict=True)
        created_at = clock()
        key_context = load_interaction_event_key(
            self.hmac_key_file,
            self.hmac_key_id,
            repository_root=repository,
        )
        import_plan = build_interaction_event_import_plan(
            source,
            key_context=key_context,
            clock=lambda: created_at,
        )
        return InteractionEventPreparedEvidence(
            import_plan=import_plan,
            key_context=key_context,
            repository_root=repository,
            created_at=created_at,
        )

    def validate(
        self,
        prepared: InteractionEventPreparedEvidence,
        *,
        repository_root: Path,
        clock: Clock,
    ) -> None:
        del clock
        repository = Path(repository_root).expanduser().resolve(strict=True)
        if repository != prepared.repository_root:
            raise InteractionEventImportError(
                "interaction_event_prepared_repository_mismatch"
            )
        validate_interaction_event_key(
            prepared.key_context,
            repository_root=repository,
        )
        try:
            observed_stat = prepared.import_plan.source_path.stat()
        except OSError as exc:
            raise InteractionEventImportError("interaction_event_source_unreadable") from exc
        expected_stat = prepared.import_plan.source_stat
        if (
            observed_stat.st_size != expected_stat.st_size
            or observed_stat.st_mtime_ns != expected_stat.st_mtime_ns
        ):
            raise InteractionEventImportError("interaction_event_source_changed")

    def preserve(
        self,
        prepared: InteractionEventPreparedEvidence,
        run_root: Path,
    ) -> PreservedEvidence:
        output_root = prepare_run_root(Path(run_root))
        preserve_interaction_event_source(prepared.import_plan, output_root)
        write_receipt_exclusive(
            output_root / SOURCE_RECEIPT_RELATIVE_PATH,
            prepared.import_plan.source_receipt,
        )
        descriptor = SourceReceiptDescriptor(
            receipt_id=prepared.import_plan.source_receipt["receipt_id"],
            receipt_hash=prepared.import_plan.source_receipt["receipt_hash"],
            source_sha256=prepared.import_plan.source_sha256,
            persisted_relative_path=SOURCE_RECEIPT_RELATIVE_PATH,
            schema_version=prepared.import_plan.source_receipt["schema_version"],
            protection_metadata=(
                ("algorithm", prepared.key_context.algorithm),
                ("key_id", prepared.key_context.key_id),
                ("version", prepared.key_context.token_version),
            ),
        )
        return PreservedEvidence(
            source_sha256=prepared.import_plan.source_sha256,
            preserved_relative_path=PRESERVED_RELATIVE_PATH,
            source_receipt=descriptor,
            provenance_metadata=(
                ("blank_line_count", prepared.import_plan.blank_line_count),
                ("record_count", len(prepared.import_plan.records)),
                ("source_size_bytes", prepared.import_plan.source_size_bytes),
                ("source_type", SOURCE_TYPE),
                ("timestamp_max_utc", prepared.import_plan.timestamp_max_utc),
                ("timestamp_min_utc", prepared.import_plan.timestamp_min_utc),
            ),
        )

    def normalize(
        self,
        prepared: InteractionEventPreparedEvidence,
        preserved: PreservedEvidence,
    ) -> NormalizedRelationshipBatch:
        plan = prepared.import_plan
        if preserved.source_sha256 != plan.source_sha256:
            raise InteractionEventImportError(
                "interaction_event_preserved_source_identity_mismatch"
            )
        if preserved.source_receipt.receipt_id != plan.source_receipt["receipt_id"]:
            raise InteractionEventImportError(
                "interaction_event_preserved_receipt_identity_mismatch"
            )
        return NormalizedRelationshipBatch(
            preserved=preserved,
            records=plan.records,
            unresolved_matches=plan.unresolved_matches,
        )
