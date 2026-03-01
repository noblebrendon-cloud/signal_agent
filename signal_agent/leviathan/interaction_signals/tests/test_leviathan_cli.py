"""Tests for leviathan CLI deterministic single-shot behavior."""
from __future__ import annotations

import io
import json
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout

from signal_agent.leviathan.cli.leviathan_cli import main as cli_main


def _run_cli(args: list[str]) -> tuple[int, str, str]:
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli_main(args)
    return code, out.getvalue(), err.getvalue()


def _assert_rounded_six(obj: object) -> None:
    if isinstance(obj, float):
        assert abs(obj - round(obj, 6)) < 1e-12
        return
    if isinstance(obj, dict):
        for v in obj.values():
            _assert_rounded_six(v)
        return
    if isinstance(obj, list):
        for v in obj:
            _assert_rounded_six(v)


class TestLeviathanCli(unittest.TestCase):
    def test_single_shot_json_is_deterministic(self):
        args = ["--text", "Deterministic proof text", "--json", "--actor", "alice", "--thread", "t1"]
        c1, o1, e1 = _run_cli(args)
        c2, o2, e2 = _run_cli(args)
        self.assertEqual(c1, 0)
        self.assertEqual(c2, 0)
        self.assertEqual(e1, "")
        self.assertEqual(e2, "")
        self.assertEqual(o1, o2)

    def test_json_output_valid_and_wired(self):
        code, out, err = _run_cli(["--text", "Signal check text", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        payload = json.loads(out)
        self.assertIn("event", payload)
        self.assertIn("features", payload)
        self.assertIn("signal", payload)
        self.assertIn("actor_state", payload)
        self.assertIn("thread_state", payload)
        self.assertIn("controller", payload)
        self.assertIn("policy", payload)
        self.assertEqual(payload["policy"]["policy_version"], "0.3")
        self.assertEqual(payload["policy"]["reasons"], sorted(payload["policy"]["reasons"]))
        _assert_rounded_six(payload)

    def test_python_m_leviathan_entrypoint_works(self):
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "leviathan.cli.leviathan_cli",
                "--text",
                "module entrypoint",
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["event"]["actor_id"], "cli_user")
        self.assertIn("signal", payload)


if __name__ == "__main__":
    unittest.main()

