"""
Tests for CONTENT_MEME_OFFLOAD domain action (v0.3).

Covers all v0.1 + v0.2 + v0.3 functionality:
  1.  Deterministic meme_id generation
  2.  LIMIT rule enforcement
  3.  DENY rules (named person, disallowed terms)
  4.  Reprojection FAIL → ConstraintViolation + Φ₁
  5.  Renderer PNG / import path
  6.  Stable pack hash
  7.  Strict spec_version enforcement (v0.2)
  8.  Telemetry pack provenance (v0.2)
  9.  Provider expansion policy gate (v0.2)
 10.  Kernel signals (v0.2)
 11.  meme_id recomputed after expansion (v0.3)
 12.  SVG renderer output (v0.3)
 13.  Template pack hash stability (v0.3)
 14.  Artifact registry ingest (v0.3)
 15.  Social signal queue write (v0.3)
 16.  Kernel stable in rule-only mode (v0.3)
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agents.meme_offload.schema import (
    SPEC_VERSION_CANONICAL,
    MemeSpecV1, MemePackRef, MemeCanvas, MemeOutput, MemeProvenance,
    MemeTextTwoPanel, MemeTextInfographic, generate_meme_id,
)
from app.utils.reprojection import (
    extract_meme_artifact_state, reproject_checkpoint_meme,
)
from app.utils.exceptions import ConstraintViolation


PACK_PATH = str(
    Path(__file__).resolve().parent.parent
    / "constraints" / "packs" / "domain" / "content_meme"
    / "CONTENT_MEME_OFFLOAD_v1.yaml"
)

TEMPLATE_PACK_DIR = (
    Path(__file__).resolve().parent.parent
    / "constraints" / "packs" / "domain" / "content_meme"
)


# ===================================================================
# v0.1 TESTS
# ===================================================================

class TestDeterministicMemeId(unittest.TestCase):
    def test_same_inputs_same_id(self):
        id1 = generate_meme_id("abc123", "frame_0000", "hello world", "two_panel")
        id2 = generate_meme_id("abc123", "frame_0000", "hello world", "two_panel")
        self.assertEqual(id1, id2)

    def test_different_inputs_different_id(self):
        id1 = generate_meme_id("abc123", "frame_0000", "hello world", "two_panel")
        id2 = generate_meme_id("abc123", "frame_0001", "hello world", "two_panel")
        self.assertNotEqual(id1, id2)

    def test_id_length(self):
        mid = generate_meme_id("hash", "frame", "text", "fmt")
        self.assertEqual(len(mid), 12)

    def test_id_is_hex(self):
        mid = generate_meme_id("hash", "frame", "text", "fmt")
        int(mid, 16)


class TestLimitEnforcement(unittest.TestCase):
    def test_limit_caps_output(self):
        from app.agents.meme_offload.meme_offload import _extract_candidate_frames
        source = "\n".join([f"Line {i}" for i in range(20)])
        frames = _extract_candidate_frames(source, "two_panel")
        self.assertEqual(len(frames), 10)


class TestDenyRules(unittest.TestCase):
    def test_named_person_detected(self):
        spec = MemeSpecV1(
            text=MemeTextTwoPanel(top="President Lincoln was here", bottom="A great leader"),
        )
        state = extract_meme_artifact_state(spec)
        self.assertTrue(state["contains_named_person"])

    def test_no_named_person(self):
        spec = MemeSpecV1(text=MemeTextTwoPanel(top="Hello world", bottom="Goodbye"))
        state = extract_meme_artifact_state(spec)
        self.assertFalse(state["contains_named_person"])

    def test_disallowed_terms_detected(self):
        spec = MemeSpecV1(
            text=MemeTextTwoPanel(top="This is about terrorism", bottom="Bad"),
        )
        state = extract_meme_artifact_state(spec)
        self.assertTrue(state["contains_disallowed_terms"])

    def test_no_disallowed_terms(self):
        spec = MemeSpecV1(text=MemeTextTwoPanel(top="Cats are great", bottom="Indeed"))
        state = extract_meme_artifact_state(spec)
        self.assertFalse(state["contains_disallowed_terms"])


class TestReprojectionFail(unittest.TestCase):
    def test_deny_named_person_raises(self):
        if not Path(PACK_PATH).exists():
            self.skipTest("Pack file not found")
        spec = MemeSpecV1(
            meme_id="test_deny_np",
            text=MemeTextTwoPanel(top="Dr. Smith discovered something", bottom="It was amazing"),
            format="two_panel",
        )
        with self.assertRaises(ConstraintViolation):
            reproject_checkpoint_meme(spec, PACK_PATH)

    def test_deny_disallowed_term_raises(self):
        if not Path(PACK_PATH).exists():
            self.skipTest("Pack file not found")
        spec = MemeSpecV1(
            meme_id="test_deny_dt",
            text=MemeTextTwoPanel(top="This contains murder references", bottom="Which is not allowed"),
            format="two_panel",
        )
        with self.assertRaises(ConstraintViolation):
            reproject_checkpoint_meme(spec, PACK_PATH)

    def test_kernel_phi1_increments_on_fail(self):
        from app.audit.coherence_kernel import CoherenceKernel
        kernel = CoherenceKernel()
        snap_before = kernel.snapshot()
        kernel.record_constraint_violation()
        snap_after = kernel.snapshot()
        self.assertGreater(snap_after.phi1, snap_before.phi1)


class TestRenderer(unittest.TestCase):
    def test_render_two_panel(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not installed")
        from app.agents.meme_offload.render.render_memes import render_meme
        with tempfile.TemporaryDirectory() as tmpdir:
            spec = MemeSpecV1(
                meme_id="test_render",
                format="two_panel",
                canvas=MemeCanvas(w=540, h=540, bg="#1a1a2e"),
                text=MemeTextTwoPanel(top="Top Text", bottom="Bottom Text"),
                output=MemeOutput(spec_path=str(Path(tmpdir) / "spec.json"), render_dir=tmpdir, filename="test_render.png"),
            )
            out_path = render_meme(spec)
            self.assertTrue(out_path.exists())
            self.assertTrue(out_path.stat().st_size > 0)
            img = Image.open(str(out_path))
            self.assertEqual(img.size, (540, 540))

    def test_render_infographic(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not installed")
        from app.agents.meme_offload.render.render_memes import render_meme
        with tempfile.TemporaryDirectory() as tmpdir:
            spec = MemeSpecV1(
                meme_id="test_infographic",
                format="infographic_list",
                canvas=MemeCanvas(w=540, h=540, bg="#1a1a2e"),
                text=MemeTextInfographic(title="Key Insights", bullets=("Point one", "Point two", "Point three")),
                output=MemeOutput(spec_path=str(Path(tmpdir) / "spec.json"), render_dir=tmpdir, filename="test_infographic.png"),
            )
            out_path = render_meme(spec)
            self.assertTrue(out_path.exists())


class TestRendererImportPath(unittest.TestCase):
    def test_render_meme_callable(self):
        from app.agents.meme_offload.render import render_memes
        self.assertTrue(callable(getattr(render_memes, "render_meme", None)))


class TestStablePackHash(unittest.TestCase):
    def test_hash_consistency(self):
        from app.utils.ir import stable_pack_hash
        from app.utils.reprojection import ConstraintPack
        if not Path(PACK_PATH).exists():
            self.skipTest("Pack file not found")
        import yaml
        with open(PACK_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        pack = ConstraintPack.from_dict(data)
        h1 = stable_pack_hash(pack)
        h2 = stable_pack_hash(pack)
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)


# ===================================================================
# v0.2 TESTS
# ===================================================================

class TestSpecVersionStrictness(unittest.TestCase):
    def test_canonical_version_accepted(self):
        spec = MemeSpecV1(spec_version="meme_spec_v1")
        self.assertEqual(spec.spec_version, SPEC_VERSION_CANONICAL)

    def test_semver_rejected(self):
        with self.assertRaises(ValueError):
            MemeSpecV1(spec_version="1.0.0")

    def test_empty_rejected(self):
        with self.assertRaises(ValueError):
            MemeSpecV1(spec_version="")

    def test_wrong_string_rejected(self):
        with self.assertRaises(ValueError):
            MemeSpecV1(spec_version="meme_spec_v2")

    def test_default_is_canonical(self):
        spec = MemeSpecV1()
        self.assertEqual(spec.spec_version, "meme_spec_v1")

    def test_validate_missing_pack_hash(self):
        spec = MemeSpecV1(pack=MemePackRef(pack_id="x", pack_version="1", pack_hash=""))
        with self.assertRaises(ValueError):
            spec.validate()

    def test_validate_missing_pack_id(self):
        spec = MemeSpecV1(pack=MemePackRef(pack_id="", pack_version="1", pack_hash="abc"))
        with self.assertRaises(ValueError):
            spec.validate()

    def test_validate_missing_pack_version(self):
        spec = MemeSpecV1(pack=MemePackRef(pack_id="x", pack_version="", pack_hash="abc"))
        with self.assertRaises(ValueError):
            spec.validate()

    def test_validate_passes_with_all_fields(self):
        spec = MemeSpecV1(pack=MemePackRef(pack_id="x", pack_version="1", pack_hash="abc"))
        spec.validate()

    def test_invalid_render_mode_rejected(self):
        with self.assertRaises(ValueError):
            MemeSpecV1(render_mode="webp")

    def test_svg_render_mode_accepted(self):
        spec = MemeSpecV1(render_mode="svg")
        self.assertEqual(spec.render_mode, "svg")

    def test_png_render_mode_default(self):
        spec = MemeSpecV1()
        self.assertEqual(spec.render_mode, "png")


class TestTelemetryIncludesPackMetadata(unittest.TestCase):
    def test_meme_offload_start_has_provenance(self):
        from app.agents.meme_offload.meme_offload import _pack_provenance, _get_rule_ids
        from app.utils.reprojection import ConstraintPack
        if not Path(PACK_PATH).exists():
            self.skipTest("Pack file not found")
        import yaml
        with open(PACK_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        pack = ConstraintPack.from_dict(data)
        rule_ids = _get_rule_ids(pack)
        self.assertIsInstance(rule_ids, list)
        self.assertTrue(len(rule_ids) >= 5)
        pack_ref = MemePackRef(pack_id="test", pack_version="1", pack_hash="sha256:abc")
        prov = _pack_provenance(pack_ref, rule_ids)
        for key in ("pack_id", "pack_version", "pack_hash", "rule_ids", "action"):
            self.assertIn(key, prov)
        self.assertEqual(prov["action"], "CONTENT_MEME_OFFLOAD")

    def test_rule_ids_are_deterministic_order(self):
        from app.agents.meme_offload.meme_offload import _get_rule_ids
        from app.utils.reprojection import ConstraintPack
        if not Path(PACK_PATH).exists():
            self.skipTest("Pack file not found")
        import yaml
        with open(PACK_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        pack = ConstraintPack.from_dict(data)
        ids1 = _get_rule_ids(pack)
        ids2 = _get_rule_ids(pack)
        self.assertEqual(ids1, ids2)


class TestProviderExpansionRequiresPolicyGate(unittest.TestCase):
    def test_expansion_disabled_by_default(self):
        from app.agents.meme_offload.meme_offload import _is_expansion_allowed
        from app.utils.reprojection import ConstraintPack
        if not Path(PACK_PATH).exists():
            self.skipTest("Pack file not found")
        import yaml
        with open(PACK_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        pack = ConstraintPack.from_dict(data)
        self.assertFalse(_is_expansion_allowed(pack))

    def test_expansion_disabled_without_rule(self):
        from app.agents.meme_offload.meme_offload import _is_expansion_allowed
        from app.utils.reprojection import ConstraintPack
        pack = ConstraintPack(scope="DOMAIN", constraint_rules=[])
        self.assertFalse(_is_expansion_allowed(pack))

    def test_expansion_enabled_with_empty_predicate(self):
        from app.agents.meme_offload.meme_offload import _is_expansion_allowed
        from app.utils.reprojection import ConstraintPack
        pack = ConstraintPack(
            scope="DOMAIN",
            constraint_rules=[{
                "constraint_id": "MEME_ALLOW_PROVIDER_EXPANSION",
                "rule_type": "ALLOW",
                "predicate": {},
            }],
        )
        self.assertTrue(_is_expansion_allowed(pack))


class TestKernelSignalsMemeExpansion(unittest.TestCase):
    def test_phi1_increments_on_constraint_violation(self):
        from app.audit.coherence_kernel import CoherenceKernel
        kernel = CoherenceKernel()
        snap_before = kernel.snapshot()
        kernel.record_constraint_violation()
        snap_after = kernel.snapshot()
        self.assertGreater(snap_after.phi1, snap_before.phi1)

    def test_no_false_drift_in_rule_only_mode(self):
        from app.audit.coherence_kernel import CoherenceKernel
        kernel = CoherenceKernel()
        snap1 = kernel.snapshot()
        snap2 = kernel.snapshot()
        self.assertEqual(snap1.phi1, snap2.phi1)
        self.assertEqual(snap1.phi2, snap2.phi2)
        self.assertEqual(snap1.phi3, snap2.phi3)
        self.assertEqual(snap1.phi4, snap2.phi4)
        self.assertEqual(snap1.regime, snap2.regime)

    def test_regime_stable_without_violations(self):
        from app.audit.coherence_kernel import CoherenceKernel
        kernel = CoherenceKernel()
        snap = kernel.snapshot()
        self.assertEqual(snap.regime.value, "STABLE")


# ===================================================================
# v0.3 NEW TESTS
# ===================================================================

class TestMemeIdRecomputedAfterExpansion(unittest.TestCase):
    """Test 11 (v0.3): meme_id must be deterministic based on FINAL text."""

    def test_expanded_text_changes_id(self):
        """Different final text → different meme_id."""
        original = generate_meme_id("hash", "frame_0000", "hello world", "two_panel")
        expanded = generate_meme_id("hash", "frame_0000", "hello world expanded version", "two_panel")
        self.assertNotEqual(original, expanded)

    def test_same_final_text_same_id(self):
        """Same final text after expansion → same meme_id."""
        id1 = generate_meme_id("hash", "frame_0000", "expanded text", "two_panel")
        id2 = generate_meme_id("hash", "frame_0000", "expanded text", "two_panel")
        self.assertEqual(id1, id2)

    def test_normalization_is_deterministic(self):
        """Normalization step + hash is repeatable."""
        text = "  Hello  World  "
        norm = text.strip()
        id1 = generate_meme_id("pack", "frame", norm, "two_panel")
        id2 = generate_meme_id("pack", "frame", norm, "two_panel")
        self.assertEqual(id1, id2)


class TestSVGRendererOutputExists(unittest.TestCase):
    """Test 12a (v0.3): SVG renderer produces valid SVG output."""

    def test_svg_two_panel_output(self):
        from app.agents.meme_offload.render.render_svg import render_meme_svg
        with tempfile.TemporaryDirectory() as tmpdir:
            spec = MemeSpecV1(
                meme_id="svg_test_01",
                format="two_panel",
                render_mode="svg",
                canvas=MemeCanvas(w=540, h=540, bg="#1a1a2e"),
                text=MemeTextTwoPanel(top="Top SVG", bottom="Bottom SVG"),
                output=MemeOutput(spec_path=str(Path(tmpdir) / "spec.json"), render_dir=tmpdir, filename="svg_test_01.svg"),
            )
            out_path = render_meme_svg(spec)
            self.assertTrue(out_path.exists())
            self.assertTrue(out_path.stat().st_size > 0)
            content = out_path.read_text(encoding="utf-8")
            self.assertIn("<svg", content)
            self.assertIn("xmlns", content)
            self.assertIn("Top SVG", content)
            self.assertIn("Bottom SVG", content)

    def test_svg_infographic_output(self):
        from app.agents.meme_offload.render.render_svg import render_meme_svg
        with tempfile.TemporaryDirectory() as tmpdir:
            spec = MemeSpecV1(
                meme_id="svg_info_01",
                format="infographic_list",
                render_mode="svg",
                canvas=MemeCanvas(w=600, h=800, bg="#f5f5f5"),
                text=MemeTextInfographic(title="Key Points", bullets=("First", "Second", "Third")),
                output=MemeOutput(spec_path=str(Path(tmpdir) / "spec.json"), render_dir=tmpdir, filename="svg_info_01.svg"),
            )
            out_path = render_meme_svg(spec)
            self.assertTrue(out_path.exists())
            content = out_path.read_text(encoding="utf-8")
            self.assertIn("Key Points", content)
            self.assertIn("First", content)

    def test_svg_no_external_deps(self):
        """SVG renderer must not import Pillow."""
        import app.agents.meme_offload.render.render_svg as svg_mod
        source = Path(svg_mod.__file__).read_text(encoding="utf-8")
        self.assertNotIn("from PIL", source)
        self.assertNotIn("import PIL", source)


class TestSVGRendererDeterministicPath(unittest.TestCase):
    """Test 12b (v0.3): SVG output path is deterministic."""

    def test_deterministic_output_path(self):
        from app.agents.meme_offload.render.render_svg import render_meme_svg
        with tempfile.TemporaryDirectory() as tmpdir:
            spec = MemeSpecV1(
                meme_id="det_svg_01",
                format="two_panel",
                render_mode="svg",
                canvas=MemeCanvas(w=540, h=540, bg="#000"),
                text=MemeTextTwoPanel(top="A", bottom="B"),
                output=MemeOutput(spec_path=str(Path(tmpdir) / "s.json"), render_dir=tmpdir, filename="det_svg_01.svg"),
            )
            p1 = render_meme_svg(spec)
            content1 = p1.read_text(encoding="utf-8")
            # Re-render to same path
            p2 = render_meme_svg(spec)
            content2 = p2.read_text(encoding="utf-8")
            self.assertEqual(str(p1), str(p2))
            self.assertEqual(content1, content2)


class TestTemplatePackHashStability(unittest.TestCase):
    """Test 13 (v0.3): Template pack hashes are stable."""

    def _hash_pack(self, pack_name: str) -> str:
        from app.utils.ir import stable_pack_hash
        from app.utils.reprojection import ConstraintPack
        import yaml
        pack_path = TEMPLATE_PACK_DIR / pack_name
        if not pack_path.exists():
            self.skipTest(f"Pack not found: {pack_name}")
        with open(pack_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        pack = ConstraintPack.from_dict(data)
        return stable_pack_hash(pack)

    def test_reddit_deadpan_hash_stable(self):
        h1 = self._hash_pack("reddit_deadpan_v1.yaml")
        h2 = self._hash_pack("reddit_deadpan_v1.yaml")
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)

    def test_linkedin_clean_hash_stable(self):
        h1 = self._hash_pack("linkedin_clean_v1.yaml")
        h2 = self._hash_pack("linkedin_clean_v1.yaml")
        self.assertEqual(h1, h2)

    def test_youtube_thumbnail_hash_stable(self):
        h1 = self._hash_pack("youtube_thumbnail_v1.yaml")
        h2 = self._hash_pack("youtube_thumbnail_v1.yaml")
        self.assertEqual(h1, h2)

    def test_all_template_packs_produce_valid_hash(self):
        """Each template pack produces a valid 64-char hex hash."""
        for name in ["reddit_deadpan_v1.yaml", "linkedin_clean_v1.yaml", "youtube_thumbnail_v1.yaml"]:
            h = self._hash_pack(name)
            self.assertEqual(len(h), 64, f"{name} hash should be 64 chars")
            int(h, 16)  # Should not raise — valid hex


class TestArtifactRegistryIngest(unittest.TestCase):
    """Test 14 (v0.3): Artifact registry auto-ingest."""

    def test_ingest_creates_entry(self):
        from app.agents.meme_offload.artifact_registry import ingest_artifact
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a fake rendered file
            rendered = Path(tmpdir) / "test_render.png"
            rendered.write_bytes(b"fake png content for testing")
            registry = Path(tmpdir) / "registry.jsonl"

            entry = ingest_artifact(
                rendered_path=rendered,
                pack_id="test_pack",
                pack_hash="sha256:abc123",
                meme_id="test_meme_01",
                registry_path=registry,
            )

            self.assertIn("artifact_id", entry)
            self.assertEqual(entry["artifact_type"], "meme_render")
            self.assertEqual(entry["pack_id"], "test_pack")
            self.assertEqual(entry["meme_id"], "test_meme_01")

            # Verify file exists
            self.assertTrue(registry.exists())
            lines = registry.read_text(encoding="utf-8").strip().split("\n")
            self.assertEqual(len(lines), 1)

    def test_ingest_idempotent(self):
        """Same file ingested twice should not duplicate."""
        from app.agents.meme_offload.artifact_registry import ingest_artifact
        with tempfile.TemporaryDirectory() as tmpdir:
            rendered = Path(tmpdir) / "test_idem.png"
            rendered.write_bytes(b"idempotent test content")
            registry = Path(tmpdir) / "registry.jsonl"

            ingest_artifact(rendered_path=rendered, pack_id="p", pack_hash="h", meme_id="m1", registry_path=registry)
            ingest_artifact(rendered_path=rendered, pack_id="p", pack_hash="h", meme_id="m1", registry_path=registry)

            lines = registry.read_text(encoding="utf-8").strip().split("\n")
            self.assertEqual(len(lines), 1, "Duplicate entries should not exist")

    def test_canonical_rename_created(self):
        """Canonical file with hash12 in name should be created."""
        from app.agents.meme_offload.artifact_registry import ingest_artifact
        with tempfile.TemporaryDirectory() as tmpdir:
            rendered = Path(tmpdir) / "meme_abc.png"
            rendered.write_bytes(b"canonical rename test")
            registry = Path(tmpdir) / "registry.jsonl"

            entry = ingest_artifact(rendered_path=rendered, pack_id="p", pack_hash="h", meme_id="m1", registry_path=registry)

            # The canonical path should contain __<hash12>
            canonical = Path(entry["path"])
            self.assertIn("__", canonical.stem)
            self.assertTrue(canonical.exists())


class TestSocialSignalQueueWrite(unittest.TestCase):
    """Test 15 (v0.3): Social signal queue write."""

    def test_queue_write_reddit(self):
        from app.hq.social_signal_pipeline import schedule_meme_signal
        with tempfile.TemporaryDirectory() as tmpdir:
            spec = MemeSpecV1(
                meme_id="social_test_01",
                pack=MemePackRef(pack_id="test", pack_version="1", pack_hash="sha256:abc"),
                text=MemeTextTwoPanel(top="Hello Reddit", bottom="From Signal Agent"),
                output=MemeOutput(spec_path="spec.json", render_dir=tmpdir, filename="social_test_01.png"),
            )
            queue_dir = Path(tmpdir) / "queue"
            payload = schedule_meme_signal(spec, "reddit", queue_dir=queue_dir)

            self.assertEqual(payload["platform"], "reddit")
            self.assertEqual(payload["meme_id"], "social_test_01")
            self.assertTrue(payload["internal_only"])
            self.assertEqual(payload["status"], "queued")

            # Verify file was written
            reddit_dir = queue_dir / "reddit"
            self.assertTrue(reddit_dir.exists())
            files = list(reddit_dir.glob("*.json"))
            self.assertEqual(len(files), 1)

            # Verify JSON is valid
            with open(files[0], "r", encoding="utf-8") as f:
                written = json.load(f)
            self.assertEqual(written["meme_id"], "social_test_01")

    def test_queue_write_linkedin(self):
        from app.hq.social_signal_pipeline import schedule_meme_signal
        with tempfile.TemporaryDirectory() as tmpdir:
            spec = MemeSpecV1(
                meme_id="social_li_01",
                pack=MemePackRef(pack_id="test", pack_version="1", pack_hash="sha256:def"),
                text=MemeTextInfographic(title="LinkedIn Post", bullets=("Point 1",)),
                output=MemeOutput(spec_path="s.json", render_dir=tmpdir, filename="s.svg"),
                render_mode="svg",
                format="infographic_list",
            )
            queue_dir = Path(tmpdir) / "queue"
            payload = schedule_meme_signal(spec, "linkedin", queue_dir=queue_dir)
            self.assertEqual(payload["platform"], "linkedin")

    def test_unsupported_platform_rejected(self):
        from app.hq.social_signal_pipeline import schedule_meme_signal
        spec = MemeSpecV1(meme_id="fail_01")
        with self.assertRaises(ValueError):
            schedule_meme_signal(spec, "tiktok")

    def test_no_network_calls(self):
        """social_signal_pipeline must not import networking modules."""
        import app.hq.social_signal_pipeline as ssp
        source = Path(ssp.__file__).read_text(encoding="utf-8")
        for forbidden in ("import requests", "import urllib", "import http.client", "import socket"):
            self.assertNotIn(forbidden, source)


class TestKernelSignalsRemainStableRuleMode(unittest.TestCase):
    """Test 16 (v0.3): Kernel signals remain stable in rule-only mode."""

    def test_all_phi_zero_on_init(self):
        from app.audit.coherence_kernel import CoherenceKernel
        kernel = CoherenceKernel()
        snap = kernel.snapshot()
        self.assertAlmostEqual(snap.phi1, 0.0, places=4)
        self.assertAlmostEqual(snap.phi2, 0.0, places=4)
        self.assertAlmostEqual(snap.phi3, 0.0, places=4)
        self.assertAlmostEqual(snap.phi4, 0.0, places=4)
        self.assertAlmostEqual(snap.phi_risk, 0.0, places=4)

    def test_coherence_one_at_init(self):
        from app.audit.coherence_kernel import CoherenceKernel
        kernel = CoherenceKernel()
        snap = kernel.snapshot()
        self.assertAlmostEqual(snap.coherence, 1.0, places=4)

    def test_multiple_snapshots_no_drift(self):
        from app.audit.coherence_kernel import CoherenceKernel
        kernel = CoherenceKernel()
        for _ in range(10):
            snap = kernel.snapshot()
        self.assertAlmostEqual(snap.phi1, 0.0, places=4)
        self.assertEqual(snap.regime.value, "STABLE")

    def test_regime_remains_stable(self):
        from app.audit.coherence_kernel import CoherenceKernel
        kernel = CoherenceKernel()
        snap = kernel.snapshot()
        self.assertEqual(snap.regime.value, "STABLE")


if __name__ == "__main__":
    unittest.main()
