from __future__ import annotations

from pathlib import Path
from typing import Sequence

from .artifacts import (
    SESSION_SCHEMA,
    canonical_observations,
    persist_attempt,
    persist_boundary,
    persist_bounded_material,
    persist_capture,
    persist_failure,
    persist_intent,
    persist_observation_index,
    persist_session,
    verify_assembly_evidence,
)
from .canonical import derive_id, require_offset_timestamp, require_text, sha256_canonical
from .checkpoints import (
    commit_checkpoint,
    create_completed_manifest_verifier_authority,
    create_checkpoint_candidate,
    resolve_current_checkpoint,
    verify_completed_run,
)
from .contracts import FailureInjector, GovernedProcessor
from .errors import AcquisitionStateError, OperationalIngestionError, OperationalValidationError
from .models import (
    AcquisitionIntent,
    CapturedPage,
    Clock,
    IngestionResult,
    PersistedArtifact,
    RequestAttempt,
    thaw_json,
)


class OperationalIngestionKernel:
    """Source-neutral coordinator for already observed, nonnetwork capture inputs."""

    def __init__(
        self,
        store_root: str | Path,
        *,
        clock: Clock,
        failure_injector: FailureInjector | None = None,
    ) -> None:
        self.store_root = Path(store_root).resolve(strict=False)
        self.clock = clock
        self.failure_injector = failure_injector

    def _inject(self, stage: str) -> None:
        if self.failure_injector is not None:
            self.failure_injector(stage)

    def _source_root(self, intent: AcquisitionIntent) -> Path:
        storage_id = derive_id(
            "osi",
            intent.source.source_type,
            intent.source.source_instance_id,
        )
        return self.store_root / storage_id

    @staticmethod
    def _validate_pages(
        attempts: Sequence[RequestAttempt],
        pages: Sequence[CapturedPage],
    ) -> None:
        if not pages:
            raise OperationalValidationError("captured_pages_required")
        ordered_pages = sorted(pages, key=lambda item: item.page_ordinal)
        if [item.page_ordinal for item in ordered_pages] != list(range(1, len(pages) + 1)):
            raise OperationalValidationError("captured_page_sequence_invalid")
        if not ordered_pages[-1].terminal:
            raise OperationalValidationError("terminal_capture_required")
        if any(item.terminal for item in ordered_pages[:-1]):
            raise OperationalValidationError("terminal_capture_must_be_final")
        successful = {
            (item.page_ordinal, item.attempt_ordinal): item
            for item in attempts
            if item.outcome == "success"
        }
        for page in ordered_pages:
            attempt = successful.get((page.page_ordinal, page.successful_attempt_ordinal))
            if attempt is None:
                raise OperationalValidationError("capture_success_attempt_missing")
            if attempt.request_fingerprint != page.request_fingerprint:
                raise OperationalValidationError("capture_success_request_mismatch")
        continuations: set[str] = set()
        for page in ordered_pages[:-1]:
            next_hash = sha256_canonical(dict(page.next_continuation))
            if next_hash in continuations:
                raise OperationalValidationError("pagination_continuation_cycle")
            continuations.add(next_hash)

    def _verify_prior(self, source_root: Path, intent: AcquisitionIntent) -> None:
        current = resolve_current_checkpoint(source_root) if source_root.exists() else None
        if current is None:
            if intent.prior_checkpoint_id is not None:
                raise AcquisitionStateError("prior_checkpoint_not_current")
            return
        if intent.prior_checkpoint_id != current.payload["checkpoint_id"]:
            raise AcquisitionStateError("prior_checkpoint_not_current")
        if intent.prior_checkpoint_hash != current.payload["artifact_hash"]:
            raise AcquisitionStateError("prior_checkpoint_hash_not_current")

    def run_from_captured_pages(
        self,
        *,
        intent: AcquisitionIntent,
        session_started_at: str,
        transport_kind: str,
        mode: str,
        attempts: Sequence[RequestAttempt],
        pages: Sequence[CapturedPage],
        processor: GovernedProcessor,
        governed_run_root: str | Path,
    ) -> IngestionResult:
        require_offset_timestamp(session_started_at, "session_started_at")
        require_text(transport_kind, "transport_kind")
        if mode not in {"fixture", "simulation", "live_readonly"}:
            raise OperationalValidationError("operational_mode_unsupported")
        self._validate_pages(attempts, pages)
        source_root = self._source_root(intent)
        source_root.mkdir(parents=True, exist_ok=True)
        self._verify_prior(source_root, intent)
        session_id = derive_id(
            "oas",
            SESSION_SCHEMA,
            intent.cycle_id,
            session_started_at,
            transport_kind,
            mode,
        )
        session_root = source_root / f"sessions/{session_id}"
        valid: list[PersistedArtifact] = []
        failed_stage = "session_open"
        session_artifact: PersistedArtifact | None = None
        try:
            intent_artifact = persist_intent(session_root, intent)
            valid.append(intent_artifact)
            session_artifact = persist_session(
                session_root,
                intent_payload=thaw_json(intent_artifact.payload),
                started_at=session_started_at,
                transport_kind=transport_kind,
                mode=mode,
            )
            valid.append(session_artifact)
            actual_session_id = str(session_artifact.payload["session_id"])
            if actual_session_id != session_id:
                raise OperationalValidationError("session_identity_derivation_mismatch")
            self._inject("after_session")

            failed_stage = "request_attempt_persistence"
            attempt_artifacts: dict[tuple[int, int], PersistedArtifact] = {}
            for attempt in sorted(attempts, key=lambda item: (item.page_ordinal, item.attempt_ordinal)):
                persisted = persist_attempt(
                    session_root,
                    session_id=session_id,
                    attempt=attempt,
                )
                attempt_artifacts[(attempt.page_ordinal, attempt.attempt_ordinal)] = persisted
                valid.append(persisted)
            self._inject("after_attempts")

            failed_stage = "page_capture_persistence"
            capture_artifacts: list[PersistedArtifact] = []
            ordered_pages = sorted(pages, key=lambda item: item.page_ordinal)
            for page in ordered_pages:
                capture = persist_capture(
                    session_root,
                    session_id=session_id,
                    page=page,
                    successful_attempt=attempt_artifacts[
                        (page.page_ordinal, page.successful_attempt_ordinal)
                    ],
                    previous_capture=(capture_artifacts[-1] if capture_artifacts else None),
                )
                capture_artifacts.append(capture)
                valid.append(capture)
            self._inject("after_captures")

            failed_stage = "bounded_material_persistence"
            observations = canonical_observations(ordered_pages)
            bounded = persist_bounded_material(
                session_root,
                intent_payload=thaw_json(intent_artifact.payload),
                observations=observations,
            )
            valid.append(bounded)
            self._inject("after_bounded_material")

            failed_stage = "acquisition_boundary_persistence"
            boundary = persist_boundary(
                source_root,
                session_root,
                intent_payload=thaw_json(intent_artifact.payload),
                session_payload=thaw_json(session_artifact.payload),
                captures=capture_artifacts,
                bounded_material=bounded,
                created_at=self.clock(),
            )
            valid.append(boundary)
            self._inject("after_boundary")

            failed_stage = "governed_processing"
            completed = processor.process(
                bounded_material_path=bounded.path,
                governed_run_root=Path(governed_run_root),
                clock=self.clock,
            )
            self._inject("after_processor")

            failed_stage = "completed_manifest_verification"
            assembly = verify_assembly_evidence(
                source_root,
                boundary=boundary,
                bounded_material=bounded,
            )
            verify_completed_run(
                completed,
                bounded,
                expected_source_sha256=assembly["bounded_material_file_sha256"],
            )
            self._inject("after_manifest_verification")

            failed_stage = "observation_index_persistence"
            current = resolve_current_checkpoint(source_root)
            prior_index = (
                None
                if current is None
                else dict(current.payload["observation_index"])
            )
            index = persist_observation_index(
                source_root,
                source=thaw_json(intent_artifact.payload["source"]),
                bounded_material=bounded,
                boundary=boundary,
                prior_index_ref=prior_index,
            )
            valid.append(index)
            self._inject("after_observation_index")

            failed_stage = "checkpoint_candidate_persistence"
            candidate = create_checkpoint_candidate(
                source_root,
                intent=intent_artifact,
                boundary=boundary,
                bounded_material=bounded,
                observation_index=index,
                completed=completed,
            )
            valid.append(candidate)
            self._inject("after_checkpoint_candidate")

            failed_stage = "completion_authority_persistence"
            authority = create_completed_manifest_verifier_authority(
                source_root,
                candidate=candidate,
                intent=intent_artifact,
                boundary=boundary,
                bounded_material=bounded,
                observation_index=index,
                completed=completed,
            )
            valid.append(authority)
            self._inject("after_completion_authority")

            failed_stage = "checkpoint_commit_persistence"
            self._inject("before_checkpoint_commit")
            commit = commit_checkpoint(
                source_root,
                candidate=candidate,
                authority=authority,
                completed=completed,
                committed_at=self.clock(),
            )
            return IngestionResult(
                source_root=source_root,
                session_root=session_root,
                intent=intent_artifact,
                session=session_artifact,
                boundary=boundary,
                bounded_material=bounded,
                observation_index=index,
                checkpoint_candidate=candidate,
                completion_authority=authority,
                checkpoint_commit=commit,
                completed_run=completed,
            )
        except Exception as exc:
            if session_artifact is not None:
                error_code = (
                    exc.__class__.__name__
                    if not isinstance(exc, OperationalIngestionError)
                    else exc.__class__.__name__
                )
                persist_failure(
                    session_root,
                    session_id=str(session_artifact.payload["session_id"]),
                    failed_stage=failed_stage,
                    failed_at=self.clock(),
                    error_class=exc.__class__.__name__,
                    error_code=error_code,
                    last_valid_artifacts=valid,
                )
            raise
