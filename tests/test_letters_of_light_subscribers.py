from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.letters_of_light.subscribers import core as subscribers
from app.retention.dispatch import plan_dispatch
from app.retention.models import build_contact_seed_event, build_contact_snapshot
from app.retention.transitions import evaluate_transition


def _external_temp_parent() -> Path:
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Temp",
        Path(os.environ.get("USERPROFILE", "")) / "AppData" / "Local" / "Temp",
        Path.home() / ".codex_tmp",
    ]
    blocked_root = Path("E:/signal_agent").resolve(strict=False)
    for candidate in candidates:
        if not str(candidate).strip():
            continue
        resolved = candidate.resolve(strict=False)
        try:
            resolved.relative_to(blocked_root)
            continue
        except ValueError:
            resolved.mkdir(parents=True, exist_ok=True)
            return resolved
    raise RuntimeError("external temp parent unavailable")


@pytest.fixture
def external_tmp_path() -> Path:
    root = Path(tempfile.mkdtemp(prefix="lol_subscriber_tests_", dir=str(_external_temp_parent())))
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


@pytest.fixture
def subscriber_paths(monkeypatch: pytest.MonkeyPatch, external_tmp_path: Path) -> dict[str, Path]:
    data_root = external_tmp_path / "private_subscriber_data"
    db_path = data_root / "subscribers.sqlite3"
    retention_root = external_tmp_path / "retention_repo"
    monkeypatch.setenv(subscribers.DATA_ROOT_ENV, str(data_root))
    monkeypatch.setenv(subscribers.SUBSCRIBER_DB_ENV, str(db_path))
    return {"data_root": data_root, "db_path": db_path, "retention_root": retention_root}


def _db_rows(db_path: Path) -> list[sqlite3.Row]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return list(conn.execute("SELECT * FROM subscribers ORDER BY created_at, subscriber_id"))
    finally:
        conn.close()


def _ledger_rows(retention_root: Path, ledger_name: str) -> list[dict]:
    path = retention_root / "data" / "state" / ledger_name
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _ledger_text(retention_root: Path) -> str:
    state_root = retention_root / "data" / "state"
    if not state_root.exists():
        return ""
    chunks = []
    for path in sorted(state_root.glob("*.jsonl")):
        chunks.append(path.read_text(encoding="utf-8"))
    return "\n".join(chunks)


def test_pending_signup_is_private_only(subscriber_paths: dict[str, Path]) -> None:
    result = subscribers.request_signup(" Reader@Example.COM ")

    assert result.status == "pending"
    assert result.token
    assert subscribers.normalize_email(" Reader@Example.COM ") == "reader@example.com"
    assert not (subscriber_paths["retention_root"] / "data" / "state").exists()

    rows = _db_rows(subscriber_paths["db_path"])
    assert len(rows) == 1
    row = rows[0]
    assert row["email"] == "reader@example.com"
    assert row["status"] == "pending"
    assert row["consent_version"] == 0
    assert row["pending_token_hash"].startswith("sha256:")
    assert result.token not in subscriber_paths["db_path"].read_text(encoding="utf-8", errors="ignore")


def test_confirmation_creates_opted_in_retention_state_exactly_once(subscriber_paths: dict[str, Path]) -> None:
    signup = subscribers.request_signup("confirm@example.com")
    assert signup.token is not None

    confirmed = subscribers.confirm_signup(signup.token, retention_repo_root=subscriber_paths["retention_root"])

    assert confirmed.status == "subscribed"
    events = _ledger_rows(subscriber_paths["retention_root"], "events.jsonl")
    transitions = _ledger_rows(subscriber_paths["retention_root"], "transitions.jsonl")
    contacts = _ledger_rows(subscriber_paths["retention_root"], "contacts.jsonl")
    assert len(events) == 1
    assert len(transitions) == 1
    assert len(contacts) == 1
    assert events[0]["event_type"] == "contact_seeded"
    assert events[0]["source"] == "public_website"
    assert events[0]["identifier_kind"] == "private_contact_ref"
    assert events[0]["consent"]["email_marketing_status"] == "opted_in"
    assert contacts[0]["current_state"] == "subscribed"
    assert contacts[0]["dispatch_policy"]["allow_email"] is True

    with pytest.raises(subscribers.SubscriberCoreError, match="confirmation_token_not_active"):
        subscribers.confirm_signup(signup.token, retention_repo_root=subscriber_paths["retention_root"])
    assert len(_ledger_rows(subscriber_paths["retention_root"], "events.jsonl")) == 1

    db_row = _db_rows(subscriber_paths["db_path"])[0]
    assert db_row["status"] == "confirmed"
    assert db_row["consent_version"] == 1
    assert db_row["pending_token_used_at"]
    assert db_row["unsubscribe_token_hash"].startswith("sha256:")


def test_duplicate_signup_is_idempotent(subscriber_paths: dict[str, Path]) -> None:
    first = subscribers.request_signup("duplicate@example.com")
    second = subscribers.request_signup(" DUPLICATE@example.com ")

    assert second.duplicate is True
    assert second.status == "pending"
    assert second.subscriber_id == first.subscriber_id
    assert second.token is None
    rows = _db_rows(subscriber_paths["db_path"])
    assert len(rows) == 1
    assert not (subscriber_paths["retention_root"] / "data" / "state").exists()


def test_expired_invalid_and_reused_confirmation_tokens_fail_closed(subscriber_paths: dict[str, Path]) -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    signup = subscribers.request_signup("tokens@example.com", now=now, token_ttl=timedelta(seconds=1))
    assert signup.token is not None

    with pytest.raises(subscribers.SubscriberCoreError, match="confirmation_token_invalid"):
        subscribers.confirm_signup("not-a-real-token", retention_repo_root=subscriber_paths["retention_root"])
    with pytest.raises(subscribers.SubscriberCoreError, match="confirmation_token_expired"):
        subscribers.confirm_signup(
            signup.token,
            now=now + timedelta(seconds=2),
            retention_repo_root=subscriber_paths["retention_root"],
        )
    assert _ledger_rows(subscriber_paths["retention_root"], "events.jsonl") == []
    assert _db_rows(subscriber_paths["db_path"])[0]["status"] == "pending"

    fresh = subscribers.request_signup("fresh-token@example.com", now=now)
    assert fresh.token is not None
    subscribers.confirm_signup(
        fresh.token,
        now=now + timedelta(seconds=1),
        retention_repo_root=subscriber_paths["retention_root"],
    )
    with pytest.raises(subscribers.SubscriberCoreError, match="confirmation_token_not_active"):
        subscribers.confirm_signup(
            fresh.token,
            now=now + timedelta(seconds=2),
            retention_repo_root=subscriber_paths["retention_root"],
        )
    assert len(_ledger_rows(subscriber_paths["retention_root"], "events.jsonl")) == 1


def test_confirmation_retention_write_failure_leaves_private_state_pending(
    monkeypatch: pytest.MonkeyPatch,
    subscriber_paths: dict[str, Path],
) -> None:
    signup = subscribers.request_signup("retention-failure@example.com")
    assert signup.token is not None

    def fail_append(*args: object, **kwargs: object) -> dict:
        raise OSError("simulated append failure")

    monkeypatch.setattr(subscribers, "append_record", fail_append)

    with pytest.raises(subscribers.SubscriberCoreError, match="retention_write_failed"):
        subscribers.confirm_signup(signup.token, retention_repo_root=subscriber_paths["retention_root"])

    row = _db_rows(subscriber_paths["db_path"])[0]
    assert row["status"] == "pending"
    assert row["pending_token_used_at"] is None


def test_unsubscribe_produces_suppression_and_blocks_eligibility(subscriber_paths: dict[str, Path]) -> None:
    signup = subscribers.request_signup("unsubscribe@example.com")
    assert signup.token is not None
    confirmed = subscribers.confirm_signup(signup.token, retention_repo_root=subscriber_paths["retention_root"])

    unsubscribed = subscribers.unsubscribe(
        confirmed.unsubscribe_token,
        retention_repo_root=subscriber_paths["retention_root"],
    )

    assert unsubscribed.status == "suppressed"
    assert unsubscribed.dispatch_blocked is True
    events = _ledger_rows(subscriber_paths["retention_root"], "events.jsonl")
    contacts = _ledger_rows(subscriber_paths["retention_root"], "contacts.jsonl")
    assert [event["event_type"] for event in events] == ["contact_seeded", "unsubscribe"]
    assert contacts[-1]["current_state"] == "suppressed"
    assert plan_dispatch(contacts[-1], contact_id=contacts[-1]["contact_id"])["decision"] == "blocked"

    with pytest.raises(subscribers.SubscriberCoreError, match="unsubscribe_token_not_active"):
        subscribers.unsubscribe(confirmed.unsubscribe_token, retention_repo_root=subscriber_paths["retention_root"])
    assert len(_ledger_rows(subscriber_paths["retention_root"], "events.jsonl")) == 2

    row = _db_rows(subscriber_paths["db_path"])[0]
    assert row["status"] == "unsubscribed"
    assert row["consent_version"] == 2


def test_invalid_private_path_configuration_fails_closed(external_tmp_path: Path) -> None:
    blocked_repo_env = {
        subscribers.DATA_ROOT_ENV: str(Path("E:/signal_agent") / "private_subscriber_data"),
        subscribers.SUBSCRIBER_DB_ENV: "subscribers.sqlite3",
    }
    with pytest.raises(subscribers.SubscriberCoreError, match="subscriber_data_root_not_private"):
        subscribers.resolve_subscriber_config(blocked_repo_env)

    git_root = external_tmp_path / "private_git_root"
    git_root.mkdir()
    (git_root / ".git").mkdir()
    git_env = {
        subscribers.DATA_ROOT_ENV: str(git_root / "subscriber_data"),
        subscribers.SUBSCRIBER_DB_ENV: "subscribers.sqlite3",
    }
    with pytest.raises(subscribers.SubscriberCoreError, match="subscriber_data_root_not_private"):
        subscribers.resolve_subscriber_config(git_env)

    public_env = {
        subscribers.DATA_ROOT_ENV: str(external_tmp_path / "public" / "subscriber_data"),
        subscribers.SUBSCRIBER_DB_ENV: "subscribers.sqlite3",
    }
    with pytest.raises(subscribers.SubscriberCoreError, match="subscriber_data_root_not_private"):
        subscribers.resolve_subscriber_config(public_env)

    outside_db_env = {
        subscribers.DATA_ROOT_ENV: str(external_tmp_path / "private_data"),
        subscribers.SUBSCRIBER_DB_ENV: str(external_tmp_path / "other" / "subscribers.sqlite3"),
    }
    with pytest.raises(subscribers.SubscriberCoreError, match="subscriber_db_outside_data_root"):
        subscribers.resolve_subscriber_config(outside_db_env)


def test_raw_email_and_token_material_stay_out_of_retention_ledgers_and_errors(
    subscriber_paths: dict[str, Path],
) -> None:
    email = "private-ledger-check@example.com"
    signup = subscribers.request_signup(email)
    assert signup.token is not None
    confirmed = subscribers.confirm_signup(signup.token, retention_repo_root=subscriber_paths["retention_root"])
    subscribers.unsubscribe(confirmed.unsubscribe_token, retention_repo_root=subscriber_paths["retention_root"])

    ledger_text = _ledger_text(subscriber_paths["retention_root"])
    assert email not in ledger_text
    assert signup.token not in ledger_text
    assert confirmed.unsubscribe_token not in ledger_text
    assert subscribers.hash_token(signup.token) not in ledger_text
    assert subscribers.hash_token(confirmed.unsubscribe_token) not in ledger_text
    assert "@" not in ledger_text

    for call in (
        lambda: subscribers.normalize_email("bad-private-ledger-check@example"),
        lambda: subscribers.confirm_signup("plain-token", retention_repo_root=subscriber_paths["retention_root"]),
        lambda: subscribers.resolve_subscriber_config(
            {
                subscribers.DATA_ROOT_ENV: str(Path("E:/githubpage") / "private"),
                subscribers.SUBSCRIBER_DB_ENV: "subscribers.sqlite3",
            }
        ),
    ):
        with pytest.raises(subscribers.SubscriberCoreError) as exc_info:
            call()
        rendered = str(exc_info.value)
        assert "private-ledger-check@example.com" not in rendered
        assert "plain-token" not in rendered
        assert "githubpage" not in rendered.lower()


def test_existing_retention_behavior_remains_unchanged() -> None:
    event = build_contact_seed_event(
        source="substack",
        identifier_kind="email",
        identifier_value="existing-retention@example.com",
        consent_status="opted_in",
    )
    transition = evaluate_transition(event, previous_snapshot=None)
    snapshot = build_contact_snapshot(previous_snapshot=None, event=event, transition=transition)

    assert snapshot is not None
    assert transition["to_state"] == "subscribed"
    assert snapshot["dispatch_policy"]["allow_email"] is True
    assert plan_dispatch(snapshot, contact_id=snapshot["contact_id"])["dispatch_type"] == "orientation_email"
