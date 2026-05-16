from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.spine_observability import cli
from app.spine_observability.laviathon_store import LAVIATHON_OBSERVATIONS_FILE


def _state_path(root: Path) -> Path:
    return root / "data" / "state" / LAVIATHON_OBSERVATIONS_FILE


def _base_cli_args() -> list[str]:
    return [
        "laviathon-add-observation",
        "--created-at",
        "2026-05-15T12:00:00Z",
        "--source-context",
        "local_cli_test",
        "--spine-target",
        "governance",
        "--observation-type",
        "critique",
        "--claim",
        "The CLI appends validated observations only.",
        "--evidence",
        "The command delegates to the local Laviathon store.",
        "--recommendation",
        "Keep external action disabled.",
        "--public-safe",
        "false",
    ]


@pytest.fixture
def laviathon_cli_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    monkeypatch.setenv("SIGNAL_AGENT_ROOT", str(root))
    return root


def test_laviathon_add_observation_appends_valid_observation(
    laviathon_cli_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = cli.main(_base_cli_args())

    assert result == 0
    output = json.loads(capsys.readouterr().out)
    assert output["observation_id"].startswith("lob_")
    assert output["external_action_allowed"] is False
    assert output["review_status"] == "pending"
    assert output["requires_human_review"] is True
    rows = _state_path(laviathon_cli_root).read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1
    assert json.loads(rows[0]) == output


def test_laviathon_list_observations_returns_appended_observations(
    laviathon_cli_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del laviathon_cli_root
    assert cli.main(_base_cli_args()) == 0
    appended = json.loads(capsys.readouterr().out)

    assert cli.main(["laviathon-list-observations"]) == 0
    listed = json.loads(capsys.readouterr().out)

    assert listed == {"observations": [appended]}


def test_laviathon_review_candidates_returns_pending_human_review_observations(
    laviathon_cli_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del laviathon_cli_root
    assert cli.main(_base_cli_args()) == 0
    appended = json.loads(capsys.readouterr().out)

    assert cli.main(["laviathon-review-candidates"]) == 0
    candidates = json.loads(capsys.readouterr().out)

    assert candidates == {"review_candidates": [appended]}


def test_laviathon_add_observation_rejects_external_action_true(
    laviathon_cli_root: Path,
) -> None:
    args = _base_cli_args() + ["--external-action-allowed", "true"]

    with pytest.raises(ValueError, match="external_action_not_allowed"):
        cli.main(args)

    assert not _state_path(laviathon_cli_root).exists()


def test_laviathon_public_post_candidate_requires_human_review(
    laviathon_cli_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del laviathon_cli_root
    args = _base_cli_args()
    args[args.index("critique")] = "public_post_candidate"
    args[args.index("false")] = "true"

    assert cli.main(args) == 0
    output = json.loads(capsys.readouterr().out)

    assert output["observation_type"] == "public_post_candidate"
    assert output["requires_human_review"] is True
    assert output["review_status"] == "pending"
    assert output["external_action_allowed"] is False


def test_laviathon_public_post_candidate_rejects_human_review_false(
    laviathon_cli_root: Path,
) -> None:
    args = _base_cli_args()
    args[args.index("critique")] = "public_post_candidate"
    args[args.index("false")] = "true"
    args.extend(["--requires-human-review", "false"])

    with pytest.raises(ValueError, match="public_candidate_requires_human_review"):
        cli.main(args)

    assert not _state_path(laviathon_cli_root).exists()


def test_laviathon_list_and_review_do_not_mutate_state_file(
    laviathon_cli_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(_base_cli_args()) == 0
    capsys.readouterr()
    path = _state_path(laviathon_cli_root)
    before = path.read_text(encoding="utf-8")

    assert cli.main(["laviathon-list-observations"]) == 0
    assert json.loads(capsys.readouterr().out)["observations"]
    after_list = path.read_text(encoding="utf-8")

    assert cli.main(["laviathon-review-candidates"]) == 0
    assert json.loads(capsys.readouterr().out)["review_candidates"]
    after_review = path.read_text(encoding="utf-8")

    assert after_list == before
    assert after_review == before


def test_laviathon_cli_output_is_valid_json(
    laviathon_cli_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del laviathon_cli_root
    assert cli.main(_base_cli_args()) == 0
    appended = json.loads(capsys.readouterr().out)
    assert isinstance(appended, dict)

    assert cli.main(["laviathon-list-observations"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert isinstance(listed["observations"], list)

    assert cli.main(["laviathon-review-candidates", "--observation-type", "critique"]) == 0
    candidates = json.loads(capsys.readouterr().out)
    assert isinstance(candidates["review_candidates"], list)


def test_laviathon_cli_source_scan_has_no_network_or_external_action_primitives() -> None:
    module_root = Path(__file__).resolve().parents[1] / "app" / "spine_observability"
    source = "\n".join(
        (module_root / name).read_text(encoding="utf-8")
        for name in ("cli.py", "laviathon.py", "laviathon_store.py")
    )

    forbidden_tokens = (
        "requests",
        "urllib",
        "http.client",
        "socket",
        ".post(",
        "send_message",
        "smtp",
        "scrape",
        "schedule",
    )
    for token in forbidden_tokens:
        assert token not in source
