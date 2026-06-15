from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import app.hq.governance as governance
from app.hq.capture import promote


def _make_capture_dir(tmp_path: Path) -> Path:
    capture_dir = tmp_path / "capture"
    for name in ("raw", "promoted", "archive"):
        (capture_dir / name).mkdir(parents=True, exist_ok=True)
    return capture_dir


def _create_raw_pair(capture_dir: Path) -> None:
    raw_dir = capture_dir / "raw"
    body_a = "Governed promotion separation keeps artifact writes after decisions."
    body_b = "Governed promotion decisions must precede promoted artifact writes."
    for idx, body in enumerate((body_a, body_b), start=1):
        (raw_dir / f"raw_2026-06-14T00-00-0{idx}_00{idx}Z.md").write_text(
            "---\n"
            "timestamp_utc: 2026-06-14T00:00:00Z\n"
            "input_type: text\n"
            "source: null\n"
            "---\n\n"
            f"{body}\n",
            encoding="utf-8",
        )


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _state_registry_path(capture_dir: Path) -> Path:
    return capture_dir.parent / "data" / "state" / "artifact_registry.jsonl"


def _promotion_log_path(capture_dir: Path) -> Path:
    return capture_dir / "promotion_log.jsonl"


def _rejected_validation(failure: str) -> dict:
    return {
        "allowed": False,
        "current_state": None,
        "next_state": "promoted",
        "lane_id": "volatile_capture",
        "state_source": "missing",
        "gate": "promotion_policy",
        "policy_id": "promotion_policy",
        "policy_result": {
            "allowed": False,
            "failures": [failure],
        },
        "reason": failure,
    }


def _production_jsonl_snapshot() -> dict[str, tuple[int, str]]:
    data_dir = Path(__file__).resolve().parents[1] / "data"
    snapshot: dict[str, tuple[int, str]] = {}
    if not data_dir.exists():
        return snapshot
    for path in sorted(data_dir.rglob("*.jsonl")):
        payload = path.read_bytes()
        snapshot[str(path)] = (len(payload), hashlib.sha256(payload).hexdigest())
    return snapshot


@pytest.mark.parametrize(
    "failure",
    [
        "candidate_cluster_members_present",
        "bundle_identity_present",
    ],
)
def test_invalid_promotion_rejection_creates_no_promoted_bundle_registry_or_success_log(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    capture_dir = _make_capture_dir(tmp_path)
    _create_raw_pair(capture_dir)
    promoted_dir = capture_dir / "promoted"
    decision_observation: dict[str, list[Path]] = {}

    def reject_before_write(*args, **kwargs) -> dict:
        decision_observation["promoted_files_at_decision"] = list(promoted_dir.glob("bundle_*.md"))
        return _rejected_validation(failure)

    monkeypatch.setattr(governance, "validate_transition", reject_before_write)

    with pytest.raises(RuntimeError, match="Canonical gate rejected promotion"):
        promote.promote_run(
            capture_dir=capture_dir,
            min_cluster_size=2,
            threshold=0.10,
        )

    assert decision_observation["promoted_files_at_decision"] == []
    assert list(promoted_dir.glob("bundle_*.md")) == []
    assert _read_jsonl(_state_registry_path(capture_dir)) == []
    assert not any(
        row.get("status") in {"ok", "partial"}
        for row in _read_jsonl(_promotion_log_path(capture_dir))
    )


def test_valid_promotion_writes_bundle_registry_and_log_after_decision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture_dir = _make_capture_dir(tmp_path)
    _create_raw_pair(capture_dir)
    promoted_dir = capture_dir / "promoted"
    real_validate = governance.validate_transition
    decision_observation: dict[str, list[Path]] = {}

    def validate_before_write(*args, **kwargs) -> dict:
        decision_observation["promoted_files_at_decision"] = list(promoted_dir.glob("bundle_*.md"))
        return real_validate(*args, **kwargs)

    monkeypatch.setattr(governance, "validate_transition", validate_before_write)
    monkeypatch.setattr(promote, "_try_route", lambda bundle_path: {"spine": "test_spine"})
    monkeypatch.setattr(promote, "_try_instability", lambda capture_dir: [])
    monkeypatch.setattr("shared.events.emit_event", lambda *args, **kwargs: None)

    result = promote.promote_run(
        capture_dir=capture_dir,
        min_cluster_size=2,
        threshold=0.10,
    )

    promoted = list(promoted_dir.glob("bundle_*.md"))
    assert decision_observation["promoted_files_at_decision"] == []
    assert result["status"] == "ok"
    assert len(promoted) == 1
    assert result["bundles"][0]["bundle"] == promoted[0].name

    registry_rows = _read_jsonl(_state_registry_path(capture_dir))
    assert any(
        row.get("artifact_id") == promoted[0].name
        and row.get("state") == "promoted"
        and row.get("path") == str(promoted[0])
        for row in registry_rows
    )

    promo_rows = _read_jsonl(_promotion_log_path(capture_dir))
    assert promo_rows[-1]["bundle_filename"] == promoted[0].name
    assert promo_rows[-1]["status"] in {"ok", "partial"}
    assert promo_rows[-1]["raw_files"]


def test_temp_hq_promotion_does_not_modify_production_jsonl_ledgers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = _production_jsonl_snapshot()
    capture_dir = _make_capture_dir(tmp_path)
    _create_raw_pair(capture_dir)
    monkeypatch.setattr(promote, "_try_route", lambda bundle_path: {"spine": "test_spine"})
    monkeypatch.setattr(promote, "_try_instability", lambda capture_dir: [])
    monkeypatch.setattr("shared.events.emit_event", lambda *args, **kwargs: None)

    promote.promote_run(
        capture_dir=capture_dir,
        min_cluster_size=2,
        threshold=0.10,
    )

    after = _production_jsonl_snapshot()
    assert after == before
