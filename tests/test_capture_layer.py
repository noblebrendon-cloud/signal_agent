"""
Tests for Capture Layer — volatile intake + promotion.

5 test classes:
1. test_capture_creates_file_and_logs
2. test_capture_does_not_touch_artifact_registry
3. test_promote_creates_bundle_from_similar_inputs
4. test_promote_logs_lineage
5. test_promote_resumable_no_duplicate_bundle
"""
from __future__ import annotations

import json
import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.hq.capture.capture import capture_add, capture_status
from app.hq.capture.promote import promote_run


class TestCaptureCreatesFileAndLogs(unittest.TestCase):
    """1) capture_add writes a raw file + appends telemetry."""

    def setUp(self):
        import tempfile
        self.tmpdir = Path(tempfile.mkdtemp())
        self.capture_dir = self.tmpdir / "capture"
        (self.capture_dir / "raw").mkdir(parents=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_text_capture(self):
        result = capture_add(
            text="Test note about deterministic systems",
            capture_dir=self.capture_dir,
        )
        self.assertIn("filename", result)
        self.assertTrue(result["filename"].startswith("raw_"))
        self.assertTrue(result["filename"].endswith(".md"))

        # File exists
        out_path = Path(result["path"])
        self.assertTrue(out_path.exists())

        # Content has frontmatter
        content = out_path.read_text(encoding="utf-8")
        self.assertIn("---", content)
        self.assertIn("input_type: text", content)
        self.assertIn("Test note about deterministic", content)

    def test_telemetry_logged(self):
        capture_add(text="Telemetry test", capture_dir=self.capture_dir)

        log_path = self.capture_dir / "capture_log.jsonl"
        self.assertTrue(log_path.exists())

        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        self.assertEqual(len(lines), 1)
        entry = json.loads(lines[0])
        self.assertEqual(entry["input_type"], "text")
        self.assertIn("filename", entry)
        self.assertEqual(entry["length"], len("Telemetry test"))

    def test_url_capture(self):
        result = capture_add(
            url="https://example.com/article",
            capture_dir=self.capture_dir,
        )
        content = Path(result["path"]).read_text(encoding="utf-8")
        self.assertIn("input_type: url", content)
        self.assertIn("https://example.com/article", content)

    def test_empty_input_creates_placeholder(self):
        result = capture_add(capture_dir=self.capture_dir)
        content = Path(result["path"]).read_text(encoding="utf-8")
        self.assertIn("[empty capture", content)


class TestCaptureDoesNotTouchArtifactRegistry(unittest.TestCase):
    """2) Capture layer NEVER modifies artifact_registry.jsonl."""

    def test_no_registry_modification(self):
        import tempfile
        import shutil

        tmpdir = Path(tempfile.mkdtemp())
        capture_dir = tmpdir / "capture"
        (capture_dir / "raw").mkdir(parents=True)

        # Create a fake registry and record its state
        registry = tmpdir / "artifact_registry.jsonl"
        registry.write_text('{"test":"sentinel"}\n', encoding="utf-8")
        original = registry.read_bytes()

        try:
            # Perform multiple captures
            for i in range(5):
                capture_add(
                    text=f"Test note {i}",
                    capture_dir=capture_dir,
                )

            # Registry must be untouched
            self.assertEqual(registry.read_bytes(), original)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestPromoteCreatesBundleFromSimilarInputs(unittest.TestCase):
    """3) promote_run clusters similar inputs into a bundle."""

    def setUp(self):
        import tempfile
        self.tmpdir = Path(tempfile.mkdtemp())
        self.capture_dir = self.tmpdir / "capture"
        (self.capture_dir / "raw").mkdir(parents=True)
        (self.capture_dir / "promoted").mkdir(parents=True)
        (self.capture_dir / "archive").mkdir(parents=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _create_raw(self, filename: str, body: str) -> None:
        path = self.capture_dir / "raw" / filename
        content = (
            "---\n"
            "timestamp_utc: 2026-02-16T18:00:00Z\n"
            "input_type: text\n"
            "source: null\n"
            "---\n\n" + body + "\n"
        )
        path.write_text(content, encoding="utf-8")

    @patch("app.hq.capture.promote._try_curate", return_value=(False, None))
    def test_similar_docs_cluster(self, _mock_curate):
        # Create similar docs about the same topic
        self._create_raw("raw_2026-02-16T18-00-01_001Z.md",
                         "Machine learning models improve signal detection. "
                         "Neural networks process patterns effectively. "
                         "https://ml.example.com/paper")
        self._create_raw("raw_2026-02-16T18-00-02_002Z.md",
                         "Machine learning advances in signal processing. "
                         "Pattern detection using neural networks. "
                         "https://ml.example.com/advances")

        result = promote_run(
            threshold=0.1,
            min_cluster_size=2,
            capture_dir=self.capture_dir,
        )

        self.assertEqual(result["status"], "ok")
        self.assertGreaterEqual(result["clusters"], 1)
        self.assertGreaterEqual(len(result["bundles"]), 1)

        # Bundle file exists (mock prevents curate from moving it)
        promoted = list((self.capture_dir / "promoted").glob("bundle_*.md"))
        self.assertGreaterEqual(len(promoted), 1)

        # Bundle content includes both files
        bundle_content = promoted[0].read_text(encoding="utf-8")
        self.assertIn("raw_2026-02-16T18-00-01_001Z.md", bundle_content)
        self.assertIn("raw_2026-02-16T18-00-02_002Z.md", bundle_content)

    def test_dissimilar_docs_stay_separate(self):
        self._create_raw("raw_2026-02-16T18-00-01_001Z.md",
                         "Quantum computing breakthrough in cryptography")
        self._create_raw("raw_2026-02-16T18-00-02_002Z.md",
                         "Gardening tips for spring vegetables and herbs")

        result = promote_run(
            threshold=0.5,
            min_cluster_size=2,
            capture_dir=self.capture_dir,
        )

        # No viable clusters (each is size 1)
        self.assertEqual(result["clusters"], 0)

    def test_dry_run_no_bundle_created(self):
        self._create_raw("raw_2026-02-16T18-00-01_001Z.md",
                         "Signal processing deterministic outputs")
        self._create_raw("raw_2026-02-16T18-00-02_002Z.md",
                         "Signal processing deterministic results")

        result = promote_run(
            threshold=0.1,
            min_cluster_size=2,
            dry_run=True,
            capture_dir=self.capture_dir,
        )

        self.assertEqual(result["status"], "dry_run")
        # No actual files created
        promoted = list((self.capture_dir / "promoted").glob("bundle_*.md"))
        self.assertEqual(len(promoted), 0)


class TestPromoteLogsLineage(unittest.TestCase):
    """4) promote_run appends lineage to promotion_log.jsonl."""

    def setUp(self):
        import tempfile
        self.tmpdir = Path(tempfile.mkdtemp())
        self.capture_dir = self.tmpdir / "capture"
        (self.capture_dir / "raw").mkdir(parents=True)
        (self.capture_dir / "promoted").mkdir(parents=True)
        (self.capture_dir / "archive").mkdir(parents=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _create_raw(self, filename: str, body: str) -> None:
        path = self.capture_dir / "raw" / filename
        content = (
            "---\ntimestamp_utc: 2026-02-16T18:00:00Z\n"
            "input_type: text\nsource: null\n---\n\n" + body + "\n"
        )
        path.write_text(content, encoding="utf-8")

    def test_lineage_logged(self):
        self._create_raw("raw_2026-02-16T18-00-01_001Z.md",
                         "Deterministic capture systems use hashing for integrity")
        self._create_raw("raw_2026-02-16T18-00-02_002Z.md",
                         "Deterministic capture and hashing ensure integrity")

        promote_run(
            threshold=0.1,
            min_cluster_size=2,
            capture_dir=self.capture_dir,
        )

        log_path = self.capture_dir / "promotion_log.jsonl"
        self.assertTrue(log_path.exists())

        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        self.assertGreaterEqual(len(lines), 1)

        entry = json.loads(lines[0])
        self.assertIn("cluster_id", entry)
        self.assertIn("bundle_filename", entry)
        self.assertIn("raw_files", entry)
        self.assertIn("strategy", entry)
        self.assertEqual(entry["strategy"], "hybrid")
        self.assertIn("status", entry)


class TestPromoteResumableNoDuplicateBundle(unittest.TestCase):
    """5) Running promote twice does not create duplicate bundles."""

    def setUp(self):
        import tempfile
        self.tmpdir = Path(tempfile.mkdtemp())
        self.capture_dir = self.tmpdir / "capture"
        (self.capture_dir / "raw").mkdir(parents=True)
        (self.capture_dir / "promoted").mkdir(parents=True)
        (self.capture_dir / "archive").mkdir(parents=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _create_raw(self, filename: str, body: str) -> None:
        path = self.capture_dir / "raw" / filename
        content = (
            "---\ntimestamp_utc: 2026-02-16T18:00:00Z\n"
            "input_type: text\nsource: null\n---\n\n" + body + "\n"
        )
        path.write_text(content, encoding="utf-8")

    @patch("app.hq.capture.promote._try_curate", return_value=(False, None))
    def test_no_duplicate_bundles(self, _mock_curate):
        self._create_raw("raw_2026-02-16T18-00-01_001Z.md",
                         "Volatile capture layer design patterns")
        self._create_raw("raw_2026-02-16T18-00-02_002Z.md",
                         "Volatile capture design and layer patterns")

        # Run 1
        r1 = promote_run(
            threshold=0.1,
            min_cluster_size=2,
            capture_dir=self.capture_dir,
        )
        self.assertEqual(r1["status"], "ok")

        # Raw files should be archived
        raw_remaining = list((self.capture_dir / "raw").glob("raw_*.md"))
        self.assertEqual(len(raw_remaining), 0)

        archived = list((self.capture_dir / "archive").glob("raw_*.md"))
        self.assertEqual(len(archived), 2)

        # Run 2 — no raw files, nothing to do
        r2 = promote_run(
            threshold=0.1,
            min_cluster_size=2,
            capture_dir=self.capture_dir,
        )
        self.assertEqual(r2["status"], "no_raw_files")

        # Still only 1 bundle (mock prevents curate from moving it)
        promoted = list((self.capture_dir / "promoted").glob("bundle_*.md"))
        self.assertEqual(len(promoted), 1)


class TestCaptureStatus(unittest.TestCase):
    """capture_status returns correct counts."""

    def test_status_counts(self):
        import tempfile, shutil
        tmpdir = Path(tempfile.mkdtemp())
        capture_dir = tmpdir / "capture"
        (capture_dir / "raw").mkdir(parents=True)

        try:
            # Empty
            s = capture_status(capture_dir=capture_dir)
            self.assertEqual(s["raw_count"], 0)

            # After 2 captures
            capture_add(text="Note 1", capture_dir=capture_dir)
            time.sleep(0.01)
            capture_add(text="Note 2", capture_dir=capture_dir)

            s = capture_status(capture_dir=capture_dir)
            self.assertEqual(s["raw_count"], 2)
            self.assertIsNotNone(s["last_capture_ts"])
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
