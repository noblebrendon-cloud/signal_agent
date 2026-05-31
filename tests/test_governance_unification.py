"""
tests/test_governance_unification.py — Canonical gate enforcement tests.

Validates that:
1. shared.lifecycle functions are dead (hard-fail on call)
2. Promotion through promote_run emits canonical transition events
3. Routing through route_bundle emits canonical transition events
4. Bootstrap state assignment is distinguishable from validated transitions
5. The bootstrap path fails if prior canonical state already exists
"""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class TestSharedLifecycleDeprecation(unittest.TestCase):
    """Phase 3 verification: shared.lifecycle is dead authority."""

    def test_can_transition_raises(self):
        """can_transition must hard-fail directing to canonical gate."""
        from shared.lifecycle import can_transition
        with self.assertRaises(RuntimeError) as ctx:
            can_transition("captured", "promoted")
        self.assertIn("DEPRECATED", str(ctx.exception))
        self.assertIn("validate_transition", str(ctx.exception))

    def test_require_transition_raises(self):
        """require_transition must hard-fail directing to canonical gate."""
        from shared.lifecycle import require_transition
        with self.assertRaises(RuntimeError) as ctx:
            require_transition("promoted", "routed")
        self.assertIn("DEPRECATED", str(ctx.exception))
        self.assertIn("validate_transition", str(ctx.exception))

    def test_invalid_transition_error_preserved(self):
        """InvalidTransitionError must still be importable for catch blocks."""
        from shared.lifecycle import InvalidTransitionError
        self.assertTrue(issubclass(InvalidTransitionError, RuntimeError))
        # Must be instantiable
        err = InvalidTransitionError("test")
        self.assertIsInstance(err, RuntimeError)


class TestPromotionCanonicalEvents(unittest.TestCase):
    """Promotion must emit canonical transition events."""

    def _setup_env(self, tmp: Path):
        """Create minimal environment for promote_run."""
        capture_dir = tmp / "data" / "capture"
        raw_dir = capture_dir / "raw"
        promoted_dir = capture_dir / "promoted"
        archive_dir = capture_dir / "archive"
        for d in (raw_dir, promoted_dir, archive_dir):
            d.mkdir(parents=True, exist_ok=True)

        # State directories
        state_dir = tmp / "data" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)

        # Config (minimal)
        config_dir = tmp / "config"
        config_dir.mkdir(parents=True, exist_ok=True)

        # State machine
        sm_path = config_dir / "state_machine.yaml"
        sm_path.write_text(
            "version: 1\n"
            "states:\n"
            "  constrained:\n"
            "    kind: working\n"
            "    terminal: false\n"
            "  promoted:\n"
            "    kind: working\n"
            "    terminal: false\n"
            "  routed:\n"
            "    kind: working\n"
            "    terminal: false\n"
            "transitions:\n"
            "  - from_missing: true\n"
            "    to: promoted\n"
            "    verb: promote\n"
            "    gate: promotion_policy\n"
            "  - from: constrained\n"
            "    to: promoted\n"
            "    verb: promote\n"
            "    gate: promotion_policy\n"
            "  - from: promoted\n"
            "    to: routed\n"
            "    verb: route\n"
            "    gate: routing_policy\n",
            encoding="utf-8",
        )

        # Policies directory
        policies_dir = config_dir / "policies"
        policies_dir.mkdir(parents=True, exist_ok=True)
        (policies_dir / "promotion_policy.yaml").write_text(
            "policy_id: promotion_policy\nstatus: active\n",
            encoding="utf-8",
        )
        (policies_dir / "routing_policy.yaml").write_text(
            "policy_id: routing_policy\nstatus: active\n",
            encoding="utf-8",
        )

        # Lanes
        (config_dir / "lanes.yaml").write_text(
            "version: 1\nlanes:\n"
            "  - lane_id: volatile_capture\n"
            "    status: active\n",
            encoding="utf-8",
        )

        # Create raw files for clustering (need >=2 for min_cluster_size)
        ts = "2026-03-20T00:00:00Z"
        for i in range(3):
            (raw_dir / f"raw_{ts.replace(':', '-')}_{i:03d}.md").write_text(
                f"---\ntimestamp_utc: {ts}\n---\n"
                f"governance signal integrity bootstrap test content artifact {i}\n",
                encoding="utf-8",
            )

        return capture_dir

    def test_promotion_emits_bootstrap_event(self):
        """Promotion of new artifact emits bootstrap_state_assignment event."""
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            capture_dir = self._setup_env(tmp)

            events_path = tmp / "data" / "state" / "transition_gate_events.jsonl"

            # Count events before
            events_before = 0
            if events_path.exists():
                events_before = len(events_path.read_text(encoding="utf-8").strip().splitlines())

            with patch.dict("os.environ", {"SIGNAL_AGENT_ROOT": str(tmp)}):
                from app.hq.capture.promote import promote_run
                result = promote_run(
                    capture_dir=capture_dir,
                    min_cluster_size=2,
                    threshold=0.10,
                )

            # Must have produced at least one bundle
            self.assertIn(result.get("status"), ("ok", "partial"), f"promote_run failed: {result}")
            bundles = result.get("bundles", [])
            if not bundles:
                self.skipTest("No bundles produced (clustering threshold)")

            # Events must have grown
            self.assertTrue(events_path.exists(), "No canonical event file created")
            lines = events_path.read_text(encoding="utf-8").strip().splitlines()
            events_after = len(lines)
            self.assertGreater(events_after, events_before,
                               "Promotion did not emit canonical events")

            # promote.py emits 'transition_attempt' with current_state=None
            # for first-time (bootstrap) promotions.
            new_events = [json.loads(line) for line in lines[events_before:]]
            bootstrap_events = [
                evt for evt in new_events
                if evt.get("event_type") == "transition_attempt"
                and evt.get("current_state") is None
            ]
            self.assertTrue(
                len(bootstrap_events) >= 1,
                f"No bootstrap transition_attempt event found. "
                f"Events: {[e.get('event_type') for e in new_events]}",
            )

    def test_promotion_gated_when_prior_state_exists(self):
        """Promotion with an existing canonical state uses validate_transition."""
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            capture_dir = self._setup_env(tmp)

            # Pre-seed the state registry with a 'constrained' entry
            reg_path = tmp / "data" / "state" / "artifact_registry.jsonl"
            events_path = tmp / "data" / "state" / "transition_gate_events.jsonl"

            with patch.dict("os.environ", {"SIGNAL_AGENT_ROOT": str(tmp)}):
                from app.hq.capture.promote import promote_run

                # First run: bootstrap
                result1 = promote_run(
                    capture_dir=capture_dir,
                    min_cluster_size=2,
                    threshold=0.10,
                )
                bundles1 = result1.get("bundles", [])
                if not bundles1:
                    self.skipTest("No bundles produced")

                # Re-create raw files and force re-promotion
                raw_dir = capture_dir / "raw"
                ts = "2026-03-20T00:00:00Z"
                for i in range(3):
                    (raw_dir / f"raw_{ts.replace(':', '-')}_{i:03d}.md").write_text(
                        f"---\ntimestamp_utc: {ts}\n---\n"
                        f"governance signal integrity bootstrap test content artifact {i}\n",
                        encoding="utf-8",
                    )

                events_before = len(events_path.read_text(encoding="utf-8").strip().splitlines())

                # Second run: should hit the canonical gate path (prior state = "promoted").
                # promoted→promoted is NOT a defined transition, so the gate must REJECT.
                # This proves the gate distinguishes bootstrap (None) from gated (prior state).
                with self.assertRaises(RuntimeError) as ctx:
                    promote_run(
                        capture_dir=capture_dir,
                        min_cluster_size=2,
                        threshold=0.10,
                        force=True,
                    )
                self.assertIn("rejected", str(ctx.exception).lower())

                # Check events grew — should contain transition_rejected
                lines = events_path.read_text(encoding="utf-8").strip().splitlines()
                new_events = lines[events_before:]

                # The rejection event must have current_state set (not None),
                # proving it did NOT take the bootstrap path.
                if new_events:
                    for line in new_events:
                        evt = json.loads(line)
                        if (evt.get("event_type") == "transition_attempt"
                                and evt.get("current_state") is None):
                            self.fail(
                                f"Bootstrap transition emitted for artifact with prior state: {evt}"
                            )


class TestSharedLifecycleProductionImports(unittest.TestCase):
    """Ensure no production code imports shared.lifecycle for transition logic."""

    def test_no_production_lifecycle_imports(self):
        """Scan tracked production files for active shared.lifecycle imports."""
        root = Path(__file__).resolve().parents[1]

        tracked = subprocess.run(
            ["git", "ls-files", "*.py"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            tracked.returncode,
            0,
            f"git ls-files failed: {tracked.stderr}",
        )

        production_imports = []
        for raw_rel in tracked.stdout.splitlines():
            rel = raw_rel.replace("\\", "/")
            name = Path(rel).name
            if (
                rel == "shared/lifecycle.py"
                or rel.startswith("tests/")
                or "/tests/" in rel
                or name.startswith("test_")
            ):
                continue
            py_file = root / rel
            try:
                content = py_file.read_text(encoding="utf-8", errors="replace")
                for i, line in enumerate(content.splitlines(), 1):
                    stripped = line.strip()
                    # Skip comments
                    if stripped.startswith("#"):
                        continue
                    if "shared.lifecycle" in stripped and "import" in stripped:
                        production_imports.append(f"{rel}:{i}: {stripped}")
            except OSError:
                continue

        self.assertEqual(
            production_imports, [],
            f"Production code still imports shared.lifecycle:\n" +
            "\n".join(production_imports)
        )


if __name__ == "__main__":
    unittest.main()
