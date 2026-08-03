from __future__ import annotations

from signal_agent.evidence_sources.contracts import (
    ContextResolver,
    EvidenceSource,
    PacketBuilder,
    RelationshipAnalyzer,
    RelationshipNormalizer,
    RunManifestBuilder,
)
from signal_agent.evidence_sources.models import (
    NormalizedRelationshipBatch,
    PreservedEvidence,
    SourceReceiptDescriptor,
)


def test_evidence_source_public_contracts_are_importable() -> None:
    assert EvidenceSource
    assert RelationshipNormalizer
    assert RelationshipAnalyzer
    assert ContextResolver
    assert PacketBuilder
    assert RunManifestBuilder
    assert SourceReceiptDescriptor
    assert PreservedEvidence
    assert NormalizedRelationshipBatch
