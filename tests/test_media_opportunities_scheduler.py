from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from signal_agent.media_opportunities import cli
from signal_agent.media_opportunities.gmail import GoogleGmailReadonlySource
from signal_agent.media_opportunities.ledgers import MediaOpportunityLedgers
from signal_agent.media_opportunities.service import MediaOpportunityService


NOW = "2026-06-25T16:00:00Z"


def _clock() -> str:
    return NOW


class FakeGmailSource:
    def __init__(self, messages: list[dict[str, Any]]) -> None:
        self.messages = messages
        self.calls: list[tuple[str, int | None]] = []

    def messages_for_label(self, label: str, *, limit: int | None = None) -> list[dict[str, Any]]:
        self.calls.append((label, limit))
        selected = list(self.messages)
        if limit is not None:
            selected = selected[:limit]
        return selected


class FlakyGmailSource:
    def __init__(self, messages: list[dict[str, Any]]) -> None:
        self.messages = messages
        self.calls = 0

    def messages_for_label(self, label: str, *, limit: int | None = None) -> list[dict[str, Any]]:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("temporary Gmail read failure")
        return list(self.messages)


@pytest.fixture
def service(tmp_path: Path) -> MediaOpportunityService:
    return MediaOpportunityService(MediaOpportunityLedgers(tmp_path / "media", clock=_clock), clock=_clock)


def _message(**overrides: object) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": "msg-1",
        "message_id": "msg-1",
        "thread_id": "thread-1",
        "subject": "Interview request",
        "from": "Producer Person <producer@example.org>",
        "sender_name": "Producer Person",
        "text": "Would Brendon join our podcast for an interview?\nOutlet: Example Podcast",
    }
    payload.update(overrides)
    return payload


def _clean_result(**overrides: object) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "clean": True,
        "label": "Media Opportunity",
        "message_count": 0,
        "created_count": 0,
        "skipped_count": 0,
        "manual_review_count": 0,
        "error_count": 0,
        "created": [],
        "skipped": [],
        "manual_review_required": [],
        "errors": [],
        "configuration_error": False,
    }
    payload.update(overrides)
    return payload


def test_watcher_reuses_existing_ingestion_path(
    service: MediaOpportunityService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, object | None, int | None]] = []
    source = object()

    def fake_ingest(*, label: str, source: object | None = None, limit: int | None = None) -> dict[str, Any]:
        calls.append((label, source, limit))
        return _clean_result()

    monkeypatch.setattr(service, "ingest_gmail_label", fake_ingest)
    sleeps: list[float] = []
    lines: list[str] = []

    result = service.watch_gmail_label(
        label="Media Opportunity",
        source=source,
        limit=7,
        interval_minutes=15,
        max_cycles=2,
        sleep_fn=sleeps.append,
        print_fn=lines.append,
    )

    assert result["clean"] is True
    assert calls == [("Media Opportunity", source, 7), ("Media Opportunity", source, 7)]
    assert sleeps == [900]
    assert lines == [
        f"{NOW} created=0 skipped=0 manual_review=0 errors=0",
        f"{NOW} created=0 skipped=0 manual_review=0 errors=0",
    ]


def test_repeat_watcher_cycles_remain_idempotent(service: MediaOpportunityService) -> None:
    source = FakeGmailSource([_message()])

    result = service.watch_gmail_label(
        label="Media Opportunity",
        source=source,
        interval_minutes=15,
        max_cycles=2,
        sleep_fn=lambda _seconds: None,
    )

    assert result["cycle_count"] == 2
    assert result["cycles"][0]["created"] == 1
    assert result["cycles"][1]["created"] == 0
    assert result["cycles"][1]["skipped"] == 1
    assert len(service.opportunities()) == 1
    assert [record.current_state for record in service.opportunities()] == ["captured"]


def test_cli_rejects_watch_interval_below_minimum(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("SIGNAL_AGENT_ROOT", str(tmp_path))

    exit_code = cli.main(
        [
            "watch-gmail-label",
            "--label",
            "Media Opportunity",
            "--interval-minutes",
            "14",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["clean"] is False
    assert "min_15_minutes" in payload["error"]


def test_gmail_read_failure_is_ledgered_without_partial_records(service: MediaOpportunityService) -> None:
    source = FlakyGmailSource([_message()])

    result = service.watch_gmail_label(
        label="Media Opportunity",
        source=source,
        interval_minutes=15,
        max_cycles=2,
        sleep_fn=lambda _seconds: None,
    )

    assert result["cycles"][0]["errors"] == 1
    assert result["cycles"][0]["configuration_error"] is False
    assert result["cycles"][1]["created"] == 1
    assert len(service.opportunities()) == 1
    rows = service.ledgers.read("gmail_intake_audit")
    assert "read_failed" in [row["status"] for row in rows]
    assert rows[0]["record_type"] == "gmail_media_opportunity_intake_run"


def test_watcher_shutdown_does_not_corrupt_state(service: MediaOpportunityService) -> None:
    source = FakeGmailSource([_message()])

    def stop(_seconds: float) -> None:
        raise KeyboardInterrupt

    result = service.watch_gmail_label(
        label="Media Opportunity",
        source=source,
        interval_minutes=15,
        sleep_fn=stop,
    )

    assert result["interrupted"] is True
    assert result["cycle_count"] == 1
    assert len(service.opportunities()) == 1
    assert service.opportunities()[0].current_state == "captured"
    rows = service.ledgers.read("gmail_intake_audit")
    assert rows[-1]["record_type"] == "gmail_media_opportunity_watch"
    assert rows[-1]["status"] == "stopped_by_operator"


def test_powershell_helper_invokes_one_run_command() -> None:
    script_path = Path("scripts/run_media_opportunity_gmail_intake.ps1")
    script = script_path.read_text(encoding="utf-8")

    assert script_path.exists()
    assert "python -m signal_agent.media_opportunities.cli ingest-gmail-label --label $Label" in script
    assert "watch-gmail-label" not in script
    assert '$Label = "Media Opportunity"' in script
    assert "$LASTEXITCODE" in script


def test_gmail_adapter_exposes_no_mutation_methods() -> None:
    public_methods = {
        name
        for name, value in vars(GoogleGmailReadonlySource).items()
        if (callable(value) or isinstance(value, classmethod)) and not name.startswith("_")
    }

    assert public_methods == {"from_environment", "messages_for_label"}


def test_scheduler_behavior_does_not_write_or_reference_public_web_files(
    service: MediaOpportunityService,
) -> None:
    source = FakeGmailSource([_message()])

    result = service.watch_gmail_label(
        label="Media Opportunity",
        source=source,
        interval_minutes=15,
        max_cycles=1,
    )

    assert result["cycles"][0]["created"] == 1
    assert service.ledgers.read("public_reference_exports") == []
    for record in service.opportunities():
        for artifact_path in record.artifact_links.values():
            assert Path(artifact_path).resolve().is_relative_to(service.ledgers.root.resolve())
            assert "media_reference_candidate" not in Path(artifact_path).name

    script = Path("scripts/run_media_opportunity_gmail_intake.ps1").read_text(encoding="utf-8").lower()
    for public_marker in ("site_laviathon", "site_refactor_working", "github-pages", "brendonrcoleman.com"):
        assert public_marker not in script
