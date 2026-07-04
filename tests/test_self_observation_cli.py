from __future__ import annotations

import json
from pathlib import Path

from signal_agent.analytics.self_observation import main


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )


def test_cli_check_reports_readiness(tmp_path: Path, capsys) -> None:
    _write_jsonl(
        tmp_path / "data" / "state" / "transition_gate_events.jsonl",
        [
            {
                "event_type": "transition_attempt",
                "status": "allowed",
                "current_state": "captured",
                "attempted_state": "promoted",
            }
        ],
    )

    exit_code = main(["--repo-root", str(tmp_path), "--check"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["primary_input_available"] is True


def test_cli_writes_json_and_markdown_reports(tmp_path: Path) -> None:
    _write_jsonl(
        tmp_path / "data" / "state" / "transition_gate_events.jsonl",
        [
            {
                "event_type": "transition_attempt",
                "status": "allowed",
                "current_state": "captured",
                "attempted_state": "promoted",
            }
        ],
    )
    json_output = tmp_path / "data" / "analytics" / "self_observation_report.json"
    markdown_output = tmp_path / "data" / "analytics" / "self_observation_report.md"

    exit_code = main(
        [
            "--repo-root",
            str(tmp_path),
            "--json-output",
            str(json_output),
            "--markdown-output",
            str(markdown_output),
        ]
    )

    assert exit_code == 0
    assert json_output.exists()
    assert markdown_output.exists()
    payload = json.loads(json_output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "self_observation_report.v1"


def test_cli_relative_output_resolves_inside_repo_root(tmp_path: Path) -> None:
    repo_root = tmp_path / ".tmp-observation-proof"
    _write_jsonl(
        repo_root / "data" / "state" / "transition_gate_events.jsonl",
        [
            {
                "event_type": "transition_attempt",
                "status": "allowed",
                "current_state": "captured",
                "attempted_state": "promoted",
            }
        ],
    )

    exit_code = main(
        [
            "--repo-root",
            str(repo_root),
            "--json-output",
            "data/analytics/report.json",
        ]
    )

    assert exit_code == 0
    assert (repo_root / "data" / "analytics" / "report.json").exists()
    assert not (tmp_path / "data" / "analytics" / "report.json").exists()


def test_cli_absolute_output_remains_absolute(tmp_path: Path) -> None:
    repo_root = tmp_path / ".tmp-observation-proof"
    _write_jsonl(
        repo_root / "data" / "state" / "transition_gate_events.jsonl",
        [
            {
                "event_type": "transition_attempt",
                "status": "allowed",
                "current_state": "captured",
                "attempted_state": "promoted",
            }
        ],
    )
    absolute_output = tmp_path / "outside" / "report.json"

    exit_code = main(
        [
            "--repo-root",
            str(repo_root),
            "--json-output",
            str(absolute_output),
        ]
    )

    assert exit_code == 0
    assert absolute_output.exists()
    assert not (repo_root / "outside" / "report.json").exists()


def test_cli_does_not_write_when_primary_inputs_missing(tmp_path: Path, capsys) -> None:
    json_output = tmp_path / "data" / "analytics" / "self_observation_report.json"

    exit_code = main(
        [
            "--repo-root",
            str(tmp_path),
            "--json-output",
            str(json_output),
        ]
    )

    assert exit_code == 2
    assert not json_output.exists()
    assert "primary inputs" in capsys.readouterr().err


def test_cli_rejects_canonical_output_path(tmp_path: Path, capsys) -> None:
    _write_jsonl(
        tmp_path / "data" / "state" / "transition_gate_events.jsonl",
        [
            {
                "event_type": "transition_attempt",
                "status": "allowed",
                "current_state": "captured",
                "attempted_state": "promoted",
            }
        ],
    )

    exit_code = main(
        [
            "--repo-root",
            str(tmp_path),
            "--json-output",
            str(tmp_path / "data" / "state" / "bad.json"),
        ]
    )

    assert exit_code == 2
    assert "not written" in capsys.readouterr().err


def test_cli_rejects_canonical_output_roots(tmp_path: Path, capsys) -> None:
    repo_root = tmp_path / ".tmp-observation-proof"
    _write_jsonl(
        repo_root / "data" / "state" / "transition_gate_events.jsonl",
        [
            {
                "event_type": "transition_attempt",
                "status": "allowed",
                "current_state": "captured",
                "attempted_state": "promoted",
            }
        ],
    )

    forbidden_outputs = [
        "data/state/report.json",
        "config/report.json",
        "config/policies/report.json",
        "signal_agent/report.json",
        "app/report.json",
        "governance/report.json",
        "constraints/report.json",
        "formal_governance/report.json",
    ]
    for output_path in forbidden_outputs:
        exit_code = main(
            [
                "--repo-root",
                str(repo_root),
                "--json-output",
                output_path,
            ]
        )

        assert exit_code == 2
        assert not (repo_root / output_path).exists()

    assert "not written" in capsys.readouterr().err
