from __future__ import annotations

import ast
import inspect
import json
import subprocess
import sys
from pathlib import Path

import signal_agent.leviathan.daemon.leviathan_daemon as daemon_module
import signal_agent.leviathan.runtime.tasks as tasks_module


def _run_daemon(
    *,
    ledger: Path,
    inbox: Path,
    processed: Path,
    lock_path: Path,
    max_ticks: int,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "signal_agent.leviathan.daemon.leviathan_daemon",
            "--ledger",
            str(ledger),
            "--inbox-dir",
            str(inbox),
            "--processed-dir",
            str(processed),
            "--lock-path",
            str(lock_path),
            "--clock-resolution",
            "0.01",
            "--max-ticks",
            str(max_ticks),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [json.loads(line) for line in lines]


def test_daemon_has_no_polling_loop_and_runs_under_clock(tmp_path: Path):
    source = inspect.getsource(daemon_module)
    tree = ast.parse(source)
    assert not any(isinstance(node, ast.While) for node in ast.walk(tree))

    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    ledger = tmp_path / "causal_ledger.jsonl"
    lock_path = tmp_path / "locks" / "leviathan_daemon.lock"
    inbox.mkdir(parents=True, exist_ok=True)
    processed.mkdir(parents=True, exist_ok=True)

    proc = _run_daemon(
        ledger=ledger,
        inbox=inbox,
        processed=processed,
        lock_path=lock_path,
        max_ticks=1,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "[Leviathan] runtime authority acquired" in proc.stdout
    assert "[Leviathan] clock initialized" in proc.stdout
    assert "[Leviathan] tasks registered" in proc.stdout
    assert "[Leviathan] entering governed execution" in proc.stdout


def test_inbox_processed_by_clock_tick(tmp_path: Path):
    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    ledger = tmp_path / "causal_ledger.jsonl"
    lock_path = tmp_path / "locks" / "leviathan_daemon.lock"
    inbox.mkdir(parents=True, exist_ok=True)
    processed.mkdir(parents=True, exist_ok=True)
    (inbox / "event1.txt").write_text("clock-governed ingestion", encoding="utf-8")

    proc = _run_daemon(
        ledger=ledger,
        inbox=inbox,
        processed=processed,
        lock_path=lock_path,
        max_ticks=1,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "[Leviathan] processed event: event1.txt" in proc.stdout
    assert (processed / "event1.txt").exists()
    assert ledger.exists()
    assert len(_read_jsonl(ledger)) == 1


def test_daemon_clock_governed_runtime_processes_inbox_once(tmp_path: Path):
    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    ledger = tmp_path / "causal_ledger.jsonl"
    lock_path = tmp_path / "locks" / "leviathan_daemon.lock"
    inbox.mkdir(parents=True, exist_ok=True)
    processed.mkdir(parents=True, exist_ok=True)
    (inbox / "event1.txt").write_text("governed once ingestion", encoding="utf-8")

    proc = _run_daemon(
        ledger=ledger,
        inbox=inbox,
        processed=processed,
        lock_path=lock_path,
        max_ticks=3,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "[Leviathan] processed event: event1.txt" in proc.stdout
    assert proc.stdout.count("[Leviathan] processed event: event1.txt") == 1
    assert (processed / "event1.txt").exists()
    assert ledger.exists()
    entries = _read_jsonl(ledger)
    assert len(entries) == 1
    assert entries[0].get("event", {}).get("event_id")


def test_rerun_cycle_is_noop_after_file_moved(tmp_path: Path):
    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    ledger = tmp_path / "causal_ledger.jsonl"
    lock_path = tmp_path / "locks" / "leviathan_daemon.lock"
    inbox.mkdir(parents=True, exist_ok=True)
    processed.mkdir(parents=True, exist_ok=True)
    (inbox / "event1.txt").write_text("rerun should be no-op", encoding="utf-8")

    first = _run_daemon(
        ledger=ledger,
        inbox=inbox,
        processed=processed,
        lock_path=lock_path,
        max_ticks=3,
    )
    assert first.returncode == 0, first.stdout + first.stderr
    assert first.stdout.count("[Leviathan] processed event: event1.txt") == 1

    entries_after_first = _read_jsonl(ledger)
    assert len(entries_after_first) == 1

    second = _run_daemon(
        ledger=ledger,
        inbox=inbox,
        processed=processed,
        lock_path=lock_path,
        max_ticks=2,
    )
    assert second.returncode == 0, second.stdout + second.stderr
    assert "[Leviathan] processed event: event1.txt" not in second.stdout

    entries_after_second = _read_jsonl(ledger)
    assert len(entries_after_second) == 1


def test_partial_failure_after_append_does_not_double_append(tmp_path: Path, monkeypatch):
    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    ledger = tmp_path / "causal_ledger.jsonl"
    inbox.mkdir(parents=True, exist_ok=True)
    processed.mkdir(parents=True, exist_ok=True)
    (inbox / "event1.txt").write_text("partial failure replay safety", encoding="utf-8")

    config = tasks_module.LeviathanTaskConfig(
        inbox_dir=inbox,
        processed_dir=processed,
        ledger_path=ledger,
    )
    runtime = tasks_module.LeviathanTaskRuntime(config, log_fn=lambda _msg: None)

    def _explode_move(src: Path, processed_dir: Path) -> Path:
        raise RuntimeError("simulated crash after append")

    monkeypatch.setattr(tasks_module, "_move_to_processed", _explode_move)

    runtime.process_inbox_once()

    entries_first = _read_jsonl(ledger)
    assert len(entries_first) == 1
    assert not (inbox / "event1.txt").exists()
    assert (processed / "event1.error.txt").exists()

    runtime.process_inbox_once()
    entries_second = _read_jsonl(ledger)
    assert len(entries_second) == 1


def test_multiple_clock_ticks_do_not_duplicate_ledger_writes(tmp_path: Path):
    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    ledger = tmp_path / "causal_ledger.jsonl"
    lock_path = tmp_path / "locks" / "leviathan_daemon.lock"
    inbox.mkdir(parents=True, exist_ok=True)
    processed.mkdir(parents=True, exist_ok=True)
    (inbox / "event1.txt").write_text("single event under multiple ticks", encoding="utf-8")

    proc = _run_daemon(
        ledger=ledger,
        inbox=inbox,
        processed=processed,
        lock_path=lock_path,
        max_ticks=3,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert ledger.exists()
    entries = _read_jsonl(ledger)
    assert len(entries) == 1
    assert entries[0].get("event", {}).get("event_id")
    assert proc.stdout.count("[Leviathan] processed event: event1.txt") == 1
