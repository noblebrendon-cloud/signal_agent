from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.hq.capture import capture, promote, router
from app.utils import io_contract


def _read_jsonl_rows(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


@pytest.fixture
def capture_dir(tmp_path: Path) -> Path:
    base = tmp_path / "capture"
    base.mkdir(parents=True, exist_ok=True)
    return base


def test_capture_telemetry_uses_governed_append_and_remains_parseable(capture_dir: Path) -> None:
    log_path = capture_dir / "capture_log.jsonl"
    expected = {
        "timestamp_utc": "2026-04-28T00:00:00Z",
        "filename": "raw_2026-04-28T00-00-00_000Z.md",
        "input_type": "text",
        "source": None,
        "length": 12,
    }

    with (
        patch.object(capture, "append_jsonl_atomic", wraps=capture.append_jsonl_atomic) as mock_append,
        patch.object(io_contract, "_FileLock", wraps=io_contract._FileLock) as mock_lock,
    ):
        capture._append_telemetry(
            capture_dir=capture_dir,
            filename=expected["filename"],
            input_type=expected["input_type"],
            source=expected["source"],
            content_length=expected["length"],
            timestamp_utc=expected["timestamp_utc"],
        )

    mock_append.assert_called_once()
    assert Path(mock_append.call_args.args[0]) == log_path
    assert mock_lock.call_count >= 1
    assert log_path.with_suffix(".jsonl.lock").exists()
    assert _read_jsonl_rows(log_path) == [expected]


@pytest.mark.parametrize(
    ("module", "helper_name", "log_name", "entry", "error_text"),
    [
        (
            promote,
            "_append_promo_log",
            "promotion_log.jsonl",
            {
                "cluster_id": "cluster-001",
                "bundle_filename": "bundle_20260428_cluster-001.md",
                "raw_files": ["raw_a.md", "raw_b.md"],
                "status": "ok",
                "strategy": "hybrid",
            },
            "Failed to append promotion log",
        ),
        (
            router,
            "_append_routing_log",
            "routing_log.jsonl",
            {
                "timestamp_utc": "2026-04-28T00:00:00Z",
                "bundle_filename": "bundle_test.md",
                "spine": "misc",
                "score": 0.12,
                "status": "ok",
                "error": None,
            },
            "Failed to append routing log",
        ),
    ],
)
def test_capture_runtime_log_helpers_use_governed_append(
    capture_dir: Path,
    module: object,
    helper_name: str,
    log_name: str,
    entry: dict,
    error_text: str,
) -> None:
    helper = getattr(module, helper_name)
    log_path = capture_dir / log_name

    with (
        patch.object(module, "append_jsonl_atomic", wraps=module.append_jsonl_atomic) as mock_append,
        patch.object(io_contract, "_FileLock", wraps=io_contract._FileLock) as mock_lock,
    ):
        helper(capture_dir, entry)

    mock_append.assert_called_once()
    assert Path(mock_append.call_args.args[0]) == log_path
    assert mock_lock.call_count >= 1
    assert log_path.with_suffix(".jsonl.lock").exists()
    assert _read_jsonl_rows(log_path) == [entry]

    with patch.object(module, "append_jsonl_atomic", side_effect=OSError("append failed")):
        with pytest.raises(RuntimeError, match=error_text):
            helper(capture_dir, entry)


def test_route_bundle_cleans_up_partial_copy_and_returns_fail(capture_dir: Path, tmp_path: Path) -> None:
    bundle_path = capture_dir / "promoted" / "bundle_test.md"
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    bundle_path.write_text("---\nlifecycle_state: promoted\n---\n\nalpha beta\n", encoding="utf-8")
    spines_dir = tmp_path / "constraints" / "spines"

    def _fail_copy(_src: str, dest: str) -> None:
        Path(dest).write_text("partial\n", encoding="utf-8")
        raise OSError("copy failed")

    validation = {
        "allowed": True,
        "current_state": "promoted",
        "next_state": "routed",
        "lane_id": "content_publishing",
        "state_source": "registry",
        "gate": "routing_policy",
        "policy_id": "routing_policy",
        "policy_result": {"allowed": True, "failures": []},
        "reason": None,
    }

    with (
        patch.object(router, "_resolve_contract", return_value={"contract_source": "registry", "confidence": 1.0, "routable": True}),
        patch.object(router, "_load_spine_config", return_value=([{"name": "content_publishing", "keywords": ["alpha"], "domains": []}], "cfg123")),
        patch("shared.authority.check_preconditions_for_routing", return_value={"authority": {"allowed": True}, "coherence": {}}),
        patch("shared.state_registry.get_state", return_value={"state": "promoted"}),
        patch("shared.state_registry.record_state"),
        patch("app.hq.governance.validate_transition", return_value=validation),
        patch("app.hq.governance.emit_transition_event"),
        patch("app.hq.governance.new_run_id", return_value="route-run-1"),
        patch.object(router.shutil, "copy2", side_effect=_fail_copy),
    ):
        result = router.route_bundle(
            bundle_path=bundle_path,
            capture_dir=capture_dir,
            spines_dir=spines_dir,
        )

    routed_copy = spines_dir / "content_publishing" / "incoming" / bundle_path.name
    assert result["status"] == "fail"
    assert "copy failed" in result["error"]
    assert not routed_copy.exists()
    assert _read_jsonl_rows(capture_dir / "routing_log.jsonl")[-1]["status"] == "fail"


def test_route_bundle_raises_when_routing_log_append_fails(capture_dir: Path) -> None:
    bundle_path = capture_dir / "promoted" / "bundle_dry_run.md"
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    bundle_path.write_text("---\nlifecycle_state: promoted\n---\n\nalpha beta\n", encoding="utf-8")

    with (
        patch.object(router, "_resolve_contract", return_value={"contract_source": "registry", "confidence": 1.0, "routable": True}),
        patch.object(router, "_load_spine_config", return_value=([{"name": "content_publishing", "keywords": ["alpha"], "domains": []}], "cfg123")),
        patch.object(router, "append_jsonl_atomic", side_effect=OSError("append failed")),
    ):
        with pytest.raises(RuntimeError, match="Failed to append routing log"):
            router.route_bundle(
                bundle_path=bundle_path,
                capture_dir=capture_dir,
                dry_run=True,
            )
