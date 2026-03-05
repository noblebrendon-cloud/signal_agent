from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _run_daemon_once(ledger: Path, inbox: Path, processed: Path) -> subprocess.CompletedProcess[str]:
    lock_path = inbox.parent / "locks" / "leviathan_daemon.lock"
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
            "--interval",
            "0",
            "--once",
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_daemon_once_appends_ledger_and_moves_file(tmp_path: Path):
    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    ledger = tmp_path / "causal_ledger.jsonl"
    inbox.mkdir(parents=True, exist_ok=True)
    processed.mkdir(parents=True, exist_ok=True)

    event_file = inbox / "event1.txt"
    event_file.write_text("incident interpretation drift detected", encoding="utf-8")
    size_before = ledger.stat().st_size if ledger.exists() else 0

    proc = _run_daemon_once(ledger=ledger, inbox=inbox, processed=processed)
    assert proc.returncode == 0, proc.stderr
    assert "[Leviathan] runtime authority acquired" in proc.stdout
    assert "[Leviathan] clock initialized" in proc.stdout
    assert "[Leviathan] tasks registered" in proc.stdout
    assert "[Leviathan] entering governed execution" in proc.stdout
    assert "[Leviathan] processed event: event1.txt" in proc.stdout
    assert "[Leviathan] ledger append ok" in proc.stdout

    assert ledger.exists()
    assert ledger.stat().st_size > size_before
    assert not event_file.exists()
    assert (processed / "event1.txt").exists()

    lines = [line for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) >= 1
    entry = json.loads(lines[-1])
    assert entry.get("event", {}).get("event_id")
    assert entry.get("event", {}).get("timestamp")


def test_daemon_once_processes_sorted_filenames(tmp_path: Path):
    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    ledger = tmp_path / "causal_ledger.jsonl"
    inbox.mkdir(parents=True, exist_ok=True)
    processed.mkdir(parents=True, exist_ok=True)

    (inbox / "b_event.txt").write_text("second", encoding="utf-8")
    (inbox / "a_event.txt").write_text("first", encoding="utf-8")

    proc = _run_daemon_once(ledger=ledger, inbox=inbox, processed=processed)
    assert proc.returncode == 0, proc.stderr

    processed_lines = [
        line for line in proc.stdout.splitlines() if line.startswith("[Leviathan] processed event:")
    ]
    assert processed_lines == [
        "[Leviathan] processed event: a_event.txt",
        "[Leviathan] processed event: b_event.txt",
    ]
