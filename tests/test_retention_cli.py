from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.retention import cli as retention_cli
from app.retention.dispatch import plan_dispatch
from app.retention.jsonl_store import append_record, preview_record
from app.retention.models import build_contact_seed_event, build_contact_snapshot
from app.retention.transitions import evaluate_transition


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    lines = [",".join(fieldnames)]
    for row in rows:
        lines.append(",".join(str(row.get(name, "")) for name in fieldnames))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture
def retention_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    monkeypatch.setenv("SIGNAL_AGENT_ROOT", str(root))
    return root


def test_dry_run_writes_nothing(retention_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    result = retention_cli.main(
        [
            "add-contact",
            "--source",
            "substack",
            "--identifier-kind",
            "email",
            "--identifier-value",
            "test@example.com",
            "--consent-status",
            "opted_in",
            "--dry-run",
        ]
    )

    assert result == 0
    assert not (retention_root / "data" / "state").exists()
    output = capsys.readouterr().out
    assert "test@example.com" not in output
    assert '"dispatch_type": "orientation_email"' in output


def test_apply_appends_event_transition_contact_and_dispatch_without_raw_identifier(
    retention_root: Path,
) -> None:
    result = retention_cli.main(
        [
            "add-contact",
            "--source",
            "substack",
            "--identifier-kind",
            "email",
            "--identifier-value",
            "test@example.com",
            "--consent-status",
            "opted_in",
            "--apply",
            "--plan-dispatch",
        ]
    )

    assert result == 0
    state_root = retention_root / "data" / "state"
    events = _read_jsonl(state_root / "events.jsonl")
    transitions = _read_jsonl(state_root / "transitions.jsonl")
    contacts = _read_jsonl(state_root / "contacts.jsonl")
    dispatches = _read_jsonl(state_root / "content_dispatch.jsonl")

    assert len(events) == 1
    assert len(transitions) == 1
    assert len(contacts) == 1
    assert len(dispatches) == 1
    assert transitions[0]["decision"] == "applied"
    assert contacts[0]["current_state"] == "subscribed"
    assert contacts[0]["identity_alignment_score"] == 0
    assert contacts[0]["conversion"] == {
        "objective": None,
        "status": "none",
        "converted_at": None,
        "evidence_event_id": None,
    }
    assert dispatches[0]["dispatch_type"] == "orientation_email"

    event_text = (state_root / "events.jsonl").read_text(encoding="utf-8")
    contacts_text = (state_root / "contacts.jsonl").read_text(encoding="utf-8")
    assert "test@example.com" not in event_text
    assert "test@example.com" not in contacts_text


def test_second_append_prev_hash_matches_first_record_hash(retention_root: Path) -> None:
    first = append_record(
        "events.jsonl",
        {"record_type": "chain_test", "event_id": "first"},
        recorded_at="2026-05-01T00:00:00Z",
    )
    second = append_record(
        "events.jsonl",
        {"record_type": "chain_test", "event_id": "second"},
        recorded_at="2026-05-01T00:00:01Z",
    )

    assert first["prev_hash"] is None
    assert second["prev_hash"] == first["record_hash"]


def test_record_hash_changes_when_prev_hash_changes(retention_root: Path) -> None:
    base_record = {"record_type": "chain_test", "event_id": "same"}
    without_prev = preview_record(
        "hash_compare_a.jsonl",
        base_record,
        recorded_at="2026-05-01T00:00:00Z",
    )
    seed = append_record(
        "hash_compare_b.jsonl",
        {"record_type": "chain_test", "event_id": "seed"},
        recorded_at="2026-05-01T00:00:00Z",
    )
    with_prev = preview_record(
        "hash_compare_b.jsonl",
        base_record,
        recorded_at="2026-05-01T00:00:00Z",
    )

    assert without_prev["prev_hash"] is None
    assert with_prev["prev_hash"] == seed["record_hash"]
    assert without_prev["record_hash"] != with_prev["record_hash"]


def test_invalid_trailing_jsonl_causes_append_failure(retention_root: Path) -> None:
    state_root = retention_root / "data" / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    target = state_root / "events.jsonl"
    target.write_text('{"record_hash":"sha256:ok"}\n{"broken":\n', encoding="utf-8")
    before = target.read_text(encoding="utf-8")

    with pytest.raises(ValueError, match="invalid_jsonl"):
        append_record(
            "events.jsonl",
            {"record_type": "chain_test", "event_id": "third"},
            recorded_at="2026-05-01T00:00:02Z",
        )

    assert target.read_text(encoding="utf-8") == before


def test_existing_files_are_preserved_and_only_appended(retention_root: Path) -> None:
    state_root = retention_root / "data" / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    sentinel_event = preview_record(
        "events.jsonl",
        {"record_type": "sentinel", "value": 1},
        repo_root=retention_root,
        recorded_at="2026-05-01T00:00:00Z",
    )
    (state_root / "events.jsonl").write_text(json.dumps(sentinel_event) + "\n", encoding="utf-8")
    (state_root / "contacts.jsonl").write_text("", encoding="utf-8")
    (state_root / "transitions.jsonl").write_text("", encoding="utf-8")
    (state_root / "content_dispatch.jsonl").write_text("", encoding="utf-8")

    before = (state_root / "events.jsonl").read_text(encoding="utf-8")

    result = retention_cli.main(
        [
            "add-contact",
            "--source",
            "linkedin",
            "--identifier-kind",
            "email",
            "--identifier-value",
            "append@example.com",
            "--consent-status",
            "unknown",
            "--apply",
        ]
    )

    assert result == 0
    after_rows = _read_jsonl(state_root / "events.jsonl")
    assert len(after_rows) == 2
    assert after_rows[0] == sentinel_event
    assert (state_root / "events.jsonl").read_text(encoding="utf-8").startswith(before)


def test_aggregate_event_does_not_create_contact(retention_root: Path) -> None:
    event = build_contact_seed_event(
        source="operator",
        identifier_kind="email",
        identifier_value="aggregate@example.com",
        consent_status="opted_in",
        scope="aggregate",
    )
    transition = evaluate_transition(event, previous_snapshot=None)
    snapshot = build_contact_snapshot(previous_snapshot=None, event=event, transition=transition)

    assert transition["decision"] == "rejected"
    assert snapshot is None


def test_suppressed_contact_receives_no_dispatch(retention_root: Path) -> None:
    seeded = build_contact_seed_event(
        source="substack",
        identifier_kind="email",
        identifier_value="blocked@example.com",
        consent_status="opted_in",
    )
    seeded_transition = evaluate_transition(seeded, previous_snapshot=None)
    snapshot = build_contact_snapshot(previous_snapshot=None, event=seeded, transition=seeded_transition)
    assert snapshot is not None

    unsubscribe_event = build_contact_seed_event(
        source="operator",
        identifier_kind="email",
        identifier_value="blocked@example.com",
        consent_status="opted_in",
        event_type="unsubscribe",
    )
    unsubscribe_transition = evaluate_transition(unsubscribe_event, previous_snapshot=snapshot)
    suppressed_snapshot = build_contact_snapshot(
        previous_snapshot=snapshot,
        event=unsubscribe_event,
        transition=unsubscribe_transition,
    )

    assert unsubscribe_transition["decision"] == "applied"
    assert suppressed_snapshot is not None
    assert suppressed_snapshot["current_state"] == "suppressed"

    dispatch_plan = plan_dispatch(suppressed_snapshot, contact_id=suppressed_snapshot["contact_id"])
    assert dispatch_plan["decision"] == "blocked"
    assert "suppressed_contacts_block_dispatch" in dispatch_plan["reason_codes"]


def test_objection_and_lawful_objection_both_suppress(retention_root: Path) -> None:
    seeded = build_contact_seed_event(
        source="substack",
        identifier_kind="email",
        identifier_value="object@example.com",
        consent_status="opted_in",
    )
    seeded_transition = evaluate_transition(seeded, previous_snapshot=None)
    snapshot = build_contact_snapshot(previous_snapshot=None, event=seeded, transition=seeded_transition)
    assert snapshot is not None

    for event_type in ("objection", "lawful_objection"):
        suppression_event = build_contact_seed_event(
            source="operator",
            identifier_kind="email",
            identifier_value="object@example.com",
            consent_status="opted_in",
            event_type=event_type,
        )
        suppression_transition = evaluate_transition(suppression_event, previous_snapshot=snapshot)
        assert suppression_transition["decision"] == "applied"
        assert suppression_transition["to_state"] == "suppressed"
        assert suppression_transition["rule_id"] == "retention.objection.to_suppressed"


def test_contact_snapshot_only_appears_after_applied_transition(retention_root: Path) -> None:
    state_root = retention_root / "data" / "state"
    state_root.mkdir(parents=True, exist_ok=True)

    event = build_contact_seed_event(
        source="operator",
        identifier_kind="email",
        identifier_value="noop@example.com",
        consent_status="opted_in",
    )
    first_transition = evaluate_transition(event, previous_snapshot=None)
    first_snapshot = build_contact_snapshot(previous_snapshot=None, event=event, transition=first_transition)
    assert first_snapshot is not None
    append_record("contacts.jsonl", first_snapshot)

    second_transition = evaluate_transition(event, previous_snapshot=first_snapshot)
    second_snapshot = build_contact_snapshot(
        previous_snapshot=first_snapshot,
        event=event,
        transition=second_transition,
    )

    assert second_transition["decision"] == "noop"
    assert second_snapshot is None


def test_ingest_substack_csv_dry_run_writes_nothing(
    retention_root: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    csv_path = tmp_path / "substack.csv"
    _write_csv(
        csv_path,
        [{"Email": "test@example.com", "Status": "active"}],
        ["Email", "Status"],
    )

    result = retention_cli.main(
        [
            "ingest-substack-csv",
            "--input",
            str(csv_path),
            "--dry-run",
        ]
    )

    assert result == 0
    assert not (retention_root / "data" / "state").exists()
    assert not (retention_root / "data" / "raw").exists()
    report = json.loads(capsys.readouterr().out)
    assert report["rows_seen"] == 1
    assert report["events_previewed"] == 1
    assert report["transitions_previewed"] == 1
    assert report["contacts_previewed"] == 1
    assert report["rows_skipped"] == 0


def test_ingest_substack_csv_apply_copies_raw_and_appends_manifest_event_transition_contact(
    retention_root: Path,
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "subscribers.csv"
    _write_csv(
        csv_path,
        [{"Subscriber Email": "stage2@example.com", "Subscription Status": "active"}],
        ["Subscriber Email", "Subscription Status"],
    )

    result = retention_cli.main(
        [
            "ingest-substack-csv",
            "--input",
            str(csv_path),
            "--apply",
        ]
    )

    assert result == 0
    state_root = retention_root / "data" / "state"
    source_batches = _read_jsonl(state_root / "source_batches.jsonl")
    events = _read_jsonl(state_root / "events.jsonl")
    transitions = _read_jsonl(state_root / "transitions.jsonl")
    contacts = _read_jsonl(state_root / "contacts.jsonl")

    assert len(source_batches) == 1
    assert len(events) == 1
    assert len(transitions) == 1
    assert len(contacts) == 1

    manifest = source_batches[0]
    raw_copy = retention_root / Path(manifest["raw_path"])
    assert raw_copy.exists()
    assert raw_copy.read_text(encoding="utf-8") == csv_path.read_text(encoding="utf-8")
    assert manifest["record_type"] == "source_batch"
    assert manifest["source"] == "substack"
    assert manifest["source_mode"] == "csv_export"


def test_ingest_substack_csv_raw_email_absent_from_state_logs(retention_root: Path, tmp_path: Path) -> None:
    csv_path = tmp_path / "subscribers.csv"
    _write_csv(
        csv_path,
        [{"Email": "privacy@example.com", "Status": "active"}],
        ["Email", "Status"],
    )

    result = retention_cli.main(
        [
            "ingest-substack-csv",
            "--input",
            str(csv_path),
            "--apply",
        ]
    )

    assert result == 0
    state_root = retention_root / "data" / "state"
    for name in ("events.jsonl", "transitions.jsonl", "contacts.jsonl", "content_dispatch.jsonl"):
        path = state_root / name
        if path.exists():
            assert "privacy@example.com" not in path.read_text(encoding="utf-8")


def test_ingest_substack_csv_missing_email_row_is_skipped(
    retention_root: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    csv_path = tmp_path / "subscribers.csv"
    _write_csv(
        csv_path,
        [{"Email": "", "Status": "active"}],
        ["Email", "Status"],
    )

    result = retention_cli.main(
        [
            "ingest-substack-csv",
            "--input",
            str(csv_path),
            "--dry-run",
        ]
    )

    assert result == 0
    report = json.loads(capsys.readouterr().out)
    assert report["rows_skipped"] == 1
    assert report["skipped_reasons"]["missing_email"] == 1


def test_ingest_substack_csv_invalid_email_row_is_skipped(
    retention_root: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    csv_path = tmp_path / "subscribers.csv"
    _write_csv(
        csv_path,
        [{"Email": "not-an-email", "Status": "active"}],
        ["Email", "Status"],
    )

    result = retention_cli.main(
        [
            "ingest-substack-csv",
            "--input",
            str(csv_path),
            "--dry-run",
        ]
    )

    assert result == 0
    report = json.loads(capsys.readouterr().out)
    assert report["rows_skipped"] == 1
    assert report["skipped_reasons"]["invalid_email"] == 1


def test_ingest_substack_csv_duplicate_import_does_not_duplicate_event_or_contact(
    retention_root: Path,
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "subscribers.csv"
    _write_csv(
        csv_path,
        [{"Email": "dup@example.com", "Status": "active"}],
        ["Email", "Status"],
    )

    first = retention_cli.main(
        [
            "ingest-substack-csv",
            "--input",
            str(csv_path),
            "--apply",
        ]
    )
    second = retention_cli.main(
        [
            "ingest-substack-csv",
            "--input",
            str(csv_path),
            "--apply",
        ]
    )

    assert first == 0
    assert second == 0
    state_root = retention_root / "data" / "state"
    assert len(_read_jsonl(state_root / "events.jsonl")) == 1
    assert len(_read_jsonl(state_root / "transitions.jsonl")) == 1
    assert len(_read_jsonl(state_root / "contacts.jsonl")) == 1
    assert len(_read_jsonl(state_root / "source_batches.jsonl")) == 2


def test_ingest_substack_csv_unsubscribed_row_becomes_suppressed(retention_root: Path, tmp_path: Path) -> None:
    csv_path = tmp_path / "subscribers.csv"
    _write_csv(
        csv_path,
        [{"Email": "gone@example.com", "Status": "unsubscribed"}],
        ["Email", "Status"],
    )

    result = retention_cli.main(
        [
            "ingest-substack-csv",
            "--input",
            str(csv_path),
            "--apply",
        ]
    )

    assert result == 0
    state_root = retention_root / "data" / "state"
    transitions = _read_jsonl(state_root / "transitions.jsonl")
    contacts = _read_jsonl(state_root / "contacts.jsonl")
    assert transitions[0]["to_state"] == "suppressed"
    assert contacts[0]["current_state"] == "suppressed"


def test_ingest_substack_csv_plan_dispatch_only_writes_when_allowed(retention_root: Path, tmp_path: Path) -> None:
    csv_path = tmp_path / "subscribers.csv"
    _write_csv(
        csv_path,
        [
            {"Email": "send@example.com", "Status": "active"},
            {"Email": "stop@example.com", "Status": "unsubscribed"},
        ],
        ["Email", "Status"],
    )

    result = retention_cli.main(
        [
            "ingest-substack-csv",
            "--input",
            str(csv_path),
            "--apply",
            "--plan-dispatch",
        ]
    )

    assert result == 0
    state_root = retention_root / "data" / "state"
    dispatches = _read_jsonl(state_root / "content_dispatch.jsonl")
    assert len(dispatches) == 1
    assert dispatches[0]["dispatch_type"] == "orientation_email"
