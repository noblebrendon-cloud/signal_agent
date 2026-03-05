"""Deterministic cooperative scheduling clock for Signal Agent."""
from __future__ import annotations

import argparse
import dataclasses
import signal
import time
from pathlib import Path
from typing import Callable


TaskCallable = Callable[[], None]
ShutdownCallable = Callable[[], None]


@dataclasses.dataclass
class ClockTask:
    """Single cooperative scheduled task."""

    name: str
    interval_seconds: float
    callback: TaskCallable
    next_run_at: float
    order: int


class SystemClock:
    """
    Deterministic cooperative scheduler.

    Guarantees:
    - Stable task ordering (registration order).
    - Deterministic interval checks.
    - Missed ticks do not accumulate burst executions.
    """

    def __init__(
        self,
        *,
        resolution_seconds: float = 0.5,
        monotonic_fn: Callable[[], float] | None = None,
        sleep_fn: Callable[[float], None] | None = None,
        log_fn: Callable[[str], None] | None = None,
    ) -> None:
        if resolution_seconds <= 0.0:
            raise ValueError("resolution_seconds must be > 0")
        self.resolution_seconds = float(resolution_seconds)
        self._monotonic = monotonic_fn or time.monotonic
        self._sleep = sleep_fn or time.sleep
        self._log = log_fn or print

        self._tasks: list[ClockTask] = []
        self._shutdown_hooks: list[ShutdownCallable] = []
        self._running = False
        self._stop_requested = False
        self._next_task_order = 0
        self.tick_count = 0
        self._last_now: float | None = None

    def register_task(
        self,
        name: str,
        interval_seconds: float,
        callback: TaskCallable,
    ) -> None:
        """Register a periodic task in stable deterministic order."""
        if not name:
            raise ValueError("task name is required")
        if interval_seconds <= 0.0:
            raise ValueError("interval_seconds must be > 0")
        if any(t.name == name for t in self._tasks):
            raise ValueError(f"task already registered: {name}")

        now = self._monotonic()
        task = ClockTask(
            name=name,
            interval_seconds=float(interval_seconds),
            callback=callback,
            next_run_at=now,
            order=self._next_task_order,
        )
        self._next_task_order += 1
        self._tasks.append(task)
        self._log(f"[Clock] task registered: {name}")

    def register_shutdown_hook(self, hook: ShutdownCallable) -> None:
        """Register a deterministic shutdown callback."""
        self._shutdown_hooks.append(hook)

    def request_stop(self) -> None:
        """Request cooperative loop shutdown."""
        self._stop_requested = True

    @property
    def running(self) -> bool:
        return self._running

    def execute_due_tasks(self, now: float, *, tick_advanced: bool = True) -> None:
        """Execute due tasks once, in registration order."""
        for task in self._tasks:
            if now + 1e-12 < task.next_run_at:
                # If monotonic time stalls (same timestamp across ticks), allow
                # high-cadence tasks (<= resolution) to run once per clock tick.
                if not (not tick_advanced and task.interval_seconds <= self.resolution_seconds):
                    continue
            task.callback()
            # No burst catch-up: schedule from current time.
            task.next_run_at = now + task.interval_seconds
            if self._stop_requested:
                break

    def _shutdown(self) -> None:
        for hook in self._shutdown_hooks:
            hook()
        self._log("[Clock] stopped")

    def run(self, *, max_ticks: int | None = None) -> None:
        """Start the cooperative loop."""
        self._running = True
        self._stop_requested = False
        self._log("[Clock] started")
        try:
            while not self._stop_requested:
                prev_now = self._last_now
                now = self._monotonic()
                if self._last_now is not None and now < self._last_now:
                    self._log(
                        "[Clock] monotonicity violation: time moved backwards; refusing task execution"
                    )
                    self._stop_requested = True
                    break
                self._last_now = now
                self.tick_count += 1
                self._log(f"[Clock] tick {self.tick_count:05d}")
                tick_advanced = prev_now is None or now > prev_now
                self.execute_due_tasks(now, tick_advanced=tick_advanced)
                if max_ticks is not None and self.tick_count >= max_ticks:
                    self._stop_requested = True
                    break
                if not self._stop_requested:
                    self._sleep(self.resolution_seconds)
        except KeyboardInterrupt:
            self._stop_requested = True
        finally:
            self._running = False
            self._shutdown()


def _install_signal_handlers(clock: SystemClock) -> list[tuple[int, signal.Handlers]]:
    handlers: list[tuple[int, signal.Handlers]] = []

    def _handler(_signum: int, _frame: object) -> None:
        clock.request_stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            prev = signal.getsignal(sig)
            signal.signal(sig, _handler)
            handlers.append((sig, prev))
        except (AttributeError, ValueError):
            continue
    return handlers


def _restore_signal_handlers(handlers: list[tuple[int, signal.Handlers]]) -> None:
    for sig, prev in handlers:
        try:
            signal.signal(sig, prev)
        except (AttributeError, ValueError):
            continue


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="signal_agent.core.clock.clock")
    parser.add_argument(
        "--resolution",
        type=float,
        default=0.5,
        help="Loop sleep resolution in seconds (default: 0.5)",
    )
    parser.add_argument(
        "--ledger",
        type=str,
        default=None,
        help="Optional Leviathan ledger JSONL path",
    )
    parser.add_argument(
        "--max-ticks",
        type=int,
        default=None,
        help="Optional deterministic cap for loop ticks",
    )
    args = parser.parse_args(argv)

    clock = SystemClock(resolution_seconds=args.resolution)

    from signal_agent.leviathan.runtime.tasks import LeviathanTaskConfig, register_leviathan_tasks

    task_config = LeviathanTaskConfig(
        ledger_path=Path(args.ledger) if args.ledger else LeviathanTaskConfig().ledger_path
    )
    register_leviathan_tasks(clock=clock, config=task_config)

    handlers = _install_signal_handlers(clock)
    try:
        clock.run(max_ticks=args.max_ticks)
    finally:
        _restore_signal_handlers(handlers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
