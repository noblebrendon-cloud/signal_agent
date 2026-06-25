from __future__ import annotations

import json
import os
import shutil
import socket
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

import pytest

from app.letters_of_light import subscribers
from app.letters_of_light.subscribers import core
from app.retention.identity import event_id_from_material
from app.retention.jsonl_store import append_record, ensure_required_state_files
from app.retention.models import PUBLIC_WEBSITE_SOURCE, build_contact_snapshot
from app.retention.transitions import evaluate_transition, load_latest_contact_snapshot


def _external_temp_parent() -> Path:
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Temp",
        Path(os.environ.get("USERPROFILE", "")) / "AppData" / "Local" / "Temp",
        Path.home() / ".codex_tmp",
    ]
    blocked_roots = [
        Path("E:/signal_agent").resolve(strict=False),
        Path("E:/githubpage").resolve(strict=False),
    ]
    for candidate in candidates:
        if not str(candidate).strip():
            continue
        resolved = candidate.resolve(strict=False)
        if any(_is_relative_to(resolved, root) for root in blocked_roots):
            continue
        resolved.mkdir(parents=True, exist_ok=True)
        return resolved
    raise RuntimeError("external temp parent unavailable")


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


@pytest.fixture
def external_tmp_path() -> Path:
    root = Path(tempfile.mkdtemp(prefix="lol_delivery_preparation_tests_", dir=str(_external_temp_parent())))
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _subscriber_config(root: Path) -> core.SubscriberConfig:
    data_root = root / "private_subscriber_data"
    return core.resolve_subscriber_config(
        {
            core.DATA_ROOT_ENV: str(data_root),
            core.SUBSCRIBER_DB_ENV: str(data_root / "subscribers.sqlite3"),
        }
    )


def _release_dir(repo_root: Path, letter_id: str) -> Path:
    return repo_root / "data" / "state" / "letters_of_light" / letter_id


def _write_release(
    repo_root: Path,
    *,
    letter_id: str = "weekly-light-001",
    approved: bool = True,
    release_state: str = "exported",
    campaign_id: str = "lol-weekly-light-001",
    manifest_letter_id: str | None = None,
    manifest_campaign_id: str | None = None,
) -> None:
    release_dir = _release_dir(repo_root, letter_id)
    export_dir = release_dir / "release_export"
    export_dir.mkdir(parents=True, exist_ok=True)
    canonical_url = f"https://brendonrcoleman.com/letters-of-light/{letter_id}/"
    release = {
        "letter_id": letter_id,
        "campaign_id": campaign_id,
        "release_state": release_state,
        "approved": approved,
        "canonical_url": canonical_url,
        "title": "Weekly Light",
    }
    manifest = {
        "letter_id": manifest_letter_id if manifest_letter_id is not None else letter_id,
        "campaign_id": manifest_campaign_id if manifest_campaign_id is not None else campaign_id,
        "canonical_url": canonical_url,
        "assets": [],
    }
    (release_dir / "release.json").write_text(json.dumps(release, sort_keys=True), encoding="utf-8")
    (export_dir / "asset_manifest.json").write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")


def _db_rows(config: core.SubscriberConfig) -> list[sqlite3.Row]:
    conn = sqlite3.connect(config.subscriber_db)
    conn.row_factory = sqlite3.Row
    try:
        return list(conn.execute("SELECT * FROM subscribers ORDER BY created_at, subscriber_id"))
    finally:
        conn.close()


def _set_private_status(config: core.SubscriberConfig, subscriber_id: str, status: str, consent_version: int) -> None:
    conn = sqlite3.connect(config.subscriber_db)
    try:
        conn.execute(
            """
            UPDATE subscribers
            SET status = ?,
                consent_version = ?,
                updated_at = '2026-01-01T00:00:00Z',
                confirmed_at = CASE WHEN ? = 'confirmed' THEN '2026-01-01T00:00:00Z' ELSE confirmed_at END
            WHERE subscriber_id = ?
            """,
            (status, consent_version, status, subscriber_id),
        )
        conn.commit()
    finally:
        conn.close()


def _append_private_retention_event(
    *,
    repo_root: Path,
    row: sqlite3.Row,
    event_type: str,
    consent_status: str,
    consent_version: int,
) -> None:
    identifier_hash = str(row["contact_identifier_hash"])
    contact_id = str(row["contact_id"])
    event = {
        "record_type": "canonical_event",
        "schema_version": "1.0",
        "event_id": event_id_from_material(
            event_type=event_type,
            source=PUBLIC_WEBSITE_SOURCE,
            identifier_hash_value=identifier_hash,
            consent_status=consent_status,
            event_key=f"{row['subscriber_id']}:{consent_version}:delivery-preparation-test",
        ),
        "event_type": event_type,
        "source": PUBLIC_WEBSITE_SOURCE,
        "source_mode": "test_private_subscriber_state",
        "scope": "contact",
        "contact_id": contact_id,
        "identifier_kind": core.PRIVATE_IDENTIFIER_KIND,
        "identifier_hash": identifier_hash,
        "actor": {
            "contact_id": contact_id,
            "identifier_kind": core.PRIVATE_IDENTIFIER_KIND,
            "identifier_hash": identifier_hash,
            "linkage_status": "private_mapping",
        },
        "consent": {
            "email_marketing_status": consent_status,
            "version": consent_version,
        },
    }
    previous_snapshot = load_latest_contact_snapshot(contact_id, repo_root=repo_root)
    transition = evaluate_transition(event, previous_snapshot=previous_snapshot)
    snapshot = build_contact_snapshot(previous_snapshot=previous_snapshot, event=event, transition=transition)
    assert snapshot is not None
    ensure_required_state_files(repo_root=repo_root)
    append_record("events.jsonl", event, repo_root=repo_root)
    append_record("transitions.jsonl", transition, repo_root=repo_root)
    append_record("contacts.jsonl", snapshot, repo_root=repo_root)


def _ledger_text(repo_root: Path) -> str:
    state_root = repo_root / "data" / "state"
    if not state_root.exists():
        return ""
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted(state_root.glob("*.jsonl")))


def _prepare(repo_root: Path, config: core.SubscriberConfig, letter_id: str = "weekly-light-001") -> dict[str, Any]:
    return subscribers.prepare_release_delivery(
        letter_id,
        subscriber_config=config,
        retention_repo_root=repo_root,
        release_repo_root=repo_root,
    )


def test_approved_release_with_confirmed_audience_produces_deterministic_no_send_result(
    external_tmp_path: Path,
) -> None:
    repo_root = external_tmp_path / "retention_repo"
    config = _subscriber_config(external_tmp_path)
    _write_release(repo_root)
    signup = core.request_signup("eligible-delivery@example.com", config=config)
    assert signup.token is not None
    confirmed = core.confirm_signup(signup.token, retention_repo_root=repo_root, config=config)

    first = _prepare(repo_root, config)
    second = _prepare(repo_root, config)

    assert first == second
    assert first["record_type"] == "letters_of_light_delivery_preparation"
    assert first["adapter"] == "local-noop"
    assert first["sent"] is False
    assert first["no_network"] is True
    assert first["external_action_allowed"] is False
    assert first["provider_payload_created"] is False
    assert first["total_private_count"] == 1
    assert first["confirmed_private_count"] == 1
    assert first["candidate_count"] == 1
    assert first["excluded_count"] == 0

    candidate = first["candidates"][0]
    assert candidate["contact_id"] == confirmed.contact_id
    assert candidate["status"] == "prepared_no_send"
    assert candidate["retention_dispatch"]["decision"] == "planned"
    assert candidate["retention_dispatch"]["channel"] == "email"
    assert candidate["consent_basis"]["email_marketing_status"] == "opted_in"
    assert candidate["provider_payload_created"] is False


def test_unapproved_missing_malformed_and_ambiguous_releases_are_rejected(
    external_tmp_path: Path,
) -> None:
    repo_root = external_tmp_path / "retention_repo"
    config = _subscriber_config(external_tmp_path)

    with pytest.raises(subscribers.DeliveryPreparationError, match="release_input_missing"):
        _prepare(repo_root, config, letter_id="missing-release")

    _write_release(repo_root, approved=False)
    with pytest.raises(subscribers.DeliveryPreparationError, match="release_not_approved"):
        _prepare(repo_root, config)

    malformed_id = "malformed-release"
    malformed_dir = _release_dir(repo_root, malformed_id)
    malformed_dir.mkdir(parents=True, exist_ok=True)
    (malformed_dir / "release.json").write_text("{", encoding="utf-8")
    with pytest.raises(subscribers.DeliveryPreparationError, match="release_input_malformed"):
        _prepare(repo_root, config, letter_id=malformed_id)

    ambiguous_id = "ambiguous-release"
    _write_release(repo_root, letter_id=ambiguous_id, manifest_letter_id="different-release")
    with pytest.raises(subscribers.DeliveryPreparationError, match="release_input_ambiguous"):
        _prepare(repo_root, config, letter_id=ambiguous_id)


def test_pending_and_unconfirmed_subscribers_are_excluded_without_retention_consent(
    external_tmp_path: Path,
) -> None:
    repo_root = external_tmp_path / "retention_repo"
    config = _subscriber_config(external_tmp_path)
    _write_release(repo_root)
    core.request_signup("pending-delivery@example.com", config=config)

    result = _prepare(repo_root, config)

    assert result["candidate_count"] == 0
    assert result["total_private_count"] == 1
    assert result["excluded_count"] == 1
    assert result["exclusions"][0]["reason_code"] == "private_status_not_confirmed"
    assert not _ledger_text(repo_root)


def test_unsubscribed_and_suppressed_contacts_are_excluded(
    external_tmp_path: Path,
) -> None:
    repo_root = external_tmp_path / "retention_repo"
    config = _subscriber_config(external_tmp_path)
    _write_release(repo_root)

    unsub_signup = core.request_signup("unsubscribed-delivery@example.com", config=config)
    assert unsub_signup.token is not None
    unsub_confirmed = core.confirm_signup(unsub_signup.token, retention_repo_root=repo_root, config=config)
    core.unsubscribe(unsub_confirmed.unsubscribe_token, retention_repo_root=repo_root, config=config)

    suppressed_signup = core.request_signup("suppressed-delivery@example.com", config=config)
    assert suppressed_signup.token is not None
    core.confirm_signup(suppressed_signup.token, retention_repo_root=repo_root, config=config)
    suppressed_row = [row for row in _db_rows(config) if row["email"] == "suppressed-delivery@example.com"][0]
    _append_private_retention_event(
        repo_root=repo_root,
        row=suppressed_row,
        event_type="unsubscribe",
        consent_status="opted_out",
        consent_version=2,
    )

    result = _prepare(repo_root, config)

    assert result["candidate_count"] == 0
    reason_codes = {item["reason_code"] for item in result["exclusions"]}
    assert "private_status_not_confirmed" in reason_codes
    assert "retention_dispatch_ineligible" in reason_codes
    suppressed_exclusion = [item for item in result["exclusions"] if item["reason_code"] == "retention_dispatch_ineligible"][0]
    assert suppressed_exclusion["current_state"] == "suppressed"
    assert suppressed_exclusion["consent_status"] == "opted_out"


def test_public_website_provenance_alone_never_creates_delivery_eligibility(
    external_tmp_path: Path,
) -> None:
    repo_root = external_tmp_path / "retention_repo"
    config = _subscriber_config(external_tmp_path)
    _write_release(repo_root)
    signup = core.request_signup("provenance-only@example.com", config=config)
    row = _db_rows(config)[0]
    _set_private_status(config, str(row["subscriber_id"]), "confirmed", consent_version=0)
    _append_private_retention_event(
        repo_root=repo_root,
        row=row,
        event_type="contact_seeded",
        consent_status="unknown",
        consent_version=0,
    )

    result = _prepare(repo_root, config)

    assert signup.duplicate is False
    assert result["candidate_count"] == 0
    assert result["confirmed_private_count"] == 1
    assert result["exclusions"][0]["reason_code"] == "retention_dispatch_ineligible"
    assert result["exclusions"][0]["current_state"] == "aware"
    assert result["exclusions"][0]["consent_status"] == "unknown"


def test_empty_audience_is_a_safe_no_send_result(external_tmp_path: Path) -> None:
    repo_root = external_tmp_path / "retention_repo"
    config = _subscriber_config(external_tmp_path)
    _write_release(repo_root)

    result = _prepare(repo_root, config)

    assert result["clean"] is True
    assert result["total_private_count"] == 0
    assert result["candidate_count"] == 0
    assert result["excluded_count"] == 0
    assert result["candidates"] == []
    assert result["exclusions"] == []


def test_delivery_preparation_outputs_logs_and_retention_are_redacted(
    external_tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    repo_root = external_tmp_path / "retention_repo"
    config = _subscriber_config(external_tmp_path)
    _write_release(repo_root)
    email = "redaction-delivery@example.com"
    signup = core.request_signup(email, config=config)
    assert signup.token is not None
    confirmed = core.confirm_signup(signup.token, retention_repo_root=repo_root, config=config)

    result = _prepare(repo_root, config)

    combined_text = "\n".join(
        [
            json.dumps(result, sort_keys=True),
            _ledger_text(repo_root),
            caplog.text,
        ]
    )
    assert email not in combined_text
    assert signup.token not in combined_text
    assert confirmed.unsubscribe_token not in combined_text
    assert core.hash_token(signup.token) not in combined_text
    assert core.hash_token(confirmed.unsubscribe_token) not in combined_text
    assert str(config.subscriber_db) not in combined_text
    assert str(config.data_root) not in combined_text
    assert "provider_payload" not in json.dumps(result["candidates"], sort_keys=True).replace("provider_payload_created", "")


def test_no_network_is_used_during_delivery_preparation(
    external_tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = external_tmp_path / "retention_repo"
    config = _subscriber_config(external_tmp_path)
    _write_release(repo_root)
    signup = core.request_signup("network-guard-delivery@example.com", config=config)
    assert signup.token is not None
    core.confirm_signup(signup.token, retention_repo_root=repo_root, config=config)
    calls: list[object] = []

    def forbidden_network(*args: object, **kwargs: object) -> object:
        calls.append((args, kwargs))
        raise AssertionError("network access is out of scope")

    monkeypatch.setattr(socket, "create_connection", forbidden_network)
    monkeypatch.setattr(socket, "socket", forbidden_network)

    result = _prepare(repo_root, config)

    assert result["candidate_count"] == 1
    assert calls == []
