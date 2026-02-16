"""
Tests for Signal Pipelines — Post Composer v0.1.

10 test classes covering:
1.  Strict queue contract validation
2.  Deterministic queue_id computation
3.  Deterministic output paths
4.  Idempotent compose
5.  Fail-closed on missing template
6.  Fail-closed on missing render path
7.  Manifest contains SHA256 hashes
8.  Newline normalization
9.  Sorted links deterministic
10. CLI compose batch
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.hq.post_composer.queue_contract import (
    SocialQueueV1, normalize_text, safe_slug, _compute_queue_id,
    QUEUE_VERSION_CANONICAL,
)
from app.hq.post_composer.compose import compose_queue_item

FIXTURES = Path(__file__).resolve().parent / "fixtures"
VALID_QUEUE_PATH = FIXTURES / "valid_queue.json"
DUMMY_RENDER_PATH = FIXTURES / "dummy_render.svg"


def _make_valid_data(**overrides) -> dict:
    """Build a minimal valid queue data dict with optional overrides."""
    data = {
        "queue_version": "social_queue_v1",
        "lane": "artifact_channel",
        "platform": "linkedin",
        "intent": "post",
        "meme_id": "test_meme_001",
        "render_paths": [str(DUMMY_RENDER_PATH)],
        "artifact_links": [
            {"label": "Meme Render", "path": str(DUMMY_RENDER_PATH)}
        ],
        "copy": {
            "headline": "Test Headline",
            "body": "Test body content.\nSecond line."
        },
        "pack": {
            "pack_id": "test_pack",
            "pack_hash": "sha256:abc123"
        },
        "provenance": {
            "source_artifact_id": "art_001",
            "session_id": "sess_001",
            "created_at_utc": "2026-02-16T08:00:00Z"
        },
    }
    data.update(overrides)
    return data


def _write_queue_json(tmpdir: str, data: dict, filename: str = "queue.json") -> str:
    """Write queue data as JSON file and return path."""
    path = Path(tmpdir) / filename
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, sort_keys=True, indent=2)
    return str(path)


# ===================================================================
# 1. Contract Validation
# ===================================================================

class TestQueueContractStrictValidation(unittest.TestCase):
    """Test 1: Missing/invalid fields fail-closed."""

    def test_valid_data_accepted(self):
        data = _make_valid_data()
        q = SocialQueueV1.from_dict(data)
        self.assertEqual(q.queue_version, QUEUE_VERSION_CANONICAL)
        self.assertEqual(q.platform, "linkedin")

    def test_missing_queue_version_fails(self):
        data = _make_valid_data()
        del data["queue_version"]
        with self.assertRaises(ValueError):
            SocialQueueV1.from_dict(data)

    def test_wrong_queue_version_fails(self):
        data = _make_valid_data(queue_version="v2")
        with self.assertRaises(ValueError):
            SocialQueueV1.from_dict(data)

    def test_invalid_lane_fails(self):
        data = _make_valid_data(lane="unknown_lane")
        with self.assertRaises(ValueError):
            SocialQueueV1.from_dict(data)

    def test_invalid_platform_fails(self):
        data = _make_valid_data(platform="tiktok")
        with self.assertRaises(ValueError):
            SocialQueueV1.from_dict(data)

    def test_invalid_intent_fails(self):
        data = _make_valid_data(intent="story")
        with self.assertRaises(ValueError):
            SocialQueueV1.from_dict(data)

    def test_missing_meme_id_fails(self):
        data = _make_valid_data()
        del data["meme_id"]
        with self.assertRaises(ValueError):
            SocialQueueV1.from_dict(data)

    def test_empty_render_paths_fails(self):
        data = _make_valid_data(render_paths=[])
        with self.assertRaises(ValueError):
            SocialQueueV1.from_dict(data)

    def test_missing_copy_fails(self):
        data = _make_valid_data()
        del data["copy"]
        with self.assertRaises(ValueError):
            SocialQueueV1.from_dict(data)

    def test_missing_pack_fails(self):
        data = _make_valid_data()
        del data["pack"]
        with self.assertRaises(ValueError):
            SocialQueueV1.from_dict(data)

    def test_missing_provenance_fails(self):
        data = _make_valid_data()
        del data["provenance"]
        with self.assertRaises(ValueError):
            SocialQueueV1.from_dict(data)

    def test_artifact_links_missing_label_fails(self):
        data = _make_valid_data(artifact_links=[{"path": "x"}])
        with self.assertRaises(ValueError):
            SocialQueueV1.from_dict(data)

    def test_all_platforms_accepted(self):
        for platform in ["linkedin", "substack", "github", "facebook", "youtube"]:
            lane = "artifact_channel" if platform in ("linkedin", "substack", "github") else "human_channel"
            data = _make_valid_data(platform=platform, lane=lane)
            q = SocialQueueV1.from_dict(data)
            self.assertEqual(q.platform, platform)

    def test_all_intents_accepted(self):
        for intent in ["post", "description", "thread"]:
            data = _make_valid_data(intent=intent)
            q = SocialQueueV1.from_dict(data)
            self.assertEqual(q.intent, intent)


# ===================================================================
# 2. Deterministic queue_id
# ===================================================================

class TestDeterministicQueueId(unittest.TestCase):
    """Test 2: Same inputs → same queue_id."""

    def test_same_data_same_id(self):
        data = _make_valid_data()
        id1 = _compute_queue_id(data)
        id2 = _compute_queue_id(data)
        self.assertEqual(id1, id2)

    def test_different_body_different_id(self):
        data1 = _make_valid_data()
        data2 = _make_valid_data()
        data2["copy"]["body"] = "Different body text."
        self.assertNotEqual(_compute_queue_id(data1), _compute_queue_id(data2))

    def test_queue_id_is_12_hex(self):
        data = _make_valid_data()
        qid = _compute_queue_id(data)
        self.assertEqual(len(qid), 12)
        int(qid, 16)  # Must be valid hex

    def test_provided_valid_queue_id_used(self):
        data = _make_valid_data()
        data["queue_id"] = "abcdef012345"
        q = SocialQueueV1.from_dict(data)
        self.assertEqual(q.queue_id, "abcdef012345")

    def test_provided_invalid_queue_id_recomputed(self):
        data = _make_valid_data()
        data["queue_id"] = "not-hex!"
        q = SocialQueueV1.from_dict(data)
        self.assertEqual(len(q.queue_id), 12)
        int(q.queue_id, 16)


# ===================================================================
# 3. Deterministic Output Paths
# ===================================================================

class TestDeterministicOutputPaths(unittest.TestCase):
    """Test 3: Same input → same out_dir and filenames."""

    def test_same_input_same_output_dir(self):
        data = _make_valid_data()
        with tempfile.TemporaryDirectory() as tmpdir:
            qpath = _write_queue_json(tmpdir, data)
            out_root = Path(tmpdir) / "out"

            r1 = compose_queue_item(qpath, out_root=out_root)
            # Clean and re-run
            shutil.rmtree(out_root)
            r2 = compose_queue_item(qpath, out_root=out_root)

            self.assertEqual(r1["out_dir"], r2["out_dir"])
            self.assertEqual(r1["md_path"], r2["md_path"])

    def test_output_dir_contains_queue_id(self):
        data = _make_valid_data()
        with tempfile.TemporaryDirectory() as tmpdir:
            qpath = _write_queue_json(tmpdir, data)
            out_root = Path(tmpdir) / "out"
            r = compose_queue_item(qpath, out_root=out_root)
            q = SocialQueueV1.from_dict(data)
            self.assertIn(q.queue_id, r["out_dir"])


# ===================================================================
# 4. Idempotent Compose
# ===================================================================

class TestIdempotentCompose(unittest.TestCase):
    """Test 4: Run twice → no changes (hashes identical)."""

    def test_second_run_skips_identical(self):
        data = _make_valid_data()
        with tempfile.TemporaryDirectory() as tmpdir:
            qpath = _write_queue_json(tmpdir, data)
            out_root = Path(tmpdir) / "out"

            r1 = compose_queue_item(qpath, out_root=out_root)
            self.assertTrue(len(r1["written_files"]) > 0)

            r2 = compose_queue_item(qpath, out_root=out_root)
            self.assertEqual(len(r2["written_files"]), 0)
            self.assertTrue(len(r2["skipped_files"]) > 0)

    def test_different_content_fails_without_force(self):
        data = _make_valid_data()
        with tempfile.TemporaryDirectory() as tmpdir:
            qpath = _write_queue_json(tmpdir, data)
            out_root = Path(tmpdir) / "out"

            compose_queue_item(qpath, out_root=out_root)

            # Corrupt the MD file
            q = SocialQueueV1.from_dict(data)
            md_path = out_root / q.lane / q.platform / q.queue_id / "post.md"
            md_path.write_bytes(b"corrupted content")

            with self.assertRaises(ValueError):
                compose_queue_item(qpath, out_root=out_root)

    def test_force_overwrites_different_content(self):
        data = _make_valid_data()
        with tempfile.TemporaryDirectory() as tmpdir:
            qpath = _write_queue_json(tmpdir, data)
            out_root = Path(tmpdir) / "out"

            compose_queue_item(qpath, out_root=out_root)

            # Corrupt
            q = SocialQueueV1.from_dict(data)
            md_path = out_root / q.lane / q.platform / q.queue_id / "post.md"
            md_path.write_bytes(b"corrupted")

            r = compose_queue_item(qpath, out_root=out_root, force=True)
            self.assertIn(str(md_path), r["written_files"])


# ===================================================================
# 5. Fail-Closed Missing Template
# ===================================================================

class TestFailClosedMissingTemplate(unittest.TestCase):
    """Test 5: Missing template → compose fails."""

    def test_missing_template_raises(self):
        data = _make_valid_data()
        with tempfile.TemporaryDirectory() as tmpdir:
            qpath = _write_queue_json(tmpdir, data)
            out_root = Path(tmpdir) / "out"

            # Temporarily rename template
            from app.hq.post_composer.compose import _TEMPLATE_DIR
            tpl = _TEMPLATE_DIR / "linkedin_post.html"
            backup = _TEMPLATE_DIR / "linkedin_post.html.bak"
            tpl.rename(backup)
            try:
                with self.assertRaises(FileNotFoundError):
                    compose_queue_item(qpath, out_root=out_root)
            finally:
                backup.rename(tpl)


# ===================================================================
# 6. Fail-Closed Missing Render Path
# ===================================================================

class TestFailClosedMissingRenderPath(unittest.TestCase):
    """Test 6: Queue references missing render file → fails."""

    def test_nonexistent_render_path_fails(self):
        data = _make_valid_data(
            render_paths=["tests/fixtures/no_such_file.svg"]
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            qpath = _write_queue_json(tmpdir, data)
            out_root = Path(tmpdir) / "out"
            with self.assertRaises(ValueError):
                compose_queue_item(qpath, out_root=out_root)


# ===================================================================
# 7. Manifest Contains Hashes
# ===================================================================

class TestManifestContainsHashes(unittest.TestCase):
    """Test 7: Manifest lists SHA256 for html/md/manifest."""

    def test_manifest_has_hashes(self):
        data = _make_valid_data()
        with tempfile.TemporaryDirectory() as tmpdir:
            qpath = _write_queue_json(tmpdir, data)
            out_root = Path(tmpdir) / "out"
            r = compose_queue_item(qpath, out_root=out_root)

            manifest_path = Path(r["manifest_path"])
            self.assertTrue(manifest_path.exists())

            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)

            rendered = manifest["rendered"]
            self.assertIn("md_sha256", rendered)
            self.assertIn("html_sha256", rendered)
            self.assertIn("manifest_sha256", rendered)

            # Verify MD hash
            md_path = Path(r["md_path"])
            md_hash = hashlib.sha256(md_path.read_bytes()).hexdigest()
            self.assertEqual(rendered["md_sha256"], md_hash)

    def test_manifest_version_correct(self):
        data = _make_valid_data()
        with tempfile.TemporaryDirectory() as tmpdir:
            qpath = _write_queue_json(tmpdir, data)
            out_root = Path(tmpdir) / "out"
            r = compose_queue_item(qpath, out_root=out_root)

            with open(r["manifest_path"], "r", encoding="utf-8") as f:
                manifest = json.load(f)
            self.assertEqual(manifest["manifest_version"], "signal_manifest_v1")

    def test_manifest_has_provenance(self):
        data = _make_valid_data()
        with tempfile.TemporaryDirectory() as tmpdir:
            qpath = _write_queue_json(tmpdir, data)
            out_root = Path(tmpdir) / "out"
            r = compose_queue_item(qpath, out_root=out_root)

            with open(r["manifest_path"], "r", encoding="utf-8") as f:
                manifest = json.load(f)

            prov = manifest["provenance"]
            self.assertEqual(prov["source_artifact_id"], "art_001")
            self.assertEqual(prov["session_id"], "sess_001")


# ===================================================================
# 8. Newline Normalization
# ===================================================================

class TestNewlineNormalization(unittest.TestCase):
    """Test 8: CRLF → LF, trailing spaces stripped."""

    def test_crlf_to_lf(self):
        self.assertEqual(normalize_text("hello\r\nworld"), "hello\nworld")

    def test_cr_to_lf(self):
        self.assertEqual(normalize_text("hello\rworld"), "hello\nworld")

    def test_trailing_spaces_stripped(self):
        self.assertEqual(normalize_text("hello   \nworld  "), "hello\nworld")

    def test_trailing_newlines_stripped(self):
        self.assertEqual(normalize_text("hello\n\n\n"), "hello")

    def test_output_files_lf_only(self):
        data = _make_valid_data()
        data["copy"]["body"] = "Line one\r\nLine two\r\nLine three"
        with tempfile.TemporaryDirectory() as tmpdir:
            qpath = _write_queue_json(tmpdir, data)
            out_root = Path(tmpdir) / "out"
            r = compose_queue_item(qpath, out_root=out_root)

            md_bytes = Path(r["md_path"]).read_bytes()
            self.assertNotIn(b"\r\n", md_bytes)
            self.assertNotIn(b"\r", md_bytes)

            if "html_path" in r:
                html_bytes = Path(r["html_path"]).read_bytes()
                self.assertNotIn(b"\r\n", html_bytes)


# ===================================================================
# 9. Sorted Links Deterministic
# ===================================================================

class TestSortedLinksDeterministic(unittest.TestCase):
    """Test 9: Links and render_paths sorted for determinism."""

    def test_links_sorted_in_output(self):
        data = _make_valid_data(
            artifact_links=[
                {"label": "Zebra", "path": "z.txt"},
                {"label": "Alpha", "path": "a.txt"},
            ],
            render_paths=[str(DUMMY_RENDER_PATH), str(DUMMY_RENDER_PATH)]
        )
        q = SocialQueueV1.from_dict(data)
        self.assertEqual(q.artifact_links[0]["label"], "Alpha")
        self.assertEqual(q.artifact_links[1]["label"], "Zebra")

    def test_render_paths_sorted(self):
        data = _make_valid_data(
            render_paths=[str(DUMMY_RENDER_PATH), str(DUMMY_RENDER_PATH)]
        )
        q = SocialQueueV1.from_dict(data)
        for i in range(len(q.render_paths) - 1):
            self.assertLessEqual(q.render_paths[i], q.render_paths[i + 1])

    def test_sort_order_deterministic(self):
        data = _make_valid_data(
            artifact_links=[
                {"label": "C", "path": "c.txt"},
                {"label": "A", "path": "a.txt"},
                {"label": "B", "path": "b.txt"},
            ]
        )
        q1 = SocialQueueV1.from_dict(data)
        q2 = SocialQueueV1.from_dict(data)
        self.assertEqual(q1.artifact_links, q2.artifact_links)


# ===================================================================
# 10. CLI Compose Batch
# ===================================================================

class TestCLIComposeBatch(unittest.TestCase):
    """Test 10: CLI batch compose with limit."""

    def test_batch_limit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create queue dir structure
            queue_dir = Path(tmpdir) / "social_queue" / "artifact_channel" / "linkedin"
            queue_dir.mkdir(parents=True)
            out_dir = Path(tmpdir) / "social_out"

            # Write 3 queue items
            for i in range(3):
                data = _make_valid_data(meme_id=f"batch_meme_{i:03d}")
                path = queue_dir / f"item_{i:03d}.json"
                with open(path, "w", encoding="utf-8", newline="\n") as f:
                    json.dump(data, f, sort_keys=True, indent=2)

            # Mock the queue root and out root
            from app.cli import brn_cmds_signal
            original_queue_root = brn_cmds_signal._QUEUE_ROOT

            try:
                brn_cmds_signal._QUEUE_ROOT = Path(tmpdir) / "social_queue"

                # Compose with limit 2
                with patch("app.hq.post_composer.compose._SOCIAL_OUT", out_dir):
                    exit_code = brn_cmds_signal.brn_signal_compose(
                        lane="artifact_channel",
                        platform="linkedin",
                        limit=2,
                    )

                self.assertEqual(exit_code, 0)

                # Verify only 2 outputs created
                out_lanes = list((out_dir / "artifact_channel" / "linkedin").iterdir())
                self.assertEqual(len(out_lanes), 2)

            finally:
                brn_cmds_signal._QUEUE_ROOT = original_queue_root


# ===================================================================
# Helpers
# ===================================================================

class TestSafeSlug(unittest.TestCase):
    """Safe slug utility tests."""

    def test_basic_slug(self):
        self.assertEqual(safe_slug("Hello World"), "hello-world")

    def test_special_chars(self):
        self.assertEqual(safe_slug("Test@#$123"), "test-123")

    def test_max_length(self):
        long = "a" * 100
        self.assertEqual(len(safe_slug(long)), 64)

    def test_deterministic(self):
        self.assertEqual(safe_slug("Test Input"), safe_slug("Test Input"))


class TestGithubMdOnly(unittest.TestCase):
    """GitHub platform gets MD-only output (no HTML)."""

    def test_github_no_html(self):
        data = _make_valid_data(platform="github", lane="artifact_channel")
        with tempfile.TemporaryDirectory() as tmpdir:
            qpath = _write_queue_json(tmpdir, data)
            out_root = Path(tmpdir) / "out"
            r = compose_queue_item(qpath, out_root=out_root)

            self.assertNotIn("html_path", r)
            self.assertTrue(Path(r["md_path"]).exists())
            self.assertTrue(Path(r["manifest_path"]).exists())


if __name__ == "__main__":
    unittest.main()
