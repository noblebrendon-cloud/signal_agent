from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from signal_agent.operational_ingestion.simulator import DeterministicVirtualClock
from signal_agent.relationship_signals.simulated_operational_pipeline import (
    run_simulated_operational_relationship_slice,
)


FIXED_TIME = "2026-08-10T12:00:00Z"
SECOND_TIME = "2026-08-10T13:00:00Z"
PROTECTION_KEY = b"M4B deterministic fixture key only"[:32]
PROTECTION_KEY_ID = "simulated-fixture-protection-v1"


def fixture_path(repository_root: Path, name: str = "base_script.json") -> Path:
    return repository_root / "tests/fixtures/operational_ingestion" / name


def load_fixture(repository_root: Path, name: str = "base_script.json") -> dict[str, Any]:
    return json.loads(fixture_path(repository_root, name).read_text(encoding="utf-8"))


def write_script(path: Path, payload: dict[str, Any]) -> Path:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def run_case(
    repository_root: Path,
    case_root: Path,
    *,
    script_name: str = "base_script.json",
    script_path: Path | None = None,
    start: str = FIXED_TIME,
    session_started_at: str | None = None,
    prior_checkpoint=None,
    resume=None,
    interrupt_after_pages: int | None = None,
    processor_failure_stage: str | None = None,
    acquisition_failure_injector=None,
    kernel_failure_injector=None,
    maximum_pages: int = 10,
    maximum_records: int = 100,
    maximum_response_bytes: int = 1024 * 1024,
    operational_store_root: Path | None = None,
    governed_run_root: Path | None = None,
):
    return run_simulated_operational_relationship_slice(
        script_path=(
            fixture_path(repository_root, script_name)
            if script_path is None
            else script_path
        ),
        retry_policy_path=(
            repository_root / "config/operational_ingestion/retry_policy_v1.json"
        ),
        operational_store_root=(
            case_root / "store"
            if operational_store_root is None
            else operational_store_root
        ),
        governed_run_root=(
            case_root / "governed"
            if governed_run_root is None
            else governed_run_root
        ),
        protection_key=PROTECTION_KEY,
        protection_key_id=PROTECTION_KEY_ID,
        repository_root=repository_root,
        clock=DeterministicVirtualClock(start),
        session_started_at=session_started_at or start,
        prior_checkpoint=prior_checkpoint,
        resume=resume,
        interrupt_after_pages=interrupt_after_pages,
        processor_failure_stage=processor_failure_stage,
        acquisition_failure_injector=acquisition_failure_injector,
        kernel_failure_injector=kernel_failure_injector,
        maximum_pages=maximum_pages,
        maximum_records=maximum_records,
        maximum_response_bytes=maximum_response_bytes,
    )


def tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def normalized_records(governed_root: Path) -> list[dict[str, Any]]:
    path = governed_root / "01_normalized/relationship_records.jsonl"
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def current_checkpoint(source_root: Path):
    from signal_agent.operational_ingestion.checkpoints import (
        resolve_current_checkpoint,
    )

    return resolve_current_checkpoint(source_root)
