from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, fields
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from signal_agent.corpus_import.errors import RunCollisionError
from signal_agent.corpus_import.interaction_events import (
    InteractionEventEvidenceAdapter,
    InteractionEventImportError,
    InteractionEventKeyError,
    InteractionEventPreparedEvidence,
)
from signal_agent.evidence_sources.contracts import EvidenceSource, RelationshipNormalizer


FIXED_CLOCK = "2026-08-02T12:00:00Z"
TEST_ONLY_KEY = bytes.fromhex(
    "6f4cda45d36a935e170c901da31c50f1"
    "ab2e248b823fc8354603c92f35d6f23e"
)


def _paths(tmp_path: Path) -> tuple[Path, Path, Path]:
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    key_file = tmp_path / "interaction-event.relationship-hmac.key"
    key_file.write_bytes(TEST_ONLY_KEY)
    fixture = Path(__file__).resolve().parent / "fixtures/interaction_events/events.jsonl"
    return repository_root, key_file, fixture


def _adapter(key_file: Path) -> InteractionEventEvidenceAdapter:
    return InteractionEventEvidenceAdapter(key_file, "interaction-event-test-key-v1")


def _prepare(tmp_path: Path):
    repository_root, key_file, fixture = _paths(tmp_path)
    adapter = _adapter(key_file)
    prepared = adapter.prepare(
        fixture,
        repository_root=repository_root,
        clock=lambda: FIXED_CLOCK,
    )
    return repository_root, adapter, prepared


def test_public_contract_is_frozen_stateless_and_structural(tmp_path: Path) -> None:
    repository_root, key_file, fixture = _paths(tmp_path)
    adapter = _adapter(key_file)
    prepared = adapter.prepare(
        fixture,
        repository_root=repository_root,
        clock=lambda: FIXED_CLOCK,
    )

    assert isinstance(adapter, EvidenceSource)
    assert isinstance(adapter, RelationshipNormalizer)
    assert {item.name for item in fields(InteractionEventPreparedEvidence)} == {
        "import_plan",
        "key_context",
        "repository_root",
        "created_at",
    }
    with pytest.raises(FrozenInstanceError):
        prepared.created_at = "changed"  # type: ignore[misc]


def test_fixture_contract_timestamps_quality_privacy_and_conflicts(tmp_path: Path) -> None:
    repository_root, adapter, prepared = _prepare(tmp_path)
    adapter.validate(
        prepared,
        repository_root=repository_root,
        clock=lambda: FIXED_CLOCK,
    )
    preserved = adapter.preserve(prepared, tmp_path / "run")
    batch = InteractionEventEvidenceAdapter(
        adapter.hmac_key_file,
        adapter.hmac_key_id,
    ).normalize(prepared, preserved)

    assert batch.preserved is preserved
    assert len(batch.records) == 6
    assert [record["source_provenance"]["line_start"] for record in batch.records] == [
        1,
        2,
        4,
        5,
        6,
        7,
    ]
    assert batch.records[0]["relationship"]["occurred_at_utc"] == "2026-07-01T13:15:00Z"
    assert batch.records[1]["relationship"]["occurred_at_utc"] == "2026-07-01T13:30:00Z"
    assert "text_blank" in batch.records[3]["data_quality_issues"]
    assert set(batch.records[4]["data_quality_issues"]) == {
        "company_missing",
        "display_name_missing",
        "position_missing",
    }
    assert batch.unresolved_matches["candidate_group_count"] == 1
    conflict = batch.unresolved_matches["candidate_groups"][0]
    assert conflict["match_basis"] == "within_source_actor_metadata_conflict"
    assert conflict["canonical_identity_selected"] is False
    assert set(conflict["conflicting_fields"]) == {"company", "position"}
    assert "actor_metadata_conflict" in batch.records[0]["data_quality_issues"]
    assert "actor_metadata_conflict" in batch.records[2]["data_quality_issues"]
    assert all(
        record["source_provenance"]["raw_line_sha256"]
        == record["source_provenance"]["raw_row_sha256"]
        for record in batch.records
    )

    actor_tokens = [
        next(
            item["value"]
            for item in record["identifiers"]
            if item["kind"] == "actor_id_hmac"
        )
        for record in batch.records
    ]
    assert actor_tokens[0] == actor_tokens[2]
    assert batch.records[0]["relationship_record_id"] != batch.records[2][
        "relationship_record_id"
    ]
    normalized_text = json.dumps(batch.records, sort_keys=True)
    for clear_identifier in (
        "actor-alpha",
        "evt-001",
        "thread-red",
        "Discussed AI governance controls.",
    ):
        assert clear_identifier not in normalized_text

    schema = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "schemas/relationship_signals/relationship_record.v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    validator = Draft202012Validator(schema)
    assert not [error for record in batch.records for error in validator.iter_errors(record)]


def test_preservation_is_exact_and_receipt_is_complete(tmp_path: Path) -> None:
    _repository_root, adapter, prepared = _prepare(tmp_path)
    run_root = tmp_path / "run"
    preserved = adapter.preserve(prepared, run_root)

    original = run_root / preserved.preserved_relative_path
    sidecar = run_root / "00_original/interaction_events.jsonl.sha256.txt"
    receipt = json.loads(
        (run_root / preserved.source_receipt.persisted_relative_path).read_text(
            encoding="utf-8"
        )
    )
    assert original.read_bytes() == prepared.import_plan.source_path.read_bytes()
    assert sidecar.read_text(encoding="utf-8") == (
        f"{prepared.import_plan.source_sha256}  interaction_events.jsonl\n"
    )
    assert receipt["source"]["physical_line_count"] == 7
    assert receipt["source"]["blank_line_count"] == 1
    assert receipt["source"]["record_count"] == 6
    assert receipt["source"]["timestamp_min_utc"] == "2026-07-01T13:15:00Z"
    assert receipt["source"]["timestamp_max_utc"] == "2026-07-04T15:00:00Z"
    assert receipt["identifier_protection"] == {
        "algorithm": "HMAC-SHA-256",
        "key_id": "interaction-event-test-key-v1",
        "version": "interaction_event_actor_identity_token.v1",
    }
    with pytest.raises(RunCollisionError):
        adapter.preserve(prepared, run_root)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"{not json}\n", "json_invalid"),
        (
            b'{"event_id":"e","actor_id":"a","thread_id":"t","timestamp":"2026-01-01T00:00:00Z"}\n',
            "required_field_missing:text",
        ),
        (
            b'{"event_id":"e","actor_id":"a","thread_id":"t","timestamp":"2026-01-01T00:00:00","text":"x"}\n',
            "timestamp_offset_required",
        ),
        (
            b'{"event_id":"e","actor_id":"a","thread_id":"t","timestamp":"2026-01-01T00:00:00Z","text":"x"}\n'
            b'{"event_id":"e","actor_id":"b","thread_id":"t","timestamp":"2026-01-01T00:01:00Z","text":"y"}\n',
            "duplicate_event_id",
        ),
        (b"\n\r\n", "has_no_records"),
        (b"\xff\xfe\x00", "utf8_required"),
    ],
)
def test_fatal_source_validation_conditions(
    tmp_path: Path,
    payload: bytes,
    message: str,
) -> None:
    repository_root, key_file, _fixture = _paths(tmp_path)
    source = tmp_path / "invalid.jsonl"
    source.write_bytes(payload)
    with pytest.raises(InteractionEventImportError, match=message):
        _adapter(key_file).prepare(
            source,
            repository_root=repository_root,
            clock=lambda: FIXED_CLOCK,
        )


def test_missing_and_nonregular_sources_are_rejected(tmp_path: Path) -> None:
    repository_root, key_file, _fixture = _paths(tmp_path)
    adapter = _adapter(key_file)
    with pytest.raises(InteractionEventImportError, match="source_unreadable"):
        adapter.prepare(
            tmp_path / "missing.jsonl",
            repository_root=repository_root,
            clock=lambda: FIXED_CLOCK,
        )
    directory = tmp_path / "directory.jsonl"
    directory.mkdir()
    with pytest.raises(InteractionEventImportError, match="source_not_regular_file"):
        adapter.prepare(
            directory,
            repository_root=repository_root,
            clock=lambda: FIXED_CLOCK,
        )


def test_key_and_repository_rules_fail_closed(tmp_path: Path) -> None:
    repository_root, key_file, fixture = _paths(tmp_path)
    short_key = tmp_path / "short.key"
    short_key.write_bytes(b"short")
    with pytest.raises(InteractionEventKeyError, match="material_too_short"):
        _adapter(short_key).prepare(
            fixture,
            repository_root=repository_root,
            clock=lambda: FIXED_CLOCK,
        )
    in_repo_key = repository_root / "key.bin"
    in_repo_key.write_bytes(TEST_ONLY_KEY)
    with pytest.raises(InteractionEventKeyError, match="must_be_outside_repository"):
        _adapter(in_repo_key).prepare(
            fixture,
            repository_root=repository_root,
            clock=lambda: FIXED_CLOCK,
        )
    with pytest.raises(InteractionEventKeyError, match="key_id_invalid"):
        InteractionEventEvidenceAdapter(key_file, "bad key id").prepare(
            fixture,
            repository_root=repository_root,
            clock=lambda: FIXED_CLOCK,
        )


def test_prepared_repository_source_and_key_identity_are_validated(tmp_path: Path) -> None:
    repository_root, adapter, prepared = _prepare(tmp_path)
    other_repository = tmp_path / "other-repo"
    other_repository.mkdir()
    with pytest.raises(InteractionEventImportError, match="repository_mismatch"):
        adapter.validate(
            prepared,
            repository_root=other_repository,
            clock=lambda: FIXED_CLOCK,
        )

    adapter.hmac_key_file.write_bytes(b"x" * 32)
    with pytest.raises(InteractionEventKeyError, match="material_changed"):
        adapter.validate(
            prepared,
            repository_root=repository_root,
            clock=lambda: FIXED_CLOCK,
        )
