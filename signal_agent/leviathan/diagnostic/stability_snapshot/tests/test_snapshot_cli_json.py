import unittest
import subprocess
import json
import sys
import tempfile
import os
from pathlib import Path

class TestSnapshotCliJson(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parent.parent.parent.parent.parent
        self.env = os.environ.copy()
        self.env["PYTHONPATH"] = str(self.repo_root)

    def run_cli(self, args):
        cmd = [sys.executable, "-m", "signal_agent.leviathan.diagnostic.stability_snapshot.cli", "snapshot"] + args
        return subprocess.run(cmd, capture_output=True, text=True, env=self.env)
        
    def test_golden_fixture_equality(self):
        answers = "1,0,1,0,1,0,1,0,1,0,1,0,1,0,1"
        res = self.run_cli(["--answers", answers, "--json"])
        self.assertEqual(res.returncode, 0)
        
        golden_path = Path(__file__).resolve().parent / "fixtures" / "golden_snapshot.json"
        
        self.assertTrue(golden_path.exists(), f"Golden fixture missing at {golden_path}")
        golden_data = json.loads(golden_path.read_text(encoding="utf-8"))
        test_data = json.loads(res.stdout)
        
        self.assertEqual(golden_data, test_data, "Snapshot output drifted from golden fixture block")
        
    def test_json_stable_across_runs(self):
        answers = "1,0,1,0,1,0,1,0,1,0,1,0,1,0,1"
        res1 = self.run_cli(["--answers", answers, "--json"])
        self.assertEqual(res1.returncode, 0, f"Failed execution: {res1.stderr}")
        
        res2 = self.run_cli(["--answers", answers, "--json"])
        self.assertEqual(res2.returncode, 0)
        
        self.assertEqual(res1.stdout, res2.stdout, "JSON output should be perfectly deterministic")
        
        parsed = json.loads(res1.stdout)
        self.assertIn("score", parsed)
        self.assertIn("interpretation", parsed)
        
    def test_identical_input_identical_output(self):
        answers = "1,1,1,1,1,1,1,1,1,1,1,1,1,1,1"
        res1 = self.run_cli(["--answers", answers, "--json"])
        
        with tempfile.TemporaryDirectory() as td:
            res2 = self.run_cli(["--answers", answers, "--json", "--out-dir", td])
            self.assertEqual(res2.returncode, 0)
            
            out_file = Path(td) / "snapshot_result.json"
            self.assertTrue(out_file.exists())
            
            file_content = out_file.read_text(encoding="utf-8")
            s1 = json.loads(res1.stdout)
            s2 = json.loads(file_content)
            self.assertEqual(s1, s2)
            
    def test_invalid_answer_count_rejected(self):
        res = self.run_cli(["--answers", "1,1,1"])
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("Error: expected", res.stderr)
        
class TestCausalLedgerCli(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parent.parent.parent.parent.parent
        self.env = os.environ.copy()
        self.env["PYTHONPATH"] = str(self.repo_root)

    def run_cli(self, args):
        cmd = [sys.executable, "-m", "signal_agent.leviathan.diagnostic.stability_snapshot.cli", "init-ledger"] + args
        return subprocess.run(cmd, capture_output=True, text=True, env=self.env)
        
    def test_init_ledger_deterministic(self):
        with tempfile.TemporaryDirectory() as td:
            res = self.run_cli(["INC123", "--out-dir", td, "--now", "2026-03-01T00:00:00Z"])
            self.assertEqual(res.returncode, 0, f"Fail: {res.stderr}\n{res.stdout}")
            
            out_file = Path(td) / "INC123_causal_ledger.json"
            self.assertTrue(out_file.exists())
            
            data = json.loads(out_file.read_text(encoding="utf-8"))
            self.assertEqual(data["incident_or_change_id"], "INC123")
            self.assertEqual(data["timestamp"], "2026-03-01T00:00:00Z")
            
    def test_init_ledger_prevents_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            res1 = self.run_cli(["INC123", "--out-dir", td, "--now", "2026-03-01T00:00:00Z"])
            self.assertEqual(res1.returncode, 0)
            
            res2 = self.run_cli(["INC123", "--out-dir", td, "--now", "2026-03-02T00:00:00Z"])
            self.assertEqual(res2.returncode, 1)
            self.assertIn("overwrite prevented", res2.stdout)
            
            out_file = Path(td) / "INC123_causal_ledger.json"
            data = json.loads(out_file.read_text(encoding="utf-8"))
            self.assertEqual(data["timestamp"], "2026-03-01T00:00:00Z")

if __name__ == '__main__':
    unittest.main()
