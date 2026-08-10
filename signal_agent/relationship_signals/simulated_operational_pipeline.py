from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from signal_agent.corpus_import.simulated_operational import (
    SimulatedOperationalEvidenceAdapter,
)
from signal_agent.operational_ingestion.canonical import (
    canonical_json_bytes,
    derive_id,
    seal,
    sha256_bytes,
)
from signal_agent.operational_ingestion.models import (
    CompletedRunReference,
    PersistedArtifact,
)
from signal_agent.operational_ingestion.simulator import (
    DeterministicVirtualClock,
    PartialAcquisition,
    SimulatedAcquisitionCoordinator,
    SimulatedExecutionResult,
    SimulatedOperationalTransport,
    SimulatedRemoteInteractionSource,
    build_simulated_intent,
    load_retry_policy,
    load_simulated_script,
)

from .analysis import GovernedSystemsRelationshipAnalyzer
from .content_library import TeachingAtomContextResolver
from .manifest import DetachedRunManifestBuilder
from .packets import GovernedRelationshipPacketBuilder
from .relationship_pipeline import run_relationship_signal_pipeline


OPERATIONAL_COMPLETED_MANIFEST_SCHEMA = (
    "signal_agent.simulated_operational_completed_manifest.v1"
)
OPERATIONAL_MANIFEST_PATH = "05_receipts/operational_completed_manifest.json"


@dataclass(frozen=True)
class SimulatedOperationalRelationshipResult:
    success: bool
    script_id: str
    execution: SimulatedExecutionResult


def _write_exact(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if not path.is_file() or path.read_bytes() != payload:
            raise RuntimeError(f"simulated_governed_artifact_conflict:{path.name}")
        return
    try:
        with path.open("xb") as handle:
            if handle.write(payload) != len(payload):
                raise OSError("simulated_governed_short_write")
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        if not path.is_file() or path.read_bytes() != payload:
            raise RuntimeError(f"simulated_governed_artifact_conflict:{path.name}")


class _FailureAwareAdapter:
    def __init__(self, failure_stage: str | None) -> None:
        self.delegate = SimulatedOperationalEvidenceAdapter()
        self.failure_stage = failure_stage
        self.source_type = self.delegate.source_type

    def prepare(self, source, *, repository_root, clock):
        return self.delegate.prepare(
            source, repository_root=repository_root, clock=clock
        )

    def validate(self, prepared, *, repository_root, clock) -> None:
        self.delegate.validate(
            prepared, repository_root=repository_root, clock=clock
        )

    def preserve(self, prepared, run_root):
        if self.failure_stage == "preservation_failure":
            raise RuntimeError("simulated_preservation_failure")
        preserved = self.delegate.preserve(prepared, run_root)
        if self.failure_stage == "after_preservation_failure":
            raise RuntimeError("simulated_after_preservation_failure")
        return preserved

    def normalize(self, prepared, preserved):
        if self.failure_stage == "normalization_failure":
            raise RuntimeError("simulated_normalization_failure")
        return self.delegate.normalize(prepared, preserved)


class _FailureAwareAnalyzer:
    def __init__(self, delegate, failure_stage: str | None) -> None:
        self.delegate = delegate
        self.failure_stage = failure_stage

    def analyze(self, records):
        if self.failure_stage == "downstream_processing_failure":
            raise RuntimeError("simulated_downstream_processing_failure")
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


class SimulatedOperationalGovernedProcessor:
    """Connect finite simulator evidence to the unchanged relationship runner."""

    def __init__(
        self,
        *,
        repository_root: str | Path,
        taxonomy_path: str | Path,
        content_library_root: str | Path,
        failure_stage: str | None = None,
    ) -> None:
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
        relationship_root = governed_root
        adapter = _FailureAwareAdapter(self.failure_stage)
        result = run_relationship_signal_pipeline(
            source=bounded_material_path,
            run_root=relationship_root,
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
                relationship_root,
                self.failure_stage,
            ),
            clock=clock,
        )
        if self.failure_stage in {
            "after_downstream_output_before_completed_manifest",
            "operational_manifest_write_failure",
        }:
            raise RuntimeError("simulated_completed_manifest_not_promoted")
        bounded_bytes = bounded_material_path.read_bytes()
        bounded = json.loads(bounded_bytes.decode("utf-8"))
        input_ref = {
            "bounded_material_id": bounded["bounded_material_id"],
            "bounded_material_hash": bounded["artifact_hash"],
            "observation_set_hash": bounded["observation_set_hash"],
        }
        receipt_relative = "05_receipts/simulated_operational_source_receipt.json"
        preserved_relative = "00_original/simulated_operational_bounded_source.json"
        receipt_path = governed_root / receipt_relative
        preserved_path = governed_root / preserved_relative
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        relationship_manifest_path = relationship_root / "05_receipts/run_manifest.json"
        relationship_manifest = json.loads(
            relationship_manifest_path.read_text(encoding="utf-8")
        )
        artifacts = []
        for path in sorted(relationship_root.rglob("*")):
            if not path.is_file() or path in {receipt_path, preserved_path}:
                continue
            artifacts.append(
                {
                    "path": path.relative_to(governed_root).as_posix(),
                    "sha256": sha256_bytes(path.read_bytes()),
                }
            )
        if not artifacts:
            raise RuntimeError("simulated_governed_artifacts_required")
        created_at = clock()
        material = {
            "schema_version": OPERATIONAL_COMPLETED_MANIFEST_SCHEMA,
            "run_id": derive_id(
                "sogr",
                input_ref,
                relationship_manifest["run_id"],
            ),
            "created_at": created_at,
            "completion_state": "completed",
            "operational_input": input_ref,
            "preservation_receipt": {
                "path": receipt_relative,
                "receipt_id": receipt["receipt_id"],
                "receipt_hash": receipt["receipt_hash"],
                "file_sha256": sha256_bytes(receipt_path.read_bytes()),
            },
            "preserved_source": {
                "path": preserved_relative,
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
                "file_sha256": sha256_bytes(
                    relationship_manifest_path.read_bytes()
                ),
            },
            "artifacts": artifacts,
            "safety_flags": {
                "network_authorized": False,
                "source_records_mutated": False,
                "upstream_write_authorized": False,
            },
        }
        manifest_id = derive_id("sogm", OPERATIONAL_COMPLETED_MANIFEST_SCHEMA, material)
        manifest = seal(
            {**material, "manifest_id": manifest_id},
            "manifest_hash",
        )
        if self.failure_stage == "manifest_verification_failure":
            corrupted = dict(manifest)
            corrupted_artifacts = [dict(item) for item in corrupted["artifacts"]]
            corrupted_artifacts[0]["sha256"] = "sha256:" + ("0" * 64)
            corrupted["artifacts"] = corrupted_artifacts
            manifest = seal(
                {key: value for key, value in corrupted.items() if key != "manifest_hash"},
                "manifest_hash",
            )
        manifest_path = governed_root / OPERATIONAL_MANIFEST_PATH
        _write_exact(manifest_path, canonical_json_bytes(manifest))
        return CompletedRunReference(
            run_id=manifest["run_id"],
            run_root=governed_root,
            run_root_ref=f"simulated-operational-governed-run:{manifest['run_id']}",
            manifest_relative_path=OPERATIONAL_MANIFEST_PATH,
            preservation_receipt_relative_path=receipt_relative,
        )


def run_simulated_operational_relationship_slice(
    *,
    script_path: str | Path,
    retry_policy_path: str | Path,
    operational_store_root: str | Path,
    governed_run_root: str | Path,
    protection_key: bytes,
    protection_key_id: str,
    repository_root: str | Path,
    clock: DeterministicVirtualClock,
    session_started_at: str,
    prior_checkpoint: PersistedArtifact | None = None,
    taxonomy_path: str | Path | None = None,
    content_library_root: str | Path | None = None,
    resume: PartialAcquisition | None = None,
    interrupt_after_pages: int | None = None,
    processor_failure_stage: str | None = None,
    acquisition_failure_injector: Callable[[str], None] | None = None,
    kernel_failure_injector: Callable[[str], None] | None = None,
    maximum_pages: int = 10,
    maximum_records: int = 100,
    maximum_response_bytes: int = 1024 * 1024,
    upper_boundary: str = "terminal",
) -> SimulatedOperationalRelationshipResult:
    repository = Path(repository_root).resolve(strict=True)
    script = load_simulated_script(script_path)
    retry_policy = load_retry_policy(retry_policy_path)
    source = SimulatedRemoteInteractionSource(
        script=script,
        protection_key=protection_key,
        protection_key_id=protection_key_id,
        maximum_pages=maximum_pages,
        maximum_records=maximum_records,
        maximum_response_bytes=maximum_response_bytes,
    )
    intent = build_simulated_intent(
        source_instance_id=script.source_instance_id,
        retry_policy=retry_policy,
        prior_checkpoint=prior_checkpoint,
        upper_boundary=upper_boundary,
    )
    processor = SimulatedOperationalGovernedProcessor(
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
    coordinator = SimulatedAcquisitionCoordinator(
        operational_store_root,
        clock=clock,
        retry_policy=retry_policy,
        acquisition_failure_injector=acquisition_failure_injector,
        kernel_failure_injector=kernel_failure_injector,
    )
    execution = coordinator.run(
        intent=intent,
        source=source,
        transport=SimulatedOperationalTransport(script),
        processor=processor,
        governed_run_root=governed_run_root,
        session_started_at=session_started_at,
        resume=resume,
        interrupt_after_pages=interrupt_after_pages,
    )
    return SimulatedOperationalRelationshipResult(
        success=True,
        script_id=script.script_id,
        execution=execution,
    )


def relationship_semantic_projection(run_root: str | Path) -> dict[str, Any]:
    """Transport-independent projection used only for equivalence verification."""

    root = Path(run_root)
    normalized_path = root / "01_normalized/relationship_records.jsonl"
    records = [
        json.loads(line)
        for line in normalized_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    effects = []
    for record in records:
        effects.append(
            {
                "relationship_record_id": record["relationship_record_id"],
                "person": record["person"],
                "professional_context": record["professional_context"],
                "relationship": record["relationship"],
                "identifiers": record["identifiers"],
                "deterministic_classification": record[
                    "deterministic_classification"
                ],
                "data_quality_issues": record["data_quality_issues"],
                "privacy": record["privacy"],
            }
        )
    analysis_path = root / "02_analysis/topic_cluster.json"
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    return {
        "effects": effects,
        "analysis": {
            "taxonomy": analysis["taxonomy"],
            "inferred_cluster": analysis["inferred_cluster"],
            "deterministic_matches": [
                {
                    key: value
                    for key, value in item.items()
                    if key != "evidence_ref"
                }
                for item in analysis["deterministic_matches"]
            ],
        },
    }
