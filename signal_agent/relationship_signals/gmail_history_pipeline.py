from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from signal_agent.corpus_import.gmail_history import (
    GmailHistoryCoverageError,
    GmailHistoryEvidenceAdapter,
    GmailHistoryExpiredError,
    GmailHistoryOfflineResult,
    build_gmail_captured_inputs,
    build_gmail_intent,
    load_gmail_fixture,
    load_gmail_history_policy,
)
from signal_agent.corpus_import.gmail_history.adapter import (
    PRESERVED_RELATIVE_PATH,
    PROJECTION_RELATIVE_PATH,
    SOURCE_RECEIPT_RELATIVE_PATH,
)
from signal_agent.corpus_import.gmail_history.canonicalization import (
    build_expired_attempt,
)
from signal_agent.operational_ingestion.artifacts import (
    SESSION_SCHEMA,
    load_artifact,
    persist_attempt,
    persist_failure,
    persist_intent,
    persist_session,
)
from signal_agent.operational_ingestion.canonical import (
    canonical_json_bytes,
    derive_id,
    seal,
    sha256_bytes,
)
from signal_agent.operational_ingestion.checkpoints import resolve_current_checkpoint
from signal_agent.operational_ingestion.errors import AcquisitionStateError
from signal_agent.operational_ingestion.kernel import OperationalIngestionKernel
from signal_agent.operational_ingestion.models import (
    CompletedRunReference,
    PersistedArtifact,
    thaw_json,
)

from .analysis import GovernedSystemsRelationshipAnalyzer
from .content_library import TeachingAtomContextResolver
from .manifest import DetachedRunManifestBuilder
from .packets import GovernedRelationshipPacketBuilder
from .relationship_pipeline import run_relationship_signal_pipeline


GMAIL_COMPLETED_MANIFEST_SCHEMA = (
    "signal_agent.gmail_history_operational_completed_manifest.v1"
)
GMAIL_COMPLETED_MANIFEST_PATH = "05_receipts/gmail_operational_completed_manifest.json"


@dataclass(frozen=True)
class GmailHistoryRelationshipResult:
    success: bool
    script_id: str
    result: GmailHistoryOfflineResult


def _write_exact(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if not path.is_file() or path.read_bytes() != payload:
            raise RuntimeError(f"gmail_governed_artifact_conflict:{path.name}")
        return
    try:
        with path.open("xb") as handle:
            if handle.write(payload) != len(payload):
                raise OSError("gmail_governed_short_write")
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        if not path.is_file() or path.read_bytes() != payload:
            raise RuntimeError(f"gmail_governed_artifact_conflict:{path.name}")


class _FailureAwareGmailAdapter:
    def __init__(
        self,
        adapter: GmailHistoryEvidenceAdapter,
        failure_stage: str | None,
    ) -> None:
        self.delegate = adapter
        self.failure_stage = failure_stage
        self.source_type = adapter.source_type

    def prepare(self, source, *, repository_root, clock):
        return self.delegate.prepare(source, repository_root=repository_root, clock=clock)

    def validate(self, prepared, *, repository_root, clock) -> None:
        self.delegate.validate(prepared, repository_root=repository_root, clock=clock)

    def preserve(self, prepared, run_root):
        if self.failure_stage == "preservation_failure":
            raise RuntimeError("gmail_preservation_failure")
        preserved = self.delegate.preserve(prepared, run_root)
        if self.failure_stage == "after_preservation_failure":
            raise RuntimeError("gmail_after_preservation_failure")
        return preserved

    def normalize(self, prepared, preserved):
        if self.failure_stage == "normalization_failure":
            raise RuntimeError("gmail_normalization_failure")
        return self.delegate.normalize(prepared, preserved)


class _FailureAwareAnalyzer:
    def __init__(self, delegate, failure_stage: str | None) -> None:
        self.delegate = delegate
        self.failure_stage = failure_stage

    def analyze(self, records):
        if self.failure_stage == "downstream_processing_failure":
            raise RuntimeError("gmail_downstream_processing_failure")
        return self.delegate.analyze(records)


class _FailureAwareManifestBuilder:
    def __init__(
        self,
        delegate: DetachedRunManifestBuilder,
        relationship_root: Path,
        failure_stage: str | None,
    ) -> None:
        self.delegate = delegate
        self.relationship_root = relationship_root
        self.failure_stage = failure_stage

    def build(self, **kwargs):
        manifest = self.delegate.build(**kwargs)
        if self.failure_stage == "generic_manifest_promotion_failure":
            destination = self.relationship_root / "05_receipts/run_manifest.json"
            destination.mkdir(parents=True, exist_ok=False)
        return manifest


class GmailHistoryGovernedProcessor:
    """Connect finite Gmail fixture evidence to the unchanged relationship runner."""

    def __init__(
        self,
        *,
        policy,
        prior_projection_path: str | Path | None,
        repository_root: str | Path,
        taxonomy_path: str | Path,
        content_library_root: str | Path,
        failure_stage: str | None = None,
    ) -> None:
        self.policy = policy
        self.prior_projection_path = (
            None
            if prior_projection_path is None
            else Path(prior_projection_path).resolve(strict=True)
        )
        self.repository_root = Path(repository_root).resolve(strict=True)
        self.taxonomy_path = Path(taxonomy_path).resolve(strict=True)
        self.content_library_root = Path(content_library_root).resolve(strict=True)
        self.failure_stage = failure_stage

    def process(
        self,
        *,
        bounded_material_path: Path,
        governed_run_root: Path,
        clock: Callable[[], str],
    ) -> CompletedRunReference:
        governed_root = Path(governed_run_root).resolve(strict=False)
        adapter = _FailureAwareGmailAdapter(
            GmailHistoryEvidenceAdapter(
                policy=self.policy,
                prior_projection_path=self.prior_projection_path,
            ),
            self.failure_stage,
        )
        result = run_relationship_signal_pipeline(
            source=bounded_material_path,
            run_root=governed_root,
            repository_root=self.repository_root,
            evidence_source=adapter,
            normalizer=adapter,
            analyzer=_FailureAwareAnalyzer(
                GovernedSystemsRelationshipAnalyzer(self.taxonomy_path),
                self.failure_stage,
            ),
            resolver=TeachingAtomContextResolver(self.content_library_root),
            packet_builder=GovernedRelationshipPacketBuilder(),
            manifest_builder=_FailureAwareManifestBuilder(
                DetachedRunManifestBuilder(),
                governed_root,
                self.failure_stage,
            ),
            clock=clock,
        )
        if self.failure_stage in {
            "after_downstream_output_before_completed_manifest",
            "operational_manifest_write_failure",
        }:
            raise RuntimeError("gmail_completed_manifest_not_promoted")
        bounded_bytes = bounded_material_path.read_bytes()
        bounded = json.loads(bounded_bytes.decode("utf-8"))
        input_ref = {
            "bounded_material_id": bounded["bounded_material_id"],
            "bounded_material_hash": bounded["artifact_hash"],
            "observation_set_hash": bounded["observation_set_hash"],
        }
        receipt_path = governed_root / SOURCE_RECEIPT_RELATIVE_PATH
        preserved_path = governed_root / PRESERVED_RELATIVE_PATH
        projection_path = governed_root / PROJECTION_RELATIVE_PATH
        relationship_manifest_path = governed_root / "05_receipts/run_manifest.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        projection = json.loads(projection_path.read_text(encoding="utf-8"))
        relationship_manifest = json.loads(
            relationship_manifest_path.read_text(encoding="utf-8")
        )
        artifacts: list[dict[str, str]] = []
        for path in sorted(governed_root.rglob("*")):
            if not path.is_file() or path in {receipt_path, preserved_path}:
                continue
            artifacts.append(
                {
                    "path": path.relative_to(governed_root).as_posix(),
                    "sha256": sha256_bytes(path.read_bytes()),
                }
            )
        if not artifacts:
            raise RuntimeError("gmail_governed_artifacts_required")
        created_at = clock()
        material = {
            "schema_version": GMAIL_COMPLETED_MANIFEST_SCHEMA,
            "run_id": derive_id(
                "ghgr",
                input_ref,
                relationship_manifest["run_id"],
                projection["projection_hash"],
            ),
            "created_at": created_at,
            "completion_state": "completed",
            "operational_input": input_ref,
            "gmail_projection": {
                "path": PROJECTION_RELATIVE_PATH,
                "projection_id": projection["projection_id"],
                "projection_hash": projection["projection_hash"],
                "target_label_projection_set_hash": projection[
                    "target_label_projection_set_hash"
                ],
                "projection_policy": projection["projection_policy"],
            },
            "preservation_receipt": {
                "path": SOURCE_RECEIPT_RELATIVE_PATH,
                "receipt_id": receipt["receipt_id"],
                "receipt_hash": receipt["receipt_hash"],
                "file_sha256": sha256_bytes(receipt_path.read_bytes()),
            },
            "preserved_source": {
                "path": PRESERVED_RELATIVE_PATH,
                "source_sha256": sha256_bytes(bounded_bytes),
                "byte_size": len(bounded_bytes),
                "file_sha256": sha256_bytes(preserved_path.read_bytes()),
            },
            "governed_relationship_manifest": {
                "path": relationship_manifest_path.relative_to(
                    governed_root
                ).as_posix(),
                "run_id": result.run_id,
                "manifest_hash": relationship_manifest["manifest_hash"],
                "file_sha256": sha256_bytes(relationship_manifest_path.read_bytes()),
            },
            "artifacts": artifacts,
            "safety_flags": {
                "authentication_authorized": False,
                "gmail_write_authorized": False,
                "live_mailbox_access_authorized": False,
                "network_authorized": False,
                "oauth_authorized": False,
                "source_records_mutated": False,
                "upstream_write_authorized": False,
            },
        }
        manifest_id = derive_id(
            "ghgm",
            GMAIL_COMPLETED_MANIFEST_SCHEMA,
            material,
        )
        manifest = seal({**material, "manifest_id": manifest_id}, "manifest_hash")
        if self.failure_stage == "manifest_verification_failure":
            corrupted = dict(manifest)
            descriptors = [dict(item) for item in corrupted["artifacts"]]
            descriptors[0]["sha256"] = "sha256:" + ("0" * 64)
            corrupted["artifacts"] = descriptors
            manifest = seal(
                {
                    key: value
                    for key, value in corrupted.items()
                    if key != "manifest_hash"
                },
                "manifest_hash",
            )
        manifest_path = governed_root / GMAIL_COMPLETED_MANIFEST_PATH
        _write_exact(manifest_path, canonical_json_bytes(manifest))
        return CompletedRunReference(
            run_id=manifest["run_id"],
            run_root=governed_root,
            run_root_ref=f"gmail-history-offline-governed-run:{manifest['run_id']}",
            manifest_relative_path=GMAIL_COMPLETED_MANIFEST_PATH,
            preservation_receipt_relative_path=SOURCE_RECEIPT_RELATIVE_PATH,
        )


def _source_root(store_root: Path, intent) -> Path:
    return store_root / derive_id(
        "osi",
        intent.source.source_type,
        intent.source.source_instance_id,
    )


def _latest_failure(source_root: Path) -> PersistedArtifact | None:
    paths = sorted(source_root.glob("sessions/*/05_failures/*.failure.json"))
    if not paths:
        return None
    path = paths[-1]
    return PersistedArtifact(path=path, payload=load_artifact(path), idempotent_replay=True)


def _record_expiry_failure(
    *,
    store_root: Path,
    intent,
    script,
    clock: Callable[[], str],
    session_started_at: str,
    prior_checkpoint: PersistedArtifact | None,
) -> PersistedArtifact:
    source_root = _source_root(store_root, intent)
    source_root.mkdir(parents=True, exist_ok=True)
    current = resolve_current_checkpoint(source_root)
    if prior_checkpoint is None or current is None:
        raise AcquisitionStateError("gmail_expiry_prior_checkpoint_required")
    if (
        current.payload["checkpoint_id"] != prior_checkpoint.payload["checkpoint_id"]
        or current.payload["artifact_hash"] != prior_checkpoint.payload["artifact_hash"]
    ):
        raise AcquisitionStateError("prior_checkpoint_not_current")
    session_id = derive_id(
        "oas",
        SESSION_SCHEMA,
        intent.cycle_id,
        session_started_at,
        "gmail_offline_fixture",
        "fixture",
    )
    session_root = source_root / f"sessions/{session_id}"
    intent_artifact = persist_intent(session_root, intent)
    session_artifact = persist_session(
        session_root,
        intent_payload=thaw_json(intent_artifact.payload),
        started_at=session_started_at,
        transport_kind="gmail_offline_fixture",
        mode="fixture",
    )
    attempt_artifact = persist_attempt(
        session_root,
        session_id=session_id,
        attempt=build_expired_attempt(script, clock=clock),
    )
    return persist_failure(
        session_root,
        session_id=session_id,
        failed_stage="gmail_history_request",
        failed_at=clock(),
        error_class=GmailHistoryExpiredError.__name__,
        error_code="gmail_history_checkpoint_expired",
        last_valid_artifacts=(intent_artifact, session_artifact, attempt_artifact),
    )


def run_gmail_history_offline_relationship_slice(
    *,
    fixture_path: str | Path,
    policy_path: str | Path,
    target_label_id: str,
    operational_store_root: str | Path,
    governed_run_root: str | Path,
    protection_key: bytes,
    protection_key_id: str,
    repository_root: str | Path,
    clock: Callable[[], str],
    session_started_at: str,
    prior_checkpoint: PersistedArtifact | None = None,
    prior_projection_path: str | Path | None = None,
    taxonomy_path: str | Path | None = None,
    content_library_root: str | Path | None = None,
    processor_failure_stage: str | None = None,
    kernel_failure_injector: Callable[[str], None] | None = None,
) -> GmailHistoryRelationshipResult:
    repository = Path(repository_root).resolve(strict=True)
    store_root = Path(operational_store_root).resolve(strict=False)
    policy = load_gmail_history_policy(
        policy_path,
        target_label_id=target_label_id,
        protection_key=protection_key,
        protection_key_id=protection_key_id,
    )
    script = load_gmail_fixture(fixture_path, policy=policy)
    if script.mode == "bootstrap":
        if prior_checkpoint is not None or prior_projection_path is not None:
            raise AcquisitionStateError("gmail_bootstrap_prior_state_forbidden")
    else:
        if prior_checkpoint is None or prior_projection_path is None:
            raise AcquisitionStateError("gmail_prior_state_required")
    intent = build_gmail_intent(
        script,
        policy=policy,
        protection_key=protection_key,
        prior_checkpoint=prior_checkpoint,
    )
    if script.mode == "expired":
        failure = _record_expiry_failure(
            store_root=store_root,
            intent=intent,
            script=script,
            clock=clock,
            session_started_at=session_started_at,
            prior_checkpoint=prior_checkpoint,
        )
        return GmailHistoryRelationshipResult(
            success=False,
            script_id=script.script_id,
            result=GmailHistoryOfflineResult(
                success=False,
                status="checkpoint_expired",
                script_id=script.script_id,
                failure_receipt=failure,
            ),
        )
    attempts, pages = build_gmail_captured_inputs(
        script,
        policy=policy,
        protection_key=protection_key,
        clock=clock,
    )
    processor = GmailHistoryGovernedProcessor(
        policy=policy,
        prior_projection_path=prior_projection_path,
        repository_root=repository,
        taxonomy_path=(
            Path(taxonomy_path)
            if taxonomy_path is not None
            else repository / "config/relationship_topics/governed_systems_v1.json"
        ),
        content_library_root=(
            Path(content_library_root)
            if content_library_root is not None
            else repository / "docs/operator/content_library"
        ),
        failure_stage=processor_failure_stage,
    )
    kernel = OperationalIngestionKernel(
        store_root,
        clock=clock,
        failure_injector=kernel_failure_injector,
    )
    try:
        execution = kernel.run_from_captured_pages(
            intent=intent,
            session_started_at=session_started_at,
            transport_kind="gmail_offline_fixture",
            mode="fixture",
            attempts=attempts,
            pages=pages,
            processor=processor,
            governed_run_root=governed_run_root,
        )
    except GmailHistoryCoverageError as exc:
        source_root = _source_root(store_root, intent)
        status = str(exc)
        return GmailHistoryRelationshipResult(
            success=False,
            script_id=script.script_id,
            result=GmailHistoryOfflineResult(
                success=False,
                status=status,
                script_id=script.script_id,
                failure_receipt=_latest_failure(source_root),
            ),
        )
    return GmailHistoryRelationshipResult(
        success=True,
        script_id=script.script_id,
        result=GmailHistoryOfflineResult(
            success=True,
            status="checkpoint_committed",
            script_id=script.script_id,
            execution=execution,
        ),
    )


def gmail_relationship_semantic_projection(run_root: str | Path) -> dict[str, Any]:
    root = Path(run_root)
    records = [
        json.loads(line)
        for line in (root / "01_normalized/relationship_records.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    projection = json.loads(
        (root / PROJECTION_RELATIVE_PATH).read_text(encoding="utf-8")
    )
    return {
        "provider_observation_set_hash": projection[
            "provider_observation_set_hash"
        ],
        "target_label_projection_set_hash": projection[
            "target_label_projection_set_hash"
        ],
        "transitions": projection["transitions"],
        "final_states": projection["final_states"],
        "unresolved_relevance": projection["unresolved_relevance"],
        "relationship_effects": [
            {
                "relationship_record_id": item["relationship_record_id"],
                "relationship": item["relationship"],
                "identifiers": item["identifiers"],
                "deterministic_classification": item[
                    "deterministic_classification"
                ],
                "privacy": item["privacy"],
            }
            for item in records
        ],
    }
