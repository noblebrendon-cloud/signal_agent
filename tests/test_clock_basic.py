from __future__ import annotations

import unittest

from signal_agent.core.clock.clock import SystemClock


class _FakeTime:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += float(seconds)


class _SequenceMonotonic:
    def __init__(self, values: list[float]) -> None:
        self._values = list(values)
        self._index = 0

    def monotonic(self) -> float:
        if self._index >= len(self._values):
            return self._values[-1]
        value = self._values[self._index]
        self._index += 1
        return value


class TestSystemClockBasic(unittest.TestCase):
    def test_task_executes_expected_count(self) -> None:
        fake = _FakeTime()
        calls: list[int] = []
        logs: list[str] = []
        clock = SystemClock(
            resolution_seconds=0.5,
            monotonic_fn=fake.monotonic,
            sleep_fn=fake.sleep,
            log_fn=logs.append,
        )
        clock.register_task("task_a", 1.0, lambda: calls.append(clock.tick_count))
        clock.run(max_ticks=6)

        # Runs at t=0.0, 1.0, 2.0 with 0.5 resolution and max_ticks=6.
        self.assertEqual(len(calls), 3)

    def test_deterministic_ordering_preserved(self) -> None:
        fake = _FakeTime()
        order: list[str] = []
        clock = SystemClock(
            resolution_seconds=0.5,
            monotonic_fn=fake.monotonic,
            sleep_fn=fake.sleep,
            log_fn=lambda _: None,
        )
        clock.register_task("alpha", 1.0, lambda: order.append("alpha"))
        clock.register_task("beta", 1.0, lambda: order.append("beta"))
        clock.run(max_ticks=3)

        # tick 1 and tick 3 are due for both tasks.
        self.assertEqual(order, ["alpha", "beta", "alpha", "beta"])

    def test_shutdown_clean_runs_hooks(self) -> None:
        fake = _FakeTime()
        hooks: list[str] = []
        clock = SystemClock(
            resolution_seconds=0.5,
            monotonic_fn=fake.monotonic,
            sleep_fn=fake.sleep,
            log_fn=lambda _: None,
        )

        def _stopper() -> None:
            clock.request_stop()

        clock.register_task("stopper", 0.5, _stopper)
        clock.register_shutdown_hook(lambda: hooks.append("flushed"))
        clock.run()

        self.assertEqual(hooks, ["flushed"])
        self.assertFalse(clock.running)

    def test_missed_ticks_do_not_accumulate_bursts(self) -> None:
        fake = _FakeTime()
        calls: list[int] = []
        clock = SystemClock(
            resolution_seconds=2.5,
            monotonic_fn=fake.monotonic,
            sleep_fn=fake.sleep,
            log_fn=lambda _: None,
        )
        clock.register_task("burst_guard", 1.0, lambda: calls.append(clock.tick_count))
        clock.run(max_ticks=3)

        # Even with large resolution, each loop iteration executes task at most once.
        self.assertEqual(len(calls), 3)

    def test_monotonicity_violation_stops_execution(self) -> None:
        seq = _SequenceMonotonic([1.0, 1.0, 0.5])
        calls: list[int] = []
        logs: list[str] = []
        clock = SystemClock(
            resolution_seconds=0.1,
            monotonic_fn=seq.monotonic,
            sleep_fn=lambda _seconds: None,
            log_fn=logs.append,
        )
        clock.register_task("guarded", 0.1, lambda: calls.append(clock.tick_count))
        clock.run()

        self.assertEqual(len(calls), 1)
        self.assertTrue(any("monotonicity violation" in line for line in logs))


if __name__ == "__main__":
    unittest.main()
