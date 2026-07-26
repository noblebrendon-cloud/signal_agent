from __future__ import annotations

import json
from pathlib import Path

from signal_agent.corpus_import.cli import main


def test_cli_accepts_optional_corpus_prefix(valid_export_zip: Path, tmp_path: Path, capsys) -> None:
    run_root = tmp_path / "run-001"

    exit_code = main(
        [
            "corpus",
            "validate-chatgpt-export",
            "--source",
            str(valid_export_zip),
            "--run-root",
            str(run_root),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "completed"
    assert payload["operation"] == "validate_hash_preserve"


def test_cli_returns_one_for_validation_failure(tmp_path: Path, capsys) -> None:
    source = tmp_path / "missing.zip"

    exit_code = main(
        [
            "validate-chatgpt-export",
            "--source",
            str(source),
            "--run-root",
            str(tmp_path / "run-001"),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["status"] == "failed"
    assert payload["errors"][0]["reason_code"] == "source_not_found"


def test_cli_returns_two_for_usage_error(capsys) -> None:
    exit_code = main(["validate-chatgpt-export", "--source", "only-source.zip"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["reason_code"] == "usage_error"
