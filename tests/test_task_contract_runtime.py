from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.audit.runtime_audit import run_postflight, run_preflight
from app.audit.task_contract import evaluate_contract, validate_task_contract


class TestTaskContractRuntime(unittest.TestCase):
    def test_contract_validator_accepts_valid_schema(self) -> None:
        contract = {
            "objective": "Run deterministic audit",
            "constraints": ["No network"],
            "acceptance": ["path_exists:data/state/preflight.json"],
            "required_artifacts": ["data/state/preflight.json"],
            "stop_conditions": {
                "phi_threshold": 0.8,
                "breaker_open": True,
                "max_retries": 3,
            },
            "run_mode": "one_shot",
        }
        self.assertEqual(validate_task_contract(contract), [])

    def test_contract_validator_rejects_invalid_acceptance(self) -> None:
        contract = {
            "objective": "Run deterministic audit",
            "constraints": ["No network"],
            "acceptance": ["manual_review_required"],
            "required_artifacts": ["data/state/preflight.json"],
            "stop_conditions": {
                "phi_threshold": 0.8,
                "breaker_open": True,
                "max_retries": 3,
            },
            "run_mode": "one_shot",
        }
        errors = validate_task_contract(contract)
        self.assertTrue(any("acceptance entries must use supported checks" in err for err in errors))

    def test_preflight_runs_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "app").mkdir()
            (root / "tests").mkdir()

            contract_path = root / "task_contract.yaml"
            contract_path.write_text(
                "\n".join(
                    [
                        'objective: "Offline preflight"',
                        "constraints: ['No network']",
                        "acceptance: ['path_exists:data/state/preflight.json']",
                        "required_artifacts: ['data/state/preflight.json']",
                        "stop_conditions:",
                        "  phi_threshold: 0.8",
                        "  breaker_open: true",
                        "  max_retries: 3",
                        "run_mode: one_shot",
                    ]
                ),
                encoding="utf-8",
            )

            codex_home = root / ".codex"
            (codex_home / "rules").mkdir(parents=True)
            (codex_home / "version.json").write_text(
                json.dumps({"latest_version": "0.104.0"}),
                encoding="utf-8",
            )
            (codex_home / "config.toml").write_text(
                'model = "gpt-5.3-codex"\n',
                encoding="utf-8",
            )
            (codex_home / "rules" / "default.rules").write_text(
                'prefix_rule(pattern=["python","-m","pytest"], decision="allow")\n',
                encoding="utf-8",
            )

            output_path = root / "data" / "state" / "preflight.json"
            with patch("socket.create_connection", side_effect=AssertionError("network must not be used")):
                payload = run_preflight(
                    repo_root=root,
                    contract_path=contract_path,
                    output_path=output_path,
                    codex_home=codex_home,
                )

            self.assertTrue(output_path.exists())
            self.assertIn("checks", payload)
            self.assertIn("runtime", payload)
            self.assertEqual(payload["runtime"]["model_id"], "gpt-5.3-codex")

    def test_contract_eval_fails_when_artifacts_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            contract = {
                "objective": "Evaluate artifacts",
                "constraints": ["No network"],
                "acceptance": ["path_exists:data/state/preflight.json"],
                "required_artifacts": ["missing/output.json"],
                "stop_conditions": {
                    "phi_threshold": 0.8,
                    "breaker_open": True,
                    "max_retries": 2,
                },
                "run_mode": "one_shot",
            }

            result = evaluate_contract(contract, root)
            self.assertFalse(result["passed"])
            self.assertFalse(result["required_artifacts"][0]["exists"])

    def test_postflight_writes_contract_eval_for_missing_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "app").mkdir()
            (root / "tests").mkdir()
            contract_path = root / "task_contract.yaml"
            contract_path.write_text(
                "\n".join(
                    [
                        'objective: "Postflight contract eval"',
                        "constraints: ['No network']",
                        "acceptance: ['path_exists:data/state/preflight.json']",
                        "required_artifacts: ['missing/artifact.txt']",
                        "stop_conditions:",
                        "  phi_threshold: 0.8",
                        "  breaker_open: true",
                        "  max_retries: 1",
                        "run_mode: one_shot",
                    ]
                ),
                encoding="utf-8",
            )

            codex_home = root / ".codex"
            (codex_home / "rules").mkdir(parents=True)
            (codex_home / "sessions" / "2026" / "02" / "25").mkdir(parents=True)
            (codex_home / "log").mkdir(parents=True)
            (codex_home / ".sandbox").mkdir(parents=True)
            (codex_home / "version.json").write_text(
                json.dumps({"latest_version": "0.104.0"}),
                encoding="utf-8",
            )
            (codex_home / "config.toml").write_text(
                'model = "gpt-5.3-codex"\n',
                encoding="utf-8",
            )
            (codex_home / "rules" / "default.rules").write_text(
                "prefix_rule(pattern=['python'], decision='allow')\n",
                encoding="utf-8",
            )
            (codex_home / "log" / "codex-tui.log").write_text("", encoding="utf-8")
            (codex_home / ".sandbox" / "sandbox.log").write_text("", encoding="utf-8")

            rollout_path = codex_home / "sessions" / "2026" / "02" / "25" / "rollout-test.jsonl"
            rollout_path.write_text(
                json.dumps(
                    {
                        "type": "response_item",
                        "payload": {
                            "type": "function_call_output",
                            "output": "Exit code: 0\nWall time: 0.1 seconds\nOutput:\nOK",
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            preflight_path = root / "data" / "state" / "preflight.json"
            run_preflight(
                repo_root=root,
                contract_path=contract_path,
                output_path=preflight_path,
                codex_home=codex_home,
            )

            postflight_path = root / "data" / "state" / "postflight.json"
            contract_eval_path = root / "data" / "state" / "contract_eval.json"
            _, contract_eval = run_postflight(
                repo_root=root,
                contract_path=contract_path,
                preflight_path=preflight_path,
                postflight_path=postflight_path,
                contract_eval_path=contract_eval_path,
                codex_home=codex_home,
            )

            self.assertTrue(postflight_path.exists())
            self.assertTrue(contract_eval_path.exists())
            self.assertFalse(contract_eval["passed"])
            self.assertFalse(contract_eval["required_artifacts"][0]["exists"])


if __name__ == "__main__":
    unittest.main()
