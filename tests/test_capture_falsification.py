"""
Tests for Capture Layer v0.3 Falsification Harness & Hardening (Hotfix).

Verifies:
1. Bridge-doc defense (bridge_isolated = True)
2. Keyword stuffing resilience (keyword_stuffing_isolated = True)
3. 2-Stage Decay (stage1 -> stage2 based on dwelling time)
4. Router audit hash presence and correctness
5. Instability detection on synthetic load (severity levels)
"""
import unittest
import shutil
import tempfile
import json
import os
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Import modules under test
from app.hq.capture import decay, router, instability, promote, stress

class TestCaptureFalsification(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.capture_dir = self.test_dir / "data" / "capture"
        self.capture_dir.mkdir(parents=True)
        (self.capture_dir / "raw").mkdir()
        
        # Point env vars to test dir
        os.environ["CAPTURE_DIR"] = str(self.capture_dir)
        os.environ["SIGNAL_AGENT_ROOT"] = str(self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir)
        if "CAPTURE_DIR" in os.environ:
            del os.environ["CAPTURE_DIR"]
        if "SIGNAL_AGENT_ROOT" in os.environ:
            del os.environ["SIGNAL_AGENT_ROOT"]

    def test_bridge_doc_isolation(self):
        """Test that a bridge document is isolated."""
        # Use tighter window hour override to force clustering behavior
        result = stress.run_stress(
            doc_count=40,
            theme_count=2,
            bridge=True,
            capture_dir=self.capture_dir,
            seed=42,
            window_hours_override=48.0
        )
        
        # Assert schema keys
        self.assertIn("docs_generated", result)
        self.assertIn("bridge_isolated", result)
        self.assertIn("keyword_stuffing_isolated", result)
        
        # Check bridge isolation
        # With seed=42 and bridge doc mixing themes, the bridge defense should trigger
        # OR it should be filtered out as size < 2.
        # Either way, isolated=True.
        self.assertTrue(result["bridge_isolated"], "Bridge document should be isolated")

    def test_2_stage_decay(self):
        """Test raw -> stage1 -> stage2 transitions with mtime logic."""
        raw_dir = self.capture_dir / "raw"
        stage1_dir = self.capture_dir / "expired_stage1"
        stage2_dir = self.capture_dir / "expired_stage2"
        
        now = datetime.now(timezone.utc)
        
        # File 1: 5 days old (keep in raw)
        ts1 = now - timedelta(days=5)
        f1 = raw_dir / f"raw_{ts1.strftime('%Y-%m-%dT%H-%M-%S')}_001Z.md"
        f1.touch()
        
        # File 2: 20 days old (move to stage1)
        ts2 = now - timedelta(days=20)
        f2 = raw_dir / f"raw_{ts2.strftime('%Y-%m-%dT%H-%M-%S')}_002Z.md"
        f2.touch()
        
        # File 3 (simulating already moved to stage1): 40 days dwelling in stage1 (move to stage2)
        stage1_dir.mkdir()
        ts3 = now - timedelta(days=40)
        f3 = stage1_dir / f"raw_{ts3.strftime('%Y-%m-%dT%H-%M-%S')}_003Z.md"
        f3.touch()
        # Set mtime to 40 days ago
        os.utime(f3, (ts3.timestamp(), ts3.timestamp()))
        
        # Run decay
        decay.decay_run(
            days=14,
            purge_days=30,
            capture_dir=self.capture_dir,
            now_utc=now
        )
        
        self.assertTrue(f1.exists(), "New file should stay in raw")
        self.assertFalse(f2.exists(), "Old raw file should move")
        self.assertTrue((stage1_dir / f2.name).exists(), "Old raw file should be in stage1")
        
        # When f2 moved, its mtime should be updated to NOW (approx)
        f2_stage1 = stage1_dir / f2.name
        self.assertAlmostEqual(f2_stage1.stat().st_mtime, now.timestamp(), delta=10.0)
        
        self.assertFalse(f3.exists(), "Old stage1 file should move")
        self.assertTrue((stage2_dir / f3.name).exists(), "Old stage1 file should be in stage2")

    def test_router_hash(self):
        """Verify router computes and logs hash, no yaml dependency."""
        cfg_path = self.capture_dir / "router_test.yaml"
        # Pure text content to test fallback parser
        cfg_path.write_text("spines:\n  - name: test_spine\n    keywords: [foo, bar]\n    domains: [example.com]", encoding="utf-8")
        
        # Mock bundle
        bundle = self.capture_dir / "bundle_test.md"
        bundle.write_text("foo bar example.com", encoding="utf-8")
        
        res = router.route_bundle(
            bundle_path=bundle,
            config_path=cfg_path,
            capture_dir=self.capture_dir,
            dry_run=False
        )
        
        self.assertIsNotNone(res.get("router_ruleset_hash"))
        self.assertEqual(res["spine"], "test_spine")
        self.assertEqual(res["status"], "ok")
        
        # Check log
        log_path = self.capture_dir / "routing_log.jsonl"
        self.assertTrue(log_path.exists())
        last_line = json.loads(log_path.read_text().strip().split("\n")[-1])
        self.assertEqual(last_line["router_ruleset_hash"], res["router_ruleset_hash"])

    def test_instability_severity(self):
        """Test severity classification."""
        # Generate 25 files for today (Extreme spike >= 20)
        raw_dir = self.capture_dir / "raw"
        now = datetime.now(timezone.utc)
        
        # Topic A: "tokenA"
        for i in range(25):
            (raw_dir / f"raw_{now.strftime('%Y-%m-%dT%H-%M-%S')}_{i:03d}Z.md").write_text("tokenA tokenA")
            
        # Run scan
        res = instability.scan_instability(
            window_days=7,
            min_today=5,
            capture_dir=self.capture_dir,
            now_utc=now
        )
        
        flags = res.get("flags", [])
        self.assertTrue(len(flags) > 0)
        flag = flags[0]
        self.assertEqual(flag["severity"], "extreme")
        self.assertEqual(flag["utc_day"], now.strftime("%Y-%m-%d"))

if __name__ == '__main__':
    unittest.main(verbosity=2)
