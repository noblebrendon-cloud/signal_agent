from __future__ import annotations

import json
from pathlib import Path

from signal_agent.corpus_import.cli import main
from signal_agent.corpus_import.hashing import canonical_json


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


def test_plan_extraction_cli_emits_one_canonical_json_object(
    completed_m1_run: Path,
    capsys,
) -> None:
    exit_code = main(
        [
            "corpus",
            "plan-chatgpt-extraction",
            "--run-root",
            str(completed_m1_run),
        ]
    )

    stdout = capsys.readouterr().out
    payload = json.loads(stdout)
    assert exit_code == 0
    assert payload["status"] == "ready"
    assert payload["operation"] == "plan_safe_extraction"
    assert stdout == canonical_json(payload) + "\n"
    assert not (completed_m1_run / ".m2_staging").exists()


def test_extract_cli_completes_milestone2(
    synthetic_run_factory,
    capsys,
) -> None:
    run_root = synthetic_run_factory.create([("conversations.json", "[]")])

    exit_code = main(
        [
            "extract-chatgpt-export",
            "--run-root",
            str(run_root),
        ]
    )

    stdout = capsys.readouterr().out
    payload = json.loads(stdout)
    assert exit_code == 0
    assert payload["status"] == "completed"
    assert payload["safe_resume_point"] == "milestone_3"
    assert stdout == canonical_json(payload) + "\n"


def test_extraction_cli_returns_one_for_operational_refusal(tmp_path: Path, capsys) -> None:
    exit_code = main(
        [
            "plan-chatgpt-extraction",
            "--run-root",
            str(tmp_path / "missing-run"),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["status"] == "refused"
    assert payload["errors"][0]["reason_code"] == "invalid_parent_receipt"


def test_extraction_cli_does_not_accept_arbitrary_source(
    completed_m1_run: Path,
    capsys,
) -> None:
    exit_code = main(
        [
            "extract-chatgpt-export",
            "--run-root",
            str(completed_m1_run),
            "--source",
            "other.zip",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["reason_code"] == "usage_error"


def test_cli_rejects_policy_weakening(completed_m1_run: Path, capsys) -> None:
    exit_code = main(
        [
            "plan-chatgpt-extraction",
            "--run-root",
            str(completed_m1_run),
            "--max-archive-members",
            "10001",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["reason_code"] == "usage_error"


def test_linkedin_relationship_slice_cli_is_local_and_non_authorizing(
    tmp_path: Path,
    capsys,
) -> None:
    repository_root = Path(__file__).resolve().parents[2]
    fake_repo = tmp_path / "repo"
    fake_repo.mkdir()
    key_dir = tmp_path / "outside-keys"
    key_dir.mkdir()
    key_file = key_dir / "cli.relationship-hmac.key"
    key_file.write_bytes(b"c" * 32)
    run_root = tmp_path / "linkedin-run"

    exit_code = main(
        [
            "corpus",
            "import-linkedin-relationships",
            "--source",
            str(repository_root / "tests/fixtures/linkedin_connections/Connections.csv"),
            "--run-root",
            str(run_root),
            "--hmac-key-file",
            str(key_file),
            "--hmac-key-id",
            "cli-key-v1",
            "--repo-root",
            str(fake_repo),
            "--content-library-root",
            str(repository_root / "docs/operator/content_library"),
        ]
    )

    stdout = capsys.readouterr().out
    payload = json.loads(stdout)
    assert exit_code == 0
    assert payload["status"] == "completed"
    assert payload["campaign_authorization"] == "none"
    assert payload["external_actions_performed"] is False
    assert stdout == canonical_json(payload) + "\n"
    assert (run_root / "05_receipts/run_manifest.json").is_file()
