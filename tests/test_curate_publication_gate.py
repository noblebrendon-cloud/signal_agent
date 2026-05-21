from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from app.hq.curation import curate


class TestCuratePublicationGate(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.repo_root = self.tmpdir
        self.registry_path = self.tmpdir / "data" / "artifact_registry.jsonl"
        self.index_path = self.tmpdir / "data" / "INDEX_ARTIFACTS.md"
        self.config_path = self.tmpdir / "app" / "hq" / "curation" / "rules.yaml"
        self.route_root = self.tmpdir / "data" / "published"

        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.route_root.parent.mkdir(parents=True, exist_ok=True)

        config = {
            "routes": {
                "docs": str(self.route_root),
                "archive": str(self.tmpdir / "data" / "archive"),
            },
            "kinds": [
                {
                    "ext": [".md"],
                    "kind": "document",
                    "route": "docs",
                }
            ],
            "defaults": {
                "route": "archive",
                "action": "move",
            },
        }
        self.config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

        self.repo_root_patch = patch.object(curate, "REPO_ROOT", self.repo_root)
        self.registry_patch = patch.object(curate, "REGISTRY_PATH", self.registry_path)
        self.index_patch = patch.object(curate, "INDEX_PATH", self.index_path)
        self.config_patch = patch.object(curate, "CONFIG_PATH", self.config_path)

        self.repo_root_patch.start()
        self.registry_patch.start()
        self.index_patch.start()
        self.config_patch.start()

    def tearDown(self) -> None:
        self.config_patch.stop()
        self.index_patch.stop()
        self.registry_patch.stop()
        self.repo_root_patch.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_source(self, name: str = "draft.md", text: str = "draft body\n") -> Path:
        source = self.tmpdir / "incoming" / name
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(text, encoding="utf-8")
        return source

    def test_curate_file_uses_atomic_registry_append_and_index_write(self) -> None:
        source = self._make_source()
        validation = {
            "allowed": True,
            "current_state": "compiled",
            "next_state": "staged",
            "lane_id": "content_publishing",
            "state_source": "legacy_assumption",
            "gate": "publication_policy",
            "policy_id": "publication_policy",
            "policy_result": {"allowed": True, "failures": []},
            "reason": None,
        }

        with (
            patch.object(curate, "validate_transition", return_value=validation),
            patch.object(curate, "emit_transition_event"),
            patch.object(curate, "append_jsonl_atomic", wraps=curate.append_jsonl_atomic) as mock_append,
            patch.object(curate, "atomic_write_text", wraps=curate.atomic_write_text) as mock_atomic_write,
        ):
            result = curate.curate_file(source, enforce_governor=False)

        self.assertEqual(result["action"], "created")
        self.assertEqual(Path(mock_append.call_args.args[0]), self.registry_path)
        self.assertTrue(
            any(Path(call.args[0]) == self.index_path for call in mock_atomic_write.call_args_list),
            "INDEX_ARTIFACTS.md should be written through atomic_write_text",
        )
        self.assertTrue(self.registry_path.exists())
        self.assertTrue(self.index_path.exists())
        self.assertFalse(source.exists())

        entries = [
            json.loads(line)
            for line in self.registry_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["route"], "docs")

        staged_files = [p for p in self.route_root.iterdir() if p.is_file()]
        self.assertEqual(len(staged_files), 1)
        self.assertEqual(Path(result["output_path"]), staged_files[0])

    def test_rejected_curate_does_not_write_registry_or_index(self) -> None:
        source = self._make_source("blocked.md", "blocked\n")
        validation = {
            "allowed": False,
            "current_state": "compiled",
            "next_state": "staged",
            "lane_id": "content_publishing",
            "state_source": "legacy_assumption",
            "gate": "publication_policy",
            "policy_id": "publication_policy",
            "policy_result": {"allowed": False, "failures": ["route_key_present"]},
            "reason": "route_key_present",
        }

        with (
            patch.object(curate, "validate_transition", return_value=validation),
            patch.object(curate, "emit_transition_event"),
        ):
            result = curate.curate_file(source, enforce_governor=False)

        self.assertEqual(result["action"], "rejected")
        self.assertTrue(source.exists())
        self.assertFalse(self.registry_path.exists())
        self.assertFalse(self.index_path.exists())
        self.assertEqual(list(self.route_root.glob("*")), [])

    def test_curate_file_supports_repo_relative_routes_without_absolute_paths(self) -> None:
        self.config_path.write_text(
            yaml.safe_dump(
                {
                    "routes": {
                        "docs": "data/published_relative",
                    },
                    "kinds": [
                        {
                            "ext": [".md"],
                            "kind": "document",
                            "route": "docs",
                        }
                    ],
                    "defaults": {
                        "route": "archive",
                        "action": "move",
                    },
                }
            ),
            encoding="utf-8",
        )
        source = self._make_source("portable.md", "portable body\n")
        validation = {
            "allowed": True,
            "current_state": "compiled",
            "next_state": "staged",
            "lane_id": "content_publishing",
            "state_source": "legacy_assumption",
            "gate": "publication_policy",
            "policy_id": "publication_policy",
            "policy_result": {"allowed": True, "failures": []},
            "reason": None,
        }

        with (
            patch.object(curate, "validate_transition", return_value=validation),
            patch.object(curate, "emit_transition_event"),
        ):
            result = curate.curate_file(source, enforce_governor=False)

        expected_root = self.repo_root / "data" / "published_relative"
        self.assertEqual(result["action"], "created")
        self.assertTrue(str(result["output_path"]).startswith(str(expected_root)))
        self.assertTrue(Path(result["output_path"]).exists())

    def test_curate_file_uses_repo_relative_archive_fallback_without_configured_archive(self) -> None:
        self.config_path.write_text(
            yaml.safe_dump(
                {
                    "defaults": {
                        "route": "archive",
                        "action": "move",
                    },
                }
            ),
            encoding="utf-8",
        )
        source = self._make_source("fallback.bin", "fallback body\n")
        validation = {
            "allowed": True,
            "current_state": "compiled",
            "next_state": "staged",
            "lane_id": "content_publishing",
            "state_source": "legacy_assumption",
            "gate": "publication_policy",
            "policy_id": "publication_policy",
            "policy_result": {"allowed": True, "failures": []},
            "reason": None,
        }

        with (
            patch.object(curate, "validate_transition", return_value=validation),
            patch.object(curate, "emit_transition_event"),
        ):
            result = curate.curate_file(source, enforce_governor=False)

        expected_root = self.repo_root / "data" / "archive"
        self.assertEqual(result["action"], "created")
        self.assertTrue(str(result["output_path"]).startswith(str(expected_root)))
        self.assertTrue(Path(result["output_path"]).exists())

    def test_curate_file_dedups_same_content_across_filenames(self) -> None:
        source_one = self._make_source("draft_one.md", "same content\n")
        source_two = self._make_source("draft_two.md", "same content\n")
        validation = {
            "allowed": True,
            "current_state": "compiled",
            "next_state": "staged",
            "lane_id": "content_publishing",
            "state_source": "legacy_assumption",
            "gate": "publication_policy",
            "policy_id": "publication_policy",
            "policy_result": {"allowed": True, "failures": []},
            "reason": None,
        }

        with (
            patch.object(curate, "validate_transition", return_value=validation),
            patch.object(curate, "emit_transition_event"),
        ):
            created = curate.curate_file(source_one, enforce_governor=False)
            deduped = curate.curate_file(source_two, enforce_governor=False)

        self.assertEqual(created["action"], "created")
        self.assertEqual(deduped["action"], "deduped")
        self.assertEqual(deduped["output_path"], created["output_path"])
        self.assertTrue(source_two.exists())

        entries = [
            json.loads(line)
            for line in self.registry_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(len(entries), 1)

    def test_curate_file_detects_registry_drift_when_output_missing(self) -> None:
        source = self._make_source("drift.md", "drift body\n")
        file_hash = curate.get_file_hash(source)
        stale_output = self.route_root / f"drift__{file_hash}.md"
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.registry_path.write_text(
            json.dumps(
                {
                    "sha256": file_hash,
                    "path": str(stale_output),
                    "route": "docs",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        result = curate.curate_file(source, enforce_governor=False)

        self.assertEqual(result["action"], "error")
        self.assertEqual(result["reason"], "registry_drift_missing_output")
        self.assertEqual(result["output_path"], str(stale_output))
        self.assertTrue(source.exists())
        self.assertEqual(list(self.route_root.glob("*")), [])

    def test_curate_file_rejects_unregistered_existing_output_collision(self) -> None:
        source = self._make_source("collision.md", "collision body\n")
        file_hash = curate.get_file_hash(source)
        collision_path = self.route_root / f"collision__{file_hash}.md"
        self.route_root.mkdir(parents=True, exist_ok=True)
        collision_path.write_text("existing body\n", encoding="utf-8")
        validation = {
            "allowed": True,
            "current_state": "compiled",
            "next_state": "staged",
            "lane_id": "content_publishing",
            "state_source": "legacy_assumption",
            "gate": "publication_policy",
            "policy_id": "publication_policy",
            "policy_result": {"allowed": True, "failures": []},
            "reason": None,
        }

        with (
            patch.object(curate, "validate_transition", return_value=validation),
            patch.object(curate, "emit_transition_event"),
        ):
            result = curate.curate_file(source, enforce_governor=False)

        self.assertEqual(result["action"], "error")
        self.assertEqual(result["reason"], "unregistered_existing_output")
        self.assertTrue(source.exists())
        self.assertFalse(self.registry_path.exists())
        self.assertEqual(collision_path.read_text(encoding="utf-8"), "existing body\n")

    def test_curate_file_handoff_does_not_create_capture_lifecycle_paths(self) -> None:
        source = self._make_source("handoff.md", "handoff body\n")
        validation = {
            "allowed": True,
            "current_state": "compiled",
            "next_state": "staged",
            "lane_id": "content_publishing",
            "state_source": "legacy_assumption",
            "gate": "publication_policy",
            "policy_id": "publication_policy",
            "policy_result": {"allowed": True, "failures": []},
            "reason": None,
        }

        with (
            patch.object(curate, "validate_transition", return_value=validation),
            patch.object(curate, "emit_transition_event"),
        ):
            result = curate.curate_file(source, enforce_governor=False)

        self.assertEqual(result["action"], "created")
        self.assertFalse((self.repo_root / "data" / "capture").exists())

    def test_curate_file_tolerates_corrupt_registry_lines_before_valid_match(self) -> None:
        source_one = self._make_source("valid.md", "valid body\n")
        validation = {
            "allowed": True,
            "current_state": "compiled",
            "next_state": "staged",
            "lane_id": "content_publishing",
            "state_source": "legacy_assumption",
            "gate": "publication_policy",
            "policy_id": "publication_policy",
            "policy_result": {"allowed": True, "failures": []},
            "reason": None,
        }

        with (
            patch.object(curate, "validate_transition", return_value=validation),
            patch.object(curate, "emit_transition_event"),
        ):
            created = curate.curate_file(source_one, enforce_governor=False)

        self.registry_path.write_text(
            "{not json}\n" + self.registry_path.read_text(encoding="utf-8"),
            encoding="utf-8",
        )

        source_two = self._make_source("valid_copy.md", "valid body\n")
        deduped = curate.curate_file(source_two, enforce_governor=False)

        self.assertEqual(created["action"], "created")
        self.assertEqual(deduped["action"], "deduped")
        self.assertEqual(deduped["output_path"], created["output_path"])

    def test_curate_file_returns_blocked_when_governor_blocks(self) -> None:
        source = self._make_source("governed.md", "governed body\n")

        with patch.object(
            curate,
            "_enforce_curate_governor",
            return_value={"decision": "BLOCK", "reason": "quota_exceeded"},
        ):
            result = curate.curate_file(source, enforce_governor=True)

        self.assertEqual(result["action"], "blocked")
        self.assertEqual(result["reason"], "quota_exceeded")
        self.assertTrue(source.exists())
