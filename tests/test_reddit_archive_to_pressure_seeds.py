from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

import pytest

from app.reflective_pressure.models import build_input_record


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = REPO_ROOT / "tools" / "datasets" / "reddit_archive_to_pressure_seeds.py"

spec = importlib.util.spec_from_file_location("reddit_archive_to_pressure_seeds", TOOL_PATH)
assert spec is not None
reddit_tool = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(reddit_tool)


def test_inspect_handles_missing_folders_safely(tmp_path: Path) -> None:
    dataset_root = tmp_path / "reddit"

    report = reddit_tool.inspect_dataset(dataset_root)

    assert report["command"] == "inspect"
    assert report["zip_exists"] is False
    assert report["raw_files"] == []
    assert report["comments_files"] == []
    assert report["posts_files"] == []
    assert report["external_action_allowed"] is False
    assert report["irreversible_action_allowed"] is False


def test_normalize_handles_sample_comment_csv_and_skips_deleted(tmp_path: Path) -> None:
    dataset_root = tmp_path / "reddit"
    _write_csv(
        dataset_root / "raw" / "comments.csv",
        fieldnames=("id", "permalink", "date", "ip", "subreddit", "gildings", "link", "parent", "body", "media"),
        rows=[
            {
                "id": "c1",
                "permalink": "/r/example/comments/post/comment",
                "date": "2026-05-01 12:00:00 UTC",
                "ip": "127.0.0.1",
                "subreddit": "example",
                "gildings": "0",
                "link": "https://reddit.test/r/example/comments/post",
                "parent": "t1_parent",
                "body": "I disagree because truth matters, and that is not what I said.",
                "media": "",
            },
            {
                "id": "c2",
                "permalink": "",
                "date": "2026-05-01 12:05:00 UTC",
                "ip": "127.0.0.1",
                "subreddit": "example",
                "gildings": "0",
                "link": "",
                "parent": "",
                "body": "[deleted]",
                "media": "",
            },
        ],
    )

    report = reddit_tool.normalize_dataset(dataset_root)
    rows = _read_jsonl(dataset_root / "derived" / "reddit_interactions_normalized.jsonl")

    assert report["raw_records_seen"] == 2
    assert report["normalized_count"] == 1
    assert report["skipped_empty_or_deleted"] == 1
    assert rows[0]["record_id"] == "reddit_comment_c1"
    assert rows[0]["source_platform"] == "reddit"
    assert rows[0]["reddit_kind"] == "reply"
    assert rows[0]["subreddit"] == "example"
    assert "ip" not in rows[0]
    assert rows[0]["external_action_allowed"] is False
    assert rows[0]["irreversible_action_allowed"] is False


def test_normalize_handles_sample_post_json(tmp_path: Path) -> None:
    dataset_root = tmp_path / "reddit"
    raw_path = dataset_root / "raw" / "posts.json"
    raw_path.parent.mkdir(parents=True)
    raw_path.write_text(
        json.dumps(
            [
                {
                    "id": "p1",
                    "title": "Why does every system argument become tribal?",
                    "body": "My point is about power and incentives, not about attacking people.",
                    "subreddit": "systems",
                    "created_utc": "1770000000",
                    "score": "12",
                    "permalink": "/r/systems/comments/p1/example",
                    "url": "https://reddit.test/r/systems/comments/p1/example",
                }
            ]
        ),
        encoding="utf-8",
    )

    report = reddit_tool.normalize_dataset(dataset_root)
    rows = _read_jsonl(dataset_root / "derived" / "reddit_interactions_normalized.jsonl")

    assert report["normalized_count"] == 1
    assert rows[0]["record_id"] == "reddit_post_p1"
    assert rows[0]["reddit_kind"] == "post"
    assert "Why does every system argument" in rows[0]["text_for_pressure_analysis"]


def test_candidate_scoring_identifies_moral_disagreement_text() -> None:
    record = {
        "reddit_kind": "reply",
        "score": -1,
        "text_for_pressure_analysis": (
            "That is not what I said. I disagree because the issue is not pride or "
            "winning; the truth matters when people call something good that is wrong."
        ),
    }

    score, reasons = reddit_tool.score_candidate(record)

    assert score >= 8
    assert "morality_language" in reasons
    assert "argumentative_language" in reasons
    assert "clarification_marker" in reasons
    assert reddit_tool._guess_pressure_type(record) == "moral_contradiction_exposure"


def test_export_produces_reflective_pressure_import_jsonl(tmp_path: Path) -> None:
    dataset_root = tmp_path / "reddit"
    _write_csv(
        dataset_root / "raw" / "comments.csv",
        fieldnames=("id", "permalink", "date", "subreddit", "gildings", "link", "parent", "body"),
        rows=[
            {
                "id": "c1",
                "permalink": "/r/faith/comments/post/comment",
                "date": "2026-05-01 12:00:00 UTC",
                "subreddit": "faith",
                "gildings": "0",
                "link": "https://reddit.test/r/faith/comments/post",
                "parent": "t1_parent",
                "body": "I think the Bible argument is being reduced to slogans, but the pressure is deeper.",
            }
        ],
    )

    reddit_tool.normalize_dataset(dataset_root)
    candidate_report = reddit_tool.filter_candidates(dataset_root)
    export_report = reddit_tool.export_seeds(dataset_root, limit=10)
    seeds = _read_jsonl(dataset_root / "derived" / "reddit_seed_batch_001.jsonl")

    assert candidate_report["candidate_count"] == 1
    assert export_report["exported_seed_count"] == 1
    assert seeds[0]["source_platform"] == "reddit"
    assert seeds[0]["source_type"] == "comment"
    assert seeds[0]["raw_text"]
    assert seeds[0]["group_or_channel"] == "r/faith"
    assert seeds[0]["intended_spine"] == "reflective"
    assert seeds[0]["tags"] == ["pressure_seed", "reddit", "reddit_archive"]
    assert "Guessed spine:" in seeds[0]["notes"]


def test_export_filters_by_min_score(tmp_path: Path) -> None:
    dataset_root = _candidate_dataset(
        tmp_path,
        [
            _candidate("low", score=4, text="A small pressure about conflict.", subreddit="example"),
            _candidate("high", score=9, text="A higher pressure about conflict and truth.", subreddit="example"),
        ],
    )

    report = reddit_tool.export_seeds(dataset_root, min_score=8, output_name="reddit_seed_high_score_001.jsonl")
    seeds = _read_jsonl(dataset_root / "derived" / "reddit_seed_high_score_001.jsonl")

    assert report["candidates_before_filtering"] == 2
    assert report["candidates_after_filtering"] == 1
    assert report["exported_seed_count"] == 1
    assert report["skipped_count"] == 1
    assert "higher pressure" in seeds[0]["raw_text"]


def test_export_filters_by_pressure_type(tmp_path: Path) -> None:
    dataset_root = _candidate_dataset(
        tmp_path,
        [
            _candidate("peace", pressure_type="peace_vs_escalation", text="Intent is being misunderstood."),
            _candidate("moral", pressure_type="moral_contradiction_exposure", text="Truth and hypocrisy are exposed."),
        ],
    )

    report = reddit_tool.export_seeds(
        dataset_root,
        pressure_type="peace_vs_escalation",
        output_name="reddit_seed_peace_vs_escalation_001.jsonl",
    )
    seeds = _read_jsonl(dataset_root / "derived" / "reddit_seed_peace_vs_escalation_001.jsonl")

    assert report["filters_applied"]["pressure_type"] == "peace_vs_escalation"
    assert report["candidates_after_filtering"] == 1
    assert "peace_vs_escalation" in seeds[0]["notes"]


def test_export_filters_by_spine(tmp_path: Path) -> None:
    dataset_root = _candidate_dataset(
        tmp_path,
        [
            _candidate("gov", spine="governance", text="The system and authority pressure is visible."),
            _candidate("faith", spine="theological", text="The Bible pressure is visible."),
        ],
    )

    report = reddit_tool.export_seeds(dataset_root, spine="governance", output_name="reddit_seed_governance_001.jsonl")
    seeds = _read_jsonl(dataset_root / "derived" / "reddit_seed_governance_001.jsonl")

    assert report["filters_applied"]["spine"] == "governance"
    assert report["candidates_after_filtering"] == 1
    assert "Guessed spine: governance" in seeds[0]["notes"]


def test_export_filters_by_subreddit_with_and_without_prefix(tmp_path: Path) -> None:
    dataset_root = _candidate_dataset(
        tmp_path,
        [
            _candidate("christianity", subreddit="Christianity", text="A faith pressure."),
            _candidate("other", subreddit="AskReddit", text="A broad pressure."),
        ],
    )

    without_prefix = reddit_tool.export_seeds(
        dataset_root,
        subreddit="christianity",
        output_name="reddit_seed_christianity_001.jsonl",
    )
    with_prefix = reddit_tool.export_seeds(
        dataset_root,
        subreddit="r/Christianity",
        output_name="reddit_seed_christianity_002.jsonl",
    )

    assert without_prefix["candidates_after_filtering"] == 1
    assert with_prefix["candidates_after_filtering"] == 1
    assert _read_jsonl(dataset_root / "derived" / "reddit_seed_christianity_001.jsonl")[0]["group_or_channel"] == "r/Christianity"
    assert _read_jsonl(dataset_root / "derived" / "reddit_seed_christianity_002.jsonl")[0]["group_or_channel"] == "r/Christianity"


def test_export_filters_by_contains_text(tmp_path: Path) -> None:
    dataset_root = _candidate_dataset(
        tmp_path,
        [
            _candidate("needle", text="This one names the actual pressure clearly."),
            _candidate("hay", text="This one is about something adjacent."),
        ],
    )

    report = reddit_tool.export_seeds(dataset_root, contains="ACTUAL PRESSURE", output_name="reddit_seed_contains_001.jsonl")
    seeds = _read_jsonl(dataset_root / "derived" / "reddit_seed_contains_001.jsonl")

    assert report["filters_applied"]["contains"] == "actual pressure"
    assert report["candidates_after_filtering"] == 1
    assert "actual pressure" in seeds[0]["raw_text"]


def test_export_exclude_deleted_skips_removed_or_unavailable_content(tmp_path: Path) -> None:
    dataset_root = _candidate_dataset(
        tmp_path,
        [
            _candidate("removed", title="[removed]", body="Useful looking body that should not pass."),
            _candidate("kept", title="Visible title", body="Visible body about truth and conflict."),
        ],
    )

    report = reddit_tool.export_seeds(
        dataset_root,
        exclude_deleted=True,
        output_name="reddit_seed_exclude_deleted_001.jsonl",
    )
    seeds = _read_jsonl(dataset_root / "derived" / "reddit_seed_exclude_deleted_001.jsonl")

    assert report["filters_applied"]["exclude_deleted"] is True
    assert report["candidates_after_filtering"] == 1
    assert "Visible body" in seeds[0]["raw_text"]


def test_export_rejects_output_name_path_traversal(tmp_path: Path) -> None:
    dataset_root = _candidate_dataset(tmp_path, [_candidate("safe")])

    with pytest.raises(ValueError, match="invalid_output_name"):
        reddit_tool.export_seeds(dataset_root, output_name="..\\outside.jsonl")

    assert not (dataset_root / "outside.jsonl").exists()


def test_export_rejects_invalid_pressure_type_and_spine(tmp_path: Path) -> None:
    dataset_root = _candidate_dataset(tmp_path, [_candidate("safe")])

    with pytest.raises(ValueError, match="invalid_pressure_type"):
        reddit_tool.export_seeds(dataset_root, pressure_type="ragebait")

    with pytest.raises(ValueError, match="invalid_spine"):
        reddit_tool.export_seeds(dataset_root, spine="influencer")


def test_valid_filtered_export_produces_importable_reflective_pressure_jsonl(tmp_path: Path) -> None:
    dataset_root = _candidate_dataset(
        tmp_path,
        [
            _candidate(
                "system",
                score=11,
                pressure_type="authority_confusion",
                spine="governance",
                text="The system pressure is not just politics; it is about authority and trust.",
                subreddit="systems",
            )
        ],
    )

    reddit_tool.export_seeds(
        dataset_root,
        min_score=8,
        pressure_type="authority_confusion",
        spine="governance",
        contains="authority",
        output_name="reddit_seed_authority_001.jsonl",
    )
    seed = _read_jsonl(dataset_root / "derived" / "reddit_seed_authority_001.jsonl")[0]
    record = build_input_record(
        source_platform=seed["source_platform"],
        source_type=seed["source_type"],
        raw_text=seed["raw_text"],
        source_context=seed["source_context"],
        group_or_channel=seed["group_or_channel"],
        intended_spine=seed["intended_spine"],
        tags=seed["tags"],
        notes=seed["notes"],
        created_at="2026-05-14T12:00:00Z",
    )

    assert record["source_platform"] == "reddit"
    assert record["intended_spine"] == "reflective"
    assert record["external_action_allowed"] is False
    assert record["irreversible_action_allowed"] is False


def test_all_derived_records_keep_unsafe_flags_false(tmp_path: Path) -> None:
    dataset_root = tmp_path / "reddit"
    _write_csv(
        dataset_root / "raw" / "comments.csv",
        fieldnames=("id", "date", "subreddit", "gildings", "parent", "body"),
        rows=[
            {
                "id": "c1",
                "date": "2026-05-01 12:00:00 UTC",
                "subreddit": "example",
                "gildings": "0",
                "parent": "t1_parent",
                "body": "Nobody understood my point because the disagreement was really about power.",
            }
        ],
    )

    reddit_tool.normalize_dataset(dataset_root)
    reddit_tool.filter_candidates(dataset_root)

    for path in (
        dataset_root / "derived" / "reddit_interactions_normalized.jsonl",
        dataset_root / "derived" / "reddit_pressure_candidates.jsonl",
    ):
        for row in _read_jsonl(path):
            assert row["external_action_allowed"] is False
            assert row["irreversible_action_allowed"] is False


def test_reddit_source_platform_is_accepted_by_reflective_pressure_models() -> None:
    record = build_input_record(
        source_platform="reddit",
        source_type="comment",
        raw_text="People keep turning deeper discussion into slogans.",
        intended_spine="reflective",
        created_at="2026-05-14T12:00:00Z",
    )

    assert record["source_platform"] == "reddit"
    assert record["external_action_allowed"] is False
    assert record["irreversible_action_allowed"] is False


def _write_csv(path: Path, *, fieldnames: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _candidate_dataset(tmp_path: Path, candidates: list[dict]) -> Path:
    dataset_root = tmp_path / "reddit"
    _write_jsonl(dataset_root / "derived" / "reddit_pressure_candidates.jsonl", candidates)
    return dataset_root


def _candidate(
    record_id: str,
    *,
    score: int = 8,
    pressure_type: str = "moral_contradiction_exposure",
    spine: str = "reflective",
    text: str = "A pressure about truth, conflict, and meaning.",
    subreddit: str = "example",
    title: str = "Visible title",
    body: str | None = None,
) -> dict:
    body_value = body if body is not None else text
    return {
        "record_id": f"reddit_comment_{record_id}",
        "source_platform": "reddit",
        "reddit_kind": "comment",
        "subreddit": subreddit,
        "created_utc": "2026-05-01 12:00:00 UTC",
        "score": 0,
        "title": title,
        "body": body_value,
        "parent_id": "",
        "link_id": "",
        "permalink": f"https://reddit.test/r/{subreddit}/comments/{record_id}",
        "url": "",
        "raw_file": "comments.csv",
        "raw_index": 1,
        "text_for_pressure_analysis": text if body is None else f"{title}\n\n{body_value}",
        "candidate_score": score,
        "candidate_reasons": ["test_fixture"],
        "guessed_pressure_type": pressure_type,
        "guessed_spine": spine,
        "recommended_output_type": "reply",
        "notes": "fixture",
        "external_action_allowed": False,
        "irreversible_action_allowed": False,
    }


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
