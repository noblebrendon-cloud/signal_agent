from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from signal_agent.evidence_sources.canonical import (
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
)
from signal_agent.evidence_sources.contracts import (
    Clock,
    ContextResolver,
    EvidenceSource,
    PacketBuilder,
    RelationshipAnalyzer,
    RelationshipNormalizer,
    RunManifestBuilder,
)


RELATIONSHIP_RECORD_SCHEMA_VERSION = "signal_agent.relationship_record.v1"
UNRESOLVED_MATCH_SCHEMA_VERSION = "signal_agent.unresolved_relationship_matches.v1"
NORMALIZED_PATH = "01_normalized/relationship_records.jsonl"
UNRESOLVED_PATH = "02_analysis/unresolved_matches.json"
ANALYSIS_PATH = "02_analysis/topic_cluster.json"
CONTEXT_PATH = "02_analysis/related_work.json"
SIGNAL_PACKET_PATH = "04_packets/signal_packet.json"
CAMPAIGN_PACKET_PATH = "04_packets/campaign_context_packet.json"
MANIFEST_PATH = "05_receipts/run_manifest.json"


class RelationshipPipelineContractError(RuntimeError):
    pass


@dataclass(frozen=True)
class RelationshipPipelineResult:
    success: bool
    run_root: Path
    run_id: str
    record_count: int
    candidate_group_count: int
    cluster_confidence_state: str


def _jsonl_bytes(records: tuple[dict[str, Any], ...]) -> bytes:
    return b"".join(canonical_json_bytes(record) for record in records)


def _artifact(
    path: str,
    payload: bytes,
    *,
    media_type: str,
    schema_version: str,
    record_count: int,
) -> dict[str, Any]:
    return {
        "path": path,
        "sha256": f"sha256:{sha256_bytes(payload)}",
        "media_type": media_type,
        "schema_version": schema_version,
        "record_count": record_count,
    }


def _write_exclusive(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        written = handle.write(payload)
        if written != len(payload):
            raise OSError(f"Short write for governed artifact: {path}")
        handle.flush()
        os.fsync(handle.fileno())


def _stage_and_promote_artifacts(
    output_root: Path,
    artifacts: list[tuple[str, bytes]],
) -> None:
    staging_root = output_root / ".staging"
    for relative_path, payload in artifacts:
        _write_exclusive(staging_root / relative_path, payload)
    for relative_path, _payload in artifacts:
        staged = staging_root / relative_path
        destination = output_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with (
                staged.open("rb") as source_handle,
                destination.open("xb") as destination_handle,
            ):
                for chunk in iter(lambda: source_handle.read(1024 * 1024), b""):
                    destination_handle.write(chunk)
                destination_handle.flush()
                os.fsync(destination_handle.fileno())
        except FileExistsError as exc:
            raise RelationshipPipelineContractError(
                f"relationship_artifact_destination_exists:{relative_path}"
            ) from exc
        staged.unlink()
    directories = sorted(
        (path for path in staging_root.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    )
    for directory in directories:
        directory.rmdir()
    staging_root.rmdir()


def _resolved_artifact_path(output_root: Path, relative_path: str) -> Path:
    path = (output_root / relative_path).resolve(strict=True)
    if output_root != path and output_root not in path.parents:
        raise RelationshipPipelineContractError("evidence_artifact_path_escaped_run_root")
    return path


def _validate_batch_contract(batch: Any, preserved: Any) -> None:
    if batch.preserved is not preserved:
        raise RelationshipPipelineContractError(
            "normalizer_must_reference_supplied_preserved_evidence"
        )
    if any(
        record.get("schema_version") != RELATIONSHIP_RECORD_SCHEMA_VERSION
        for record in batch.records
    ):
        raise RelationshipPipelineContractError("relationship_record_schema_mismatch")
    if batch.unresolved_matches.get("schema_version") != UNRESOLVED_MATCH_SCHEMA_VERSION:
        raise RelationshipPipelineContractError("unresolved_match_schema_mismatch")


def run_relationship_signal_pipeline(
    *,
    source: str | Path,
    run_root: str | Path,
    repository_root: str | Path,
    evidence_source: EvidenceSource[Any],
    normalizer: RelationshipNormalizer[Any],
    analyzer: RelationshipAnalyzer,
    resolver: ContextResolver,
    packet_builder: PacketBuilder,
    manifest_builder: RunManifestBuilder,
    clock: Clock,
) -> RelationshipPipelineResult:
    """Run the relationship-only pipeline through injected ownership contracts."""

    repository = Path(repository_root).expanduser().resolve(strict=True)
    created_at = clock()

    def fixed_clock() -> str:
        return created_at

    prepared = evidence_source.prepare(
        source,
        repository_root=repository,
        clock=fixed_clock,
    )
    evidence_source.validate(
        prepared,
        repository_root=repository,
        clock=fixed_clock,
    )
    preserved = evidence_source.preserve(prepared, Path(run_root))
    batch = normalizer.normalize(prepared, preserved)
    _validate_batch_contract(batch, preserved)
    output_root = Path(run_root).expanduser().resolve(strict=True)
    receipt_path = _resolved_artifact_path(
        output_root,
        preserved.source_receipt.persisted_relative_path,
    )
    preserved_path = _resolved_artifact_path(
        output_root,
        preserved.preserved_relative_path,
    )
    if sha256_file(preserved_path) != preserved.source_sha256:
        raise RelationshipPipelineContractError("preserved_source_sha256_mismatch")
    analysis = analyzer.analyze(batch.records)
    context = resolver.resolve(analysis)

    normalized_bytes = _jsonl_bytes(batch.records)
    unresolved_bytes = canonical_json_bytes(batch.unresolved_matches)
    analysis_bytes = canonical_json_bytes(analysis)
    context_bytes = canonical_json_bytes(context)
    normalized_artifact = _artifact(
        NORMALIZED_PATH,
        normalized_bytes,
        media_type="application/x-ndjson",
        schema_version=RELATIONSHIP_RECORD_SCHEMA_VERSION,
        record_count=len(batch.records),
    )
    unresolved_artifact = _artifact(
        UNRESOLVED_PATH,
        unresolved_bytes,
        media_type="application/json",
        schema_version=batch.unresolved_matches["schema_version"],
        record_count=batch.unresolved_matches["candidate_group_count"],
    )
    analysis_artifact = _artifact(
        ANALYSIS_PATH,
        analysis_bytes,
        media_type="application/json",
        schema_version=analysis["schema_version"],
        record_count=len(analysis["deterministic_matches"]),
    )
    context_artifact = _artifact(
        CONTEXT_PATH,
        context_bytes,
        media_type="application/json",
        schema_version=context["schema_version"],
        record_count=len(context["results"]),
    )
    signal_packet = packet_builder.build_signal_packet(
        created_at=created_at,
        batch=batch,
        normalized_artifact=normalized_artifact,
        unresolved_artifact=unresolved_artifact,
        analysis_artifact=analysis_artifact,
        context_artifact=context_artifact,
        analysis=analysis,
        context=context,
    )
    signal_bytes = canonical_json_bytes(signal_packet)
    signal_artifact = _artifact(
        SIGNAL_PACKET_PATH,
        signal_bytes,
        media_type="application/json",
        schema_version=signal_packet["schema_version"],
        record_count=1,
    )
    campaign_packet = packet_builder.build_campaign_context_packet(
        created_at=created_at,
        signal_packet=signal_packet,
        signal_packet_path=SIGNAL_PACKET_PATH,
        signal_packet_file_sha256=sha256_bytes(signal_bytes),
    )
    campaign_bytes = canonical_json_bytes(campaign_packet)
    campaign_artifact = _artifact(
        CAMPAIGN_PACKET_PATH,
        campaign_bytes,
        media_type="application/json",
        schema_version=campaign_packet["schema_version"],
        record_count=1,
    )
    artifacts = [
        normalized_artifact,
        unresolved_artifact,
        analysis_artifact,
        context_artifact,
        signal_artifact,
        campaign_artifact,
    ]
    manifest = manifest_builder.build(
        created_at=created_at,
        batch=batch,
        source_receipt_file_sha256=sha256_file(receipt_path),
        analysis=analysis,
        artifacts=artifacts,
    )
    _stage_and_promote_artifacts(
        output_root,
        [
            (NORMALIZED_PATH, normalized_bytes),
            (UNRESOLVED_PATH, unresolved_bytes),
            (ANALYSIS_PATH, analysis_bytes),
            (CONTEXT_PATH, context_bytes),
            (SIGNAL_PACKET_PATH, signal_bytes),
            (CAMPAIGN_PACKET_PATH, campaign_bytes),
        ],
    )
    _write_exclusive(output_root / MANIFEST_PATH, canonical_json_bytes(manifest))
    return RelationshipPipelineResult(
        success=True,
        run_root=output_root,
        run_id=manifest["run_id"],
        record_count=len(batch.records),
        candidate_group_count=batch.unresolved_matches["candidate_group_count"],
        cluster_confidence_state=analysis["inferred_cluster"]["confidence_state"],
    )
