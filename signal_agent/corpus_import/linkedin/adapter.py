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
    LinkedInImportError,
    LinkedInImportPlan,
    build_linkedin_import_plan,
    preserve_linkedin_source,
)
from .key_verifier import KeyContext, ensure_key_verifier, load_key_context


@dataclass(frozen=True)
class LinkedInPreparedEvidence:
    """Opaque, per-run LinkedIn preparation state owned by the adapter."""

    import_plan: LinkedInImportPlan = field(repr=False)
    key_context: KeyContext = field(repr=False)
    repository_root: Path
    created_at: str


@dataclass(frozen=True)
class LinkedInEvidenceAdapter:
    """First EvidenceSource and RelationshipNormalizer implementation."""

    hmac_key_file: Path
    hmac_key_id: str
    source_type: str = SOURCE_TYPE

    def prepare(
        self,
        source: str | Path,
        *,
        repository_root: Path,
        clock: Clock,
    ) -> LinkedInPreparedEvidence:
        repository = Path(repository_root).expanduser().resolve(strict=True)
        created_at = clock()
        key_context = load_key_context(
            self.hmac_key_file,
            self.hmac_key_id,
            repo_root=repository,
        )
        import_plan = build_linkedin_import_plan(
            source,
            key_context=key_context,
            clock=lambda: created_at,
        )
        return LinkedInPreparedEvidence(
            import_plan=import_plan,
            key_context=key_context,
            repository_root=repository,
            created_at=created_at,
        )

    def validate(
        self,
        prepared: LinkedInPreparedEvidence,
        *,
        repository_root: Path,
        clock: Clock,
    ) -> None:
        del clock
        repository = Path(repository_root).expanduser().resolve(strict=True)
        if repository != prepared.repository_root:
            raise LinkedInImportError("linkedin_prepared_repository_mismatch")
        ensure_key_verifier(
            prepared.key_context,
            repo_root=repository,
            clock=lambda: prepared.created_at,
        )

    def preserve(
        self,
        prepared: LinkedInPreparedEvidence,
        run_root: Path,
    ) -> PreservedEvidence:
        output_root = prepare_run_root(Path(run_root))
        preserve_linkedin_source(prepared.import_plan, output_root)
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
                ("source_size_bytes", prepared.import_plan.source_size_bytes),
                ("source_type", SOURCE_TYPE),
            ),
        )

    def normalize(
        self,
        prepared: LinkedInPreparedEvidence,
        preserved: PreservedEvidence,
    ) -> NormalizedRelationshipBatch:
        plan = prepared.import_plan
        if preserved.source_sha256 != plan.source_sha256:
            raise LinkedInImportError("linkedin_preserved_source_identity_mismatch")
        if preserved.source_receipt.receipt_id != plan.source_receipt["receipt_id"]:
            raise LinkedInImportError("linkedin_preserved_receipt_identity_mismatch")
        return NormalizedRelationshipBatch(
            preserved=preserved,
            records=plan.records,
            unresolved_matches=plan.unresolved_matches,
        )
