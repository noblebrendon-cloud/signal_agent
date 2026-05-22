from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = REPO_ROOT / "tools" / "datasets" / "reflective_pressure_review_batch.py"

spec = importlib.util.spec_from_file_location("reflective_pressure_review_batch", TOOL_PATH)
assert spec is not None
review_tool = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(review_tool)


def test_build_review_creates_table_template_and_manifest(tmp_path: Path) -> None:
    input_path = tmp_path / "reddit_seed_high_score_review_001.jsonl"
    review_dir = tmp_path / "review"
    _write_jsonl(input_path, [_seed(1), _seed(2)])

    report = review_tool.build_review(input_path, review_dir)

    table_path = review_dir / "reddit_high_score_review_001_table.md"
    decisions_path = review_dir / "reddit_high_score_review_001_decisions.template.jsonl"
    manifest_path = review_dir / "reddit_high_score_review_001_manifest.json"
    assert report["total_records"] == 2
    assert table_path.exists()
    assert decisions_path.exists()
    assert manifest_path.exists()
    assert "| row_number | decision | source_platform |" in table_path.read_text(encoding="utf-8")
    decisions = _read_jsonl(decisions_path)
    assert decisions[0]["decision"] == ""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["import_blocked_until_decisions_present"] is True
    assert manifest["allowed_decisions"] == ["KEEP", "SKIP", "NEEDS_CORRECTION", "GOLD_CANDIDATE"]


def test_apply_decisions_fails_if_decisions_are_blank(tmp_path: Path) -> None:
    input_path, decisions_path, review_dir = _batch_with_decisions(tmp_path, [""])

    with pytest.raises(ValueError, match="blank_decision"):
        review_tool.apply_decisions(input_path, decisions_path, review_dir / "approved.jsonl")

    assert not (review_dir / "approved.jsonl").exists()


def test_apply_decisions_fails_on_invalid_decision(tmp_path: Path) -> None:
    input_path, decisions_path, review_dir = _batch_with_decisions(tmp_path, ["MAYBE"])

    with pytest.raises(ValueError, match="invalid_decision"):
        review_tool.apply_decisions(input_path, decisions_path, review_dir / "approved.jsonl")


def test_apply_decisions_exports_only_approved_decision_types_and_skips_skip(tmp_path: Path) -> None:
    input_path = tmp_path / "seeds.jsonl"
    review_dir = tmp_path / "review"
    decisions_path = review_dir / "decisions.jsonl"
    _write_jsonl(input_path, [_seed(1), _seed(2), _seed(3), _seed(4)])
    _write_jsonl(
        decisions_path,
        [
            _decision(1, "KEEP"),
            _decision(2, "SKIP"),
            _decision(3, "NEEDS_CORRECTION"),
            _decision(4, "GOLD_CANDIDATE"),
        ],
    )

    report = review_tool.apply_decisions(input_path, decisions_path, review_dir / "approved.jsonl")
    approved = _read_jsonl(review_dir / "approved.jsonl")

    assert report["approved_count"] == 3
    assert report["skipped_count"] == 1
    assert [row["raw_text"] for row in approved] == [
        "Seed text 1",
        "Seed text 3",
        "Seed text 4",
    ]


def test_row_count_mismatch_fails_closed(tmp_path: Path) -> None:
    input_path = tmp_path / "seeds.jsonl"
    decisions_path = tmp_path / "review" / "decisions.jsonl"
    _write_jsonl(input_path, [_seed(1), _seed(2)])
    _write_jsonl(decisions_path, [_decision(1, "KEEP")])

    with pytest.raises(ValueError, match="row_count_mismatch"):
        review_tool.apply_decisions(input_path, decisions_path, decisions_path.parent / "approved.jsonl")


def test_row_number_mismatch_fails_closed(tmp_path: Path) -> None:
    input_path, decisions_path, review_dir = _batch_with_decisions(tmp_path, ["KEEP"])
    _write_jsonl(decisions_path, [_decision(2, "KEEP")])

    with pytest.raises(ValueError, match="row_number_mismatch"):
        review_tool.apply_decisions(input_path, decisions_path, review_dir / "approved.jsonl")


def test_summarize_decisions_returns_correct_counts(tmp_path: Path) -> None:
    decisions_path = tmp_path / "review" / "decisions.jsonl"
    _write_jsonl(
        decisions_path,
        [
            _decision(1, "KEEP", corrected_pressure_type="spiritual_reductionism"),
            _decision(2, "SKIP"),
            _decision(3, "NEEDS_CORRECTION", corrected_pressure_type="semantic_misalignment"),
            _decision(4, "GOLD_CANDIDATE"),
            _decision(5, ""),
            _decision(6, "MAYBE"),
        ],
    )

    summary = review_tool.summarize_decisions(decisions_path)

    assert summary["total"] == 6
    assert summary["keep_count"] == 1
    assert summary["skip_count"] == 1
    assert summary["needs_correction_count"] == 1
    assert summary["gold_candidate_count"] == 1
    assert summary["blank_count"] == 1
    assert summary["invalid_count"] == 1
    assert summary["corrected_pressure_type_counts"] == {
        "spiritual_reductionism": 1,
        "semantic_misalignment": 1,
    }
    assert summary["ready_for_import"] is False


def test_copy_approved_to_repo_rejects_destination_outside_reflective_pressure_inputs(tmp_path: Path) -> None:
    approved_path = tmp_path / "review" / "approved.jsonl"
    _write_jsonl(approved_path, [_seed(1)])

    with pytest.raises(ValueError, match="repo_output_path_outside_reflective_pressure_inputs"):
        review_tool.copy_approved_to_repo(
            approved_path,
            tmp_path / "data" / "inputs" / "outside.jsonl",
            repo_root=tmp_path,
        )


def test_copy_approved_to_repo_copies_valid_approved_file(tmp_path: Path) -> None:
    approved_path = tmp_path / "review" / "approved.jsonl"
    destination = tmp_path / "data" / "inputs" / "reflective_pressure" / "approved.jsonl"
    _write_jsonl(approved_path, [_seed(1)])

    report = review_tool.copy_approved_to_repo(approved_path, destination, repo_root=tmp_path)

    assert report["copied_count"] == 1
    assert _read_jsonl(destination) == [_seed(1)]


def test_no_unsafe_flags_are_modified_or_introduced(tmp_path: Path) -> None:
    input_path, decisions_path, review_dir = _batch_with_decisions(tmp_path, ["KEEP"])

    review_tool.apply_decisions(input_path, decisions_path, review_dir / "approved.jsonl")
    approved = _read_jsonl(review_dir / "approved.jsonl")

    assert approved[0]["external_action_allowed"] is False
    assert approved[0]["irreversible_action_allowed"] is False
    assert "human_approved" not in approved[0]
    assert "published" not in approved[0]


def _batch_with_decisions(tmp_path: Path, decisions: list[str]) -> tuple[Path, Path, Path]:
    input_path = tmp_path / "seeds.jsonl"
    review_dir = tmp_path / "review"
    decisions_path = review_dir / "decisions.jsonl"
    _write_jsonl(input_path, [_seed(index) for index in range(1, len(decisions) + 1)])
    _write_jsonl(decisions_path, [_decision(index, decision) for index, decision in enumerate(decisions, start=1)])
    return input_path, decisions_path, review_dir


def _seed(index: int) -> dict:
    return {
        "source_platform": "reddit",
        "source_type": "comment",
        "raw_text": f"Seed text {index}",
        "source_context": f"Source context {index}",
        "group_or_channel": "r/example",
        "intended_spine": "reflective",
        "tags": ["pressure_seed", "reddit"],
        "notes": "Guessed pressure type: spiritual_reductionism; Candidate score: 8",
        "external_action_allowed": False,
        "irreversible_action_allowed": False,
    }


def _decision(index: int, decision: str, *, corrected_pressure_type: str = "") -> dict:
    return {
        "row_number": index,
        "decision": decision,
        "reason": "",
        "corrected_pressure_type": corrected_pressure_type,
        "corrected_hidden_pressure": "",
        "gold_candidate": False,
        "operator_notes": "",
    }


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
