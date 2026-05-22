from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.reflective_pressure import cli


def _read_stdout_json(capsys: pytest.CaptureFixture[str]) -> dict:
    return json.loads(capsys.readouterr().out)


@pytest.fixture
def rp_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    monkeypatch.setenv("SIGNAL_AGENT_ROOT", str(root))
    return root


def test_cli_full_success_flow(rp_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    result = cli.main(
        [
            "rp-add-input",
            "--source-platform",
            "facebook_group",
            "--source-type",
            "comment",
            "--raw-text",
            "People keep turning every deeper discussion back into slogans instead of dealing with the actual pressure.",
            "--intended-spine",
            "reflective",
            "--tags",
            "slogans,pressure",
        ]
    )
    assert result == 0
    input_record = _read_stdout_json(capsys)

    result = cli.main(["rp-classify", "--input-id", input_record["input_id"]])
    assert result == 0
    classification = _read_stdout_json(capsys)
    assert classification["pressure_type"] == "shallow_certainty"

    result = cli.main(
        [
            "rp-generate-draft",
            "--input-id",
            input_record["input_id"],
            "--classification-id",
            classification["classification_id"],
            "--output-type",
            "reply",
            "--target-platform",
            "facebook_group",
        ]
    )
    assert result == 0
    draft = _read_stdout_json(capsys)
    assert draft["human_approved"] is False
    assert draft["published"] is False

    result = cli.main(
        [
            "rp-record-observation",
            "--input-id",
            input_record["input_id"],
            "--draft-id",
            draft["draft_id"],
            "--views",
            "1000",
            "--reactions",
            "25",
            "--comments",
            "18",
            "--shares",
            "4",
            "--saves",
            "0",
            "--profile-clicks",
            "3",
            "--recognition-events",
            "6",
            "--constructive-reply-ratio",
            "0.7",
            "--self-insertion-density",
            "0.5",
            "--delayed-recirculation",
            "0",
            "--contradiction-heat",
            "3",
        ]
    )
    assert result == 0
    observation = _read_stdout_json(capsys)
    assert observation["views"] == 1000
    assert observation["recognition_events"] == 6

    result = cli.main(["rp-summary", "--by", "pressure_type"])
    assert result == 0
    summary = _read_stdout_json(capsys)
    assert summary["counts"] == {"shallow_certainty": 1}

    result = cli.main(["rp-reconcile"])
    assert result == 0
    report = _read_stdout_json(capsys)
    assert report["clean"] is True
    assert report["summary"]["event_count"] == 4

    state_root = rp_root / "data" / "state"
    assert (state_root / "reflective_pressure_inputs.jsonl").exists()
    assert (state_root / "reflective_pressure_classifications.jsonl").exists()
    assert (state_root / "reflective_pressure_drafts.jsonl").exists()
    assert (state_root / "reflective_pressure_observations.jsonl").exists()
    assert (state_root / "reflective_pressure_events.jsonl").exists()


def test_cli_unknown_input_outputs_json_error(rp_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    result = cli.main(["rp-classify", "--input-id", "rpi_missing"])
    report = _read_stdout_json(capsys)

    assert result == 1
    assert report["clean"] is False
    assert report["error"] == "unknown_input:rpi_missing"
