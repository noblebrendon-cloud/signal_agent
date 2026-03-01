from __future__ import annotations

import argparse
import contextlib
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.pipeline.contract_evaluator import evaluate_cycle


class SystemHalt(Exception):
    pass


class FileLock:
    def __init__(self, lock_path: Path, stale_after_s: int = 3600) -> None:
        self.lock_path = lock_path
        self.stale_after_s = stale_after_s
        self._fd: int | None = None

    def acquire(self) -> tuple[bool, str | None]:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        if self.lock_path.exists():
            try:
                if time.time() - self.lock_path.stat().st_mtime > self.stale_after_s:
                    self.lock_path.unlink(missing_ok=True)
            except Exception:
                return (False, "lock_unavailable")
        try:
            fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            self._fd = fd
            os.write(fd, f"pid={os.getpid()} utc={datetime.now(timezone.utc).isoformat()}\n".encode("utf-8"))
            return (True, None)
        except Exception:
            return (False, "lock_held")

    def release(self) -> None:
        try:
            if self._fd is not None:
                os.close(self._fd)
        finally:
            self._fd = None
            try:
                self.lock_path.unlink(missing_ok=True)
            except Exception:
                pass


@contextlib.contextmanager
def _clock_lock():
    lock = FileLock(Path("data/state/clock.lock"))
    acquired, _ = lock.acquire()
    try:
        yield acquired
    finally:
        if acquired:
            lock.release()


def _governor_allows(governor: Any, scope: str) -> bool:
    if hasattr(governor, "enforce"):
        decision = governor.enforce(scope=scope)
        if isinstance(decision, dict):
            return str(decision.get("decision", "")).upper() == "ALLOW"
        return bool(decision)
    return True


def tick_once(
    kernel: Any,
    governor: Any,
    breaker_store: Any,
    contract_path: Path = Path("task_contract.yaml"),
) -> str:
    """
    Canonical boundary for single tick.
    Gate order: Lock -> Governor -> Kernel -> Breaker -> Evaluate
    """
    with _clock_lock() as acquired:
        if not acquired:
            return "NO_OP_OVERLAP_LOCK"

        if not _governor_allows(governor, "daemon.tick"):
            return "NO_OP_GOVERNOR_LOCKED"

        snap = kernel.snapshot()
        regime = getattr(snap, "regime", None)
        if str(regime).endswith("FAILURE") or str(regime).upper() == "FAILURE":
            raise SystemHalt("Kernel regime FAILURE: hard stop")

        required = getattr(breaker_store, "required_breakers", lambda: [])()
        if not required and hasattr(breaker_store, "get_state"):
            required = ["default"]

        for name in required:
            state = breaker_store.get_state(name)
            str_state = str(state.get("state") if isinstance(state, dict) else state).upper()
            if str_state == "OPEN":
                return "NO_OP_BREAKER_OPEN"

        evaluate_cycle(contract_path=contract_path, kernel_snap=snap)
        return "SUCCESS"


def tick(*args, **kwargs) -> Any:
    return tick_once(*args, **kwargs)


def _build_default_kernel_governor_breakers() -> tuple[Any, Any, Any]:
    from app.audit.coherence_kernel import CoherenceKernel  # type: ignore
    from app.governor import activation_governor as governor  # type: ignore
    from app.utils.breaker_store_sqlite import SqliteBreakerStore  # type: ignore

    kernel = CoherenceKernel()
    breaker_store = SqliteBreakerStore(Path("data/state/breaker_store.sqlite"))
    return kernel, governor, breaker_store


def run_loop(interval_s: int = 60) -> None:
    kernel, governor, breaker_store = _build_default_kernel_governor_breakers()
    while True:
        try:
            tick_once(kernel, governor, breaker_store)
        except SystemHalt:
            return
        time.sleep(max(1, interval_s))


def main() -> int:
    parser = argparse.ArgumentParser(prog="clock")
    parser.add_argument("--tick-only", action="store_true", help="Run one tick and exit")
    parser.add_argument("--interval", type=int, default=60, help="Loop interval (seconds)")
    args = parser.parse_args()

    if args.tick_only:
        kernel, governor, breaker_store = _build_default_kernel_governor_breakers()
        try:
            tick_once(kernel, governor, breaker_store)
        except SystemHalt:
            pass
        return 0

    run_loop(args.interval)
    return 0


if __name__ == "__main__":
    sys.exit(main())
