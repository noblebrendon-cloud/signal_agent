from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.spine_observability import cli
from app.spine_observability.models import build_spine_record
from app.spine_observability.store import (
    METRIC_SNAPSHOTS_FILE,
    PLATFORMS_FILE,
    SPINES_FILE,
    add_metric_snapshot,
    add_platform_account,
    add_spine,
)
from app.spine_observability.summary import (
    build_spine_summary,
    build_under_tracked_report,
)


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


@pytest.fixture
def spine_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    monkeypatch.setenv("SIGNAL_AGENT_ROOT", str(root))
    return root


def test_valid_spine_appends(spine_root: Path) -> None:
    record = add_spine(
        name="governance_spine",
        description="Governance content spine",
        created_at="2026-05-13T00:00:00Z",
    )

    rows = _read_jsonl(spine_root / "data" / "state" / SPINES_FILE)
    assert len(rows) == 1
    assert rows[0] == record
    assert record["schema_version"] == "1.0"
    assert record["spine_id"].startswith("spn_")
    assert record["name"] == "governance_spine"
    assert record["description"] == "Governance content spine"
    assert record["created_at"] == "2026-05-13T00:00:00Z"
    assert record["active"] is True
    assert record["prev_hash"] is None
    assert record["record_hash"].startswith("sha256:")


def test_duplicate_or_invalid_spine_behavior_is_deterministic(spine_root: Path) -> None:
    first = add_spine(
        name="governance_spine",
        description="Governance content spine",
        created_at="2026-05-13T00:00:00Z",
    )
    duplicate_preview = build_spine_record(
        name="governance_spine",
        description="Different description",
        created_at="2026-05-14T00:00:00Z",
    )

    assert duplicate_preview["spine_id"] == first["spine_id"]
    with pytest.raises(ValueError, match=f"duplicate_spine:{first['spine_id']}"):
        add_spine(
            name="governance_spine",
            description="Different description",
            created_at="2026-05-14T00:00:00Z",
        )
    with pytest.raises(ValueError, match="missing_name"):
        build_spine_record(name="", description="", created_at="2026-05-13T00:00:00Z")

    rows = _read_jsonl(spine_root / "data" / "state" / SPINES_FILE)
    assert len(rows) == 1


def test_valid_platform_account_appends_under_existing_spine(spine_root: Path) -> None:
    spine = add_spine(
        name="governance_spine",
        description="Governance content spine",
        created_at="2026-05-13T00:00:00Z",
    )
    platform = add_platform_account(
        spine_id=spine["spine_id"],
        platform="linkedin",
        account_label="primary",
        content_lane="governance",
        created_at="2026-05-13T00:01:00Z",
    )

    rows = _read_jsonl(spine_root / "data" / "state" / PLATFORMS_FILE)
    assert len(rows) == 1
    assert rows[0] == platform
    assert platform["platform_account_id"].startswith("spa_")
    assert platform["spine_id"] == spine["spine_id"]
    assert platform["platform"] == "linkedin"
    assert platform["account_label"] == "primary"
    assert platform["content_lane"] == "governance"
    assert platform["active"] is True


def test_platform_account_fails_if_spine_does_not_exist(spine_root: Path) -> None:
    with pytest.raises(ValueError, match="unknown_spine:spn_missing"):
        add_platform_account(
            spine_id="spn_missing",
            platform="linkedin",
            account_label="primary",
            content_lane="governance",
            created_at="2026-05-13T00:01:00Z",
        )

    assert _read_jsonl(spine_root / "data" / "state" / PLATFORMS_FILE) == []


def test_valid_manual_metric_snapshot_appends(spine_root: Path) -> None:
    platform = _seed_platform(spine_root)
    snapshot = add_metric_snapshot(
        platform_account_id=platform["platform_account_id"],
        captured_at="2026-05-13T12:00:00Z",
        metric_window_start="2026-05-06",
        metric_window_end="2026-05-13",
        metrics={"followers": 1200, "posts_last_7d": 3},
        notes="Manual weekly snapshot",
    )

    rows = _read_jsonl(spine_root / "data" / "state" / METRIC_SNAPSHOTS_FILE)
    assert len(rows) == 1
    assert rows[0] == snapshot
    assert snapshot["snapshot_id"].startswith("sms_")
    assert snapshot["platform_account_id"] == platform["platform_account_id"]
    assert snapshot["source_type"] == "manual"
    assert snapshot["external_action_allowed"] is False
    assert snapshot["metrics"] == {"followers": 1200, "posts_last_7d": 3}


def test_metric_snapshot_fails_if_platform_account_does_not_exist(spine_root: Path) -> None:
    with pytest.raises(ValueError, match="unknown_platform_account:spa_missing"):
        add_metric_snapshot(
            platform_account_id="spa_missing",
            captured_at="2026-05-13T12:00:00Z",
            metric_window_start="2026-05-06",
            metric_window_end="2026-05-13",
            metrics={"followers": 1200},
        )

    assert _read_jsonl(spine_root / "data" / "state" / METRIC_SNAPSHOTS_FILE) == []


def test_external_action_allowed_cannot_be_true(spine_root: Path) -> None:
    platform = _seed_platform(spine_root)

    with pytest.raises(ValueError, match="external_action_not_allowed"):
        add_metric_snapshot(
            platform_account_id=platform["platform_account_id"],
            captured_at="2026-05-13T12:00:00Z",
            metric_window_start="2026-05-06",
            metric_window_end="2026-05-13",
            metrics={"followers": 1200},
            external_action_allowed=True,
        )

    assert _read_jsonl(spine_root / "data" / "state" / METRIC_SNAPSHOTS_FILE) == []


def test_summary_groups_by_spine(spine_root: Path) -> None:
    governance = add_spine(
        name="governance_spine",
        description="Governance content spine",
        created_at="2026-05-13T00:00:00Z",
    )
    reflective = add_spine(
        name="reflective_spine",
        description="Reflective content spine",
        created_at="2026-05-13T00:01:00Z",
    )
    linkedin = add_platform_account(
        spine_id=governance["spine_id"],
        platform="linkedin",
        account_label="primary",
        content_lane="governance",
        created_at="2026-05-13T00:02:00Z",
    )
    facebook = add_platform_account(
        spine_id=reflective["spine_id"],
        platform="facebook",
        account_label="primary",
        content_lane="reflection",
        created_at="2026-05-13T00:03:00Z",
    )
    add_metric_snapshot(
        platform_account_id=linkedin["platform_account_id"],
        captured_at="2026-05-13T12:00:00Z",
        metric_window_start="2026-05-06",
        metric_window_end="2026-05-13",
        metrics={"followers": 1200},
    )
    add_metric_snapshot(
        platform_account_id=facebook["platform_account_id"],
        captured_at="2026-05-13T13:00:00Z",
        metric_window_start="2026-05-06",
        metric_window_end="2026-05-13",
        metrics={"followers": 300},
    )

    summary = build_spine_summary(
        under_tracked_days=7,
        as_of="2026-05-14T00:00:00Z",
    )

    grouped = {spine["name"]: spine for spine in summary["spines"]}
    assert list(grouped) == ["governance_spine", "reflective_spine"]
    assert grouped["governance_spine"]["platforms"][0]["platform"] == "linkedin"
    assert grouped["governance_spine"]["platforms"][0]["latest_snapshot"]["metrics"]["followers"] == 1200
    assert grouped["reflective_spine"]["platforms"][0]["platform"] == "facebook"
    assert summary["under_tracked_platforms"] == []


def test_under_tracked_platform_detection_works(spine_root: Path) -> None:
    spine = add_spine(
        name="governance_spine",
        description="Governance content spine",
        created_at="2026-05-01T00:00:00Z",
    )
    fresh = add_platform_account(
        spine_id=spine["spine_id"],
        platform="linkedin",
        account_label="primary",
        content_lane="governance",
        created_at="2026-05-01T00:01:00Z",
    )
    stale = add_platform_account(
        spine_id=spine["spine_id"],
        platform="x",
        account_label="primary",
        content_lane="governance",
        created_at="2026-05-01T00:02:00Z",
    )
    missing = add_platform_account(
        spine_id=spine["spine_id"],
        platform="substack",
        account_label="primary",
        content_lane="governance",
        created_at="2026-05-01T00:03:00Z",
    )
    add_metric_snapshot(
        platform_account_id=fresh["platform_account_id"],
        captured_at="2026-05-13T12:00:00Z",
        metric_window_start="2026-05-06",
        metric_window_end="2026-05-13",
        metrics={"followers": 1200},
    )
    add_metric_snapshot(
        platform_account_id=stale["platform_account_id"],
        captured_at="2026-04-01T12:00:00Z",
        metric_window_start="2026-03-25",
        metric_window_end="2026-04-01",
        metrics={"followers": 1000},
    )

    report = build_under_tracked_report(
        days=7,
        as_of="2026-05-14T00:00:00Z",
    )

    by_id = {row["platform_account_id"]: row for row in report["under_tracked_platforms"]}
    assert fresh["platform_account_id"] not in by_id
    assert by_id[stale["platform_account_id"]]["reason"] == "stale_snapshot"
    assert by_id[missing["platform_account_id"]]["reason"] == "missing_snapshot"


def test_cli_commands_work_with_tmp_path_isolation(
    spine_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = cli.main(
        [
            "spine-add",
            "--name",
            "governance_spine",
            "--description",
            "Governance content spine",
            "--created-at",
            "2026-05-13T00:00:00Z",
        ]
    )
    assert result == 0
    spine = json.loads(capsys.readouterr().out)

    result = cli.main(["spine-list"])
    assert result == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed["spines"][0]["spine_id"] == spine["spine_id"]

    result = cli.main(
        [
            "spine-add-platform",
            "--spine-name",
            "governance_spine",
            "--platform",
            "linkedin",
            "--account-label",
            "primary",
            "--content-lane",
            "governance",
            "--created-at",
            "2026-05-13T00:01:00Z",
        ]
    )
    assert result == 0
    platform = json.loads(capsys.readouterr().out)

    result = cli.main(
        [
            "spine-add-metric-snapshot",
            "--platform-account-id",
            platform["platform_account_id"],
            "--captured-at",
            "2026-05-13T12:00:00Z",
            "--metric-window-start",
            "2026-05-06",
            "--metric-window-end",
            "2026-05-13",
            "--metrics-json",
            '{"followers": 1200, "posts_last_7d": 3}',
        ]
    )
    assert result == 0
    snapshot = json.loads(capsys.readouterr().out)
    assert snapshot["external_action_allowed"] is False

    result = cli.main(
        [
            "spine-summary",
            "--format",
            "json",
            "--as-of",
            "2026-05-14T00:00:00Z",
        ]
    )
    assert result == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["spines"][0]["platforms"][0]["latest_snapshot"]["snapshot_id"] == snapshot["snapshot_id"]

    state_root = spine_root / "data" / "state"
    assert (state_root / SPINES_FILE).exists()
    assert (state_root / PLATFORMS_FILE).exists()
    assert (state_root / METRIC_SNAPSHOTS_FILE).exists()


def test_no_network_or_posting_behavior_exists() -> None:
    module_root = Path(__file__).resolve().parents[1] / "app" / "spine_observability"
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(module_root.glob("*.py"))
    )

    forbidden_tokens = (
        "requests",
        "urllib",
        "http.client",
        "socket",
        "post(",
        "send_message",
        "scrape",
    )
    for token in forbidden_tokens:
        assert token not in source


def _seed_platform(spine_root: Path) -> dict:
    del spine_root
    spine = add_spine(
        name="governance_spine",
        description="Governance content spine",
        created_at="2026-05-13T00:00:00Z",
    )
    return add_platform_account(
        spine_id=spine["spine_id"],
        platform="linkedin",
        account_label="primary",
        content_lane="governance",
        created_at="2026-05-13T00:01:00Z",
    )
