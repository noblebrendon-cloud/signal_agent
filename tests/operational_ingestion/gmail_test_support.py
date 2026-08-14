from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from signal_agent.operational_ingestion.simulator import DeterministicVirtualClock
from signal_agent.relationship_signals.gmail_history_pipeline import (
    run_gmail_history_offline_relationship_slice,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FIXED_TIME = "2026-08-10T12:00:00Z"
SECOND_TIME = "2026-08-10T13:00:00Z"
THIRD_TIME = "2026-08-10T14:00:00Z"
PROTECTION_KEY = b"G" * 32
PROTECTION_KEY_ID = "gmail-offline-fixture-protection-v1"
TARGET_LABEL_ID = "Label_TARGET"


def fixture_path(name: str) -> Path:
    return REPOSITORY_ROOT / "tests/fixtures/operational_ingestion" / name


def policy_path() -> Path:
    return REPOSITORY_ROOT / "config/operational_ingestion/gmail_history_metadata_v1.json"


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads(fixture_path(name).read_text(encoding="utf-8"))


def write_fixture(path: Path, payload: dict[str, Any]) -> Path:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def run_case(
    case_root: Path,
    *,
    script_name: str,
    script_path: Path | None = None,
    start: str = FIXED_TIME,
    session_started_at: str | None = None,
    prior_checkpoint=None,
    prior_projection_path: Path | None = None,
    operational_store_root: Path | None = None,
    governed_run_root: Path | None = None,
    processor_failure_stage: str | None = None,
    kernel_failure_injector=None,
):
    return run_gmail_history_offline_relationship_slice(
        fixture_path=fixture_path(script_name) if script_path is None else script_path,
        policy_path=policy_path(),
        target_label_id=TARGET_LABEL_ID,
        operational_store_root=(
            case_root / "store" if operational_store_root is None else operational_store_root
        ),
        governed_run_root=(
            case_root / "governed" if governed_run_root is None else governed_run_root
        ),
        protection_key=PROTECTION_KEY,
        protection_key_id=PROTECTION_KEY_ID,
        repository_root=REPOSITORY_ROOT,
        clock=DeterministicVirtualClock(start),
        session_started_at=session_started_at or start,
        prior_checkpoint=prior_checkpoint,
        prior_projection_path=prior_projection_path,
        processor_failure_stage=processor_failure_stage,
        kernel_failure_injector=kernel_failure_injector,
    )


def projection_path(governed_root: Path) -> Path:
    return governed_root / "05_receipts/gmail_target_label_projection.json"


def load_projection(governed_root: Path) -> dict[str, Any]:
    return json.loads(projection_path(governed_root).read_text(encoding="utf-8"))


def normalized_records(governed_root: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in (governed_root / "01_normalized/relationship_records.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]


def tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
