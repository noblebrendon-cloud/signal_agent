from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from signal_agent.corpus_import.interaction_events import InteractionEventEvidenceAdapter
from signal_agent.corpus_import.receipts import utc_now_iso

from .analysis import GovernedSystemsRelationshipAnalyzer
from .content_library import TeachingAtomContextResolver
from .manifest import DetachedRunManifestBuilder
from .packets import GovernedRelationshipPacketBuilder
from .relationship_pipeline import run_relationship_signal_pipeline


@dataclass(frozen=True)
class InteractionEventRelationshipSliceResult:
    success: bool
    run_root: Path
    run_id: str
    record_count: int
    candidate_group_count: int
    cluster_confidence_state: str


def run_interaction_event_relationship_slice(
    *,
    source: str | Path,
    run_root: str | Path,
    hmac_key_file: str | Path,
    hmac_key_id: str,
    repo_root: str | Path,
    content_library_root: str | Path | None = None,
    taxonomy_path: str | Path | None = None,
    clock: Callable[[], str] = utc_now_iso,
) -> InteractionEventRelationshipSliceResult:
    """Compose an offline interaction-event export with the neutral pipeline."""

    code_repository = Path(__file__).resolve().parents[2]
    taxonomy_file = Path(taxonomy_path) if taxonomy_path else (
        code_repository / "config" / "relationship_topics" / "governed_systems_v1.json"
    )
    library_root = Path(content_library_root) if content_library_root else (
        code_repository / "docs" / "operator" / "content_library"
    )
    adapter = InteractionEventEvidenceAdapter(
        hmac_key_file=Path(hmac_key_file),
        hmac_key_id=hmac_key_id,
    )
    result = run_relationship_signal_pipeline(
        source=source,
        run_root=run_root,
        repository_root=repo_root,
        evidence_source=adapter,
        normalizer=adapter,
        analyzer=GovernedSystemsRelationshipAnalyzer(taxonomy_file),
        resolver=TeachingAtomContextResolver(library_root),
        packet_builder=GovernedRelationshipPacketBuilder(),
        manifest_builder=DetachedRunManifestBuilder(),
        clock=clock,
    )
    return InteractionEventRelationshipSliceResult(
        success=result.success,
        run_root=result.run_root,
        run_id=result.run_id,
        record_count=result.record_count,
        candidate_group_count=result.candidate_group_count,
        cluster_confidence_state=result.cluster_confidence_state,
    )
