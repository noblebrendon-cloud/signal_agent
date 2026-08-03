from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Protocol, TypeVar, runtime_checkable

from .models import NormalizedRelationshipBatch, PreservedEvidence


PreparedT = TypeVar("PreparedT")
Clock = Callable[[], str]


@runtime_checkable
class EvidenceSource(Protocol[PreparedT]):
    """Adapter-owned preparation, validation, and preservation boundary."""

    source_type: str

    def prepare(
        self,
        source: str | Path,
        *,
        repository_root: Path,
        clock: Clock,
    ) -> PreparedT:
        ...

    def validate(
        self,
        prepared: PreparedT,
        *,
        repository_root: Path,
        clock: Clock,
    ) -> None:
        ...

    def preserve(self, prepared: PreparedT, run_root: Path) -> PreservedEvidence:
        ...


@runtime_checkable
class RelationshipNormalizer(Protocol[PreparedT]):
    """Specialize preserved evidence into governed relationship records."""

    def normalize(
        self,
        prepared: PreparedT,
        preserved: PreservedEvidence,
    ) -> NormalizedRelationshipBatch:
        ...


@runtime_checkable
class RelationshipAnalyzer(Protocol):
    def analyze(self, records: tuple[dict[str, Any], ...]) -> dict[str, Any]:
        ...


@runtime_checkable
class ContextResolver(Protocol):
    def resolve(self, analysis: dict[str, Any]) -> dict[str, Any]:
        ...


@runtime_checkable
class PacketBuilder(Protocol):
    def build_signal_packet(
        self,
        *,
        created_at: str,
        batch: NormalizedRelationshipBatch,
        normalized_artifact: dict[str, Any],
        unresolved_artifact: dict[str, Any],
        analysis_artifact: dict[str, Any],
        context_artifact: dict[str, Any],
        analysis: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        ...

    def build_campaign_context_packet(
        self,
        *,
        created_at: str,
        signal_packet: dict[str, Any],
        signal_packet_path: str,
        signal_packet_file_sha256: str,
    ) -> dict[str, Any]:
        ...


@runtime_checkable
class RunManifestBuilder(Protocol):
    def build(
        self,
        *,
        created_at: str,
        batch: NormalizedRelationshipBatch,
        source_receipt_file_sha256: str,
        analysis: dict[str, Any],
        artifacts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        ...
