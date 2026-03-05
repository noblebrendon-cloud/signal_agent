"""Tests for cli/summarize_ledger.py (v0.5)."""
import unittest
import sys, pathlib, tempfile, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent.parent.parent))

from signal_agent.leviathan.interaction_signals.cli.summarize_ledger import main

class TestSummarizeLedger(unittest.TestCase):
    def setUp(self):
        self._tmp_root = pathlib.Path(".tmp") / "temp"
        self._tmp_root.mkdir(parents=True, exist_ok=True)
        self.tmp_dir = tempfile.TemporaryDirectory(dir=str(self._tmp_root))
        self.ledger_path = pathlib.Path(self.tmp_dir.name) / "test_ledger.jsonl"

    def tearDown(self):
        self.tmp_dir.cleanup()

    def _write_ledger(self, records: list[dict]):
        with self.ledger_path.open("w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

    def test_main_runs_without_crashing_on_valid_ledger(self):
        records = [
            {
                "event": {"thread_id": "t1", "actor_id": "a1", "timestamp": "2026"},
                "phase_region": "stable_high_leverage",
                "actor_after": {
                    "transition_matrix": {
                        "COGNITIVE_HONESTY": {"TRANSACTION": 0.4, "COGNITIVE_HONESTY": 0.6}
                    },
                    "mode_volatility_30": 0.5
                },
                "dyad_after": {
                    "self_actor_id": "self",
                    "other_actor_id": "a1",
                    "working_pair_score": 0.8,
                    "asymmetry_penalty": 0.1,
                    "extraction_penalty": 0.0
                },
                "policy_action": {
                    "notes": ["v_spike: sudden divergence"]
                }
            },
            {
                "event": {"thread_id": "t1", "actor_id": "a2", "timestamp": "2026"},
                "phase_region": "unstable_high_leverage"
            }
        ]
        self._write_ledger(records)
        
        # Test basic deterministic run
        ret = main(["--ledger", str(self.ledger_path)])
        self.assertEqual(ret, 0)
        
        # Test CSV export
        csv_prefix = str(pathlib.Path(self.tmp_dir.name) / "out")
        ret_csv = main(["--ledger", str(self.ledger_path), "--csv-out", csv_prefix])
        self.assertEqual(ret_csv, 0)
        
        # Verify CSVs were created
        self.assertTrue((pathlib.Path(self.tmp_dir.name) / "out_actors.csv").exists())
        self.assertTrue((pathlib.Path(self.tmp_dir.name) / "out_dyads.csv").exists())

    def test_missing_ledger_fails_gracefully(self):
        bad_path = str(pathlib.Path(self.tmp_dir.name) / "does_not_exist.jsonl")
        ret = main(["--ledger", bad_path])
        self.assertEqual(ret, 1)

if __name__ == "__main__":
    unittest.main()
