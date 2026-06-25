from __future__ import annotations

import json
from pathlib import Path

import pytest

from signal_agent.media_opportunities import cli


def test_cli_create_opportunity_writes_private_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("SIGNAL_AGENT_ROOT", str(tmp_path))

    exit_code = cli.main(
        [
            "create-opportunity",
            "--type",
            "guest_essay",
            "--invitation-text",
            "Could you write a guest essay about deterministic publishing?",
            "--url",
            "https://example.org/call",
            "--outlet",
            "Example Journal",
            "--topic",
            "Deterministic publishing",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["clean"] is True
    assert payload["opportunity"]["opportunity_id"].startswith("opp_")
    artifact_root = Path(payload["artifact_root"])
    assert artifact_root.exists()
    assert artifact_root.joinpath("response_draft.md").exists()
    assert artifact_root.resolve().is_relative_to(tmp_path.joinpath("data", "state", "media_opportunities").resolve())


def test_cli_rejects_invalid_transition(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("SIGNAL_AGENT_ROOT", str(tmp_path))

    assert cli.main(
        [
            "create-opportunity",
            "--type",
            "review",
            "--invitation-text",
            "Would you like this reviewed?",
        ]
    ) == 0
    created = json.loads(capsys.readouterr().out)
    opportunity_id = created["opportunity"]["opportunity_id"]

    exit_code = cli.main(
        [
            "transition",
            "--opportunity-id",
            opportunity_id,
            "--state",
            "approved_for_public_reference",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["clean"] is False
    assert "transition_not_allowed" in payload["error"]


def test_cli_ingest_gmail_label_dispatches_without_mutation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("SIGNAL_AGENT_ROOT", str(tmp_path))

    def fake_ingest(self: object, *, label: str, limit: int | None = None) -> dict:
        return {
            "clean": True,
            "label": label,
            "limit": limit,
            "created_count": 0,
            "skipped_count": 0,
            "manual_review_required": [],
            "errors": [],
        }

    monkeypatch.setattr(cli.MediaOpportunityService, "ingest_gmail_label", fake_ingest)

    exit_code = cli.main(["ingest-gmail-label", "--label", "Media Opportunity", "--limit", "5"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["label"] == "Media Opportunity"
    assert payload["limit"] == 5
