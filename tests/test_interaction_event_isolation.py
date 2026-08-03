from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from signal_agent.corpus_import.interaction_events import InteractionEventEvidenceAdapter
from signal_agent.corpus_import.linkedin.adapter import LinkedInEvidenceAdapter
from signal_agent.relationship_signals.analysis import GovernedSystemsRelationshipAnalyzer
from signal_agent.relationship_signals.content_library import TeachingAtomContextResolver
from signal_agent.relationship_signals.manifest import DetachedRunManifestBuilder
from signal_agent.relationship_signals.packets import GovernedRelationshipPacketBuilder
from signal_agent.relationship_signals.relationship_pipeline import (
    run_relationship_signal_pipeline,
)


FIXED_CLOCK = "2026-08-02T12:00:00Z"
TEST_ONLY_KEY = bytes.fromhex(
    "6f4cda45d36a935e170c901da31c50f1"
    "ab2e248b823fc8354603c92f35d6f23e"
)


def _interaction_adapter(key_file: Path) -> InteractionEventEvidenceAdapter:
    return InteractionEventEvidenceAdapter(key_file, "interleaved-test-key-v1")


def test_prepared_values_interleave_across_instances_without_state_leakage(
    tmp_path: Path,
) -> None:
    fake_repo = tmp_path / "repo"
    fake_repo.mkdir()
    key_file = tmp_path / "key.bin"
    key_file.write_bytes(TEST_ONLY_KEY)
    fixture = Path(__file__).resolve().parent / "fixtures/interaction_events/events.jsonl"
    source_a = tmp_path / "a.jsonl"
    source_b = tmp_path / "b.jsonl"
    source_a.write_bytes(fixture.read_bytes())
    source_b.write_bytes(
        fixture.read_bytes().replace(b'"evt-006"', b'"evt-106"')
    )
    first = _interaction_adapter(key_file)
    second = _interaction_adapter(key_file)
    prepared_a = first.prepare(
        source_a,
        repository_root=fake_repo,
        clock=lambda: FIXED_CLOCK,
    )
    prepared_b = second.prepare(
        source_b,
        repository_root=fake_repo,
        clock=lambda: FIXED_CLOCK,
    )

    second.validate(
        prepared_a,
        repository_root=fake_repo,
        clock=lambda: FIXED_CLOCK,
    )
    first.validate(
        prepared_b,
        repository_root=fake_repo,
        clock=lambda: FIXED_CLOCK,
    )
    preserved_b = first.preserve(prepared_b, tmp_path / "run-b")
    preserved_a = second.preserve(prepared_a, tmp_path / "run-a")
    batch_a = _interaction_adapter(key_file).normalize(prepared_a, preserved_a)
    batch_b = _interaction_adapter(key_file).normalize(prepared_b, preserved_b)

    assert batch_a.preserved is preserved_a
    assert batch_b.preserved is preserved_b
    assert batch_a.preserved.source_sha256 != batch_b.preserved.source_sha256
    assert batch_a.records[-1]["relationship_record_id"] != batch_b.records[-1][
        "relationship_record_id"
    ]


def test_linkedin_and_interaction_adapters_can_be_prepared_and_completed_interleaved(
    tmp_path: Path,
) -> None:
    fake_repo = tmp_path / "repo"
    fake_repo.mkdir()
    key_file = tmp_path / "key.bin"
    key_file.write_bytes(TEST_ONLY_KEY)
    fixture_root = Path(__file__).resolve().parent / "fixtures"
    interaction = _interaction_adapter(key_file)
    linkedin = LinkedInEvidenceAdapter(key_file, "interleaved-test-key-v1")
    prepared_interaction = interaction.prepare(
        fixture_root / "interaction_events/events.jsonl",
        repository_root=fake_repo,
        clock=lambda: FIXED_CLOCK,
    )
    prepared_linkedin = linkedin.prepare(
        fixture_root / "linkedin_connections/Connections.csv",
        repository_root=fake_repo,
        clock=lambda: FIXED_CLOCK,
    )

    linkedin.validate(
        prepared_linkedin,
        repository_root=fake_repo,
        clock=lambda: FIXED_CLOCK,
    )
    interaction.validate(
        prepared_interaction,
        repository_root=fake_repo,
        clock=lambda: FIXED_CLOCK,
    )
    preserved_linkedin = linkedin.preserve(prepared_linkedin, tmp_path / "linkedin-run")
    preserved_interaction = interaction.preserve(
        prepared_interaction, tmp_path / "interaction-run"
    )
    linkedin_batch = LinkedInEvidenceAdapter(
        key_file, "interleaved-test-key-v1"
    ).normalize(prepared_linkedin, preserved_linkedin)
    interaction_batch = _interaction_adapter(key_file).normalize(
        prepared_interaction, preserved_interaction
    )

    assert len(linkedin_batch.records) == 7
    assert len(interaction_batch.records) == 6
    assert linkedin_batch.preserved is preserved_linkedin
    assert interaction_batch.preserved is preserved_interaction


def test_failure_after_preservation_leaves_receipt_and_no_completed_manifest(
    tmp_path: Path,
) -> None:
    repository_root = Path(__file__).resolve().parents[1]
    fake_repo = tmp_path / "repo"
    fake_repo.mkdir()
    key_file = tmp_path / "key.bin"
    key_file.write_bytes(TEST_ONLY_KEY)
    source = Path(__file__).resolve().parent / "fixtures/interaction_events/events.jsonl"
    run_root = tmp_path / "failed-run"

    class _FailingAnalyzer:
        def analyze(self, records: tuple[dict[str, Any], ...]) -> dict[str, Any]:
            assert len(records) == 6
            raise RuntimeError("injected_interaction_analysis_failure")

    adapter = _interaction_adapter(key_file)
    with pytest.raises(RuntimeError, match="injected_interaction_analysis_failure"):
        run_relationship_signal_pipeline(
            source=source,
            run_root=run_root,
            repository_root=fake_repo,
            evidence_source=adapter,
            normalizer=InteractionEventEvidenceAdapter(
                key_file, "interleaved-test-key-v1"
            ),
            analyzer=_FailingAnalyzer(),
            resolver=TeachingAtomContextResolver(
                repository_root / "docs/operator/content_library"
            ),
            packet_builder=GovernedRelationshipPacketBuilder(),
            manifest_builder=DetachedRunManifestBuilder(),
            clock=lambda: FIXED_CLOCK,
        )

    assert (run_root / "00_original/interaction_events.jsonl").is_file()
    assert (run_root / "05_receipts/source_receipt.json").is_file()
    assert not (run_root / "05_receipts/run_manifest.json").exists()
    assert not (run_root / "01_normalized/relationship_records.jsonl").exists()
    assert not (run_root / ".staging").exists()
