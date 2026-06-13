from __future__ import annotations

import json
from pathlib import Path

from signal_agent.formal_governance.cli import main
from signal_agent.formal_governance.ledger import read_ledger_entries, verify_ledger


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "formal_governance"


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_cli_run_proof_pack_writes_expected_temp_outputs(tmp_path: Path, capsys) -> None:
    out_dir = tmp_path / "formal_governance_proof"

    exit_code = main(
        [
            "run-proof-pack",
            "--fixtures",
            str(FIXTURES),
            "--out",
            str(out_dir),
            "--timestamp",
            "2026-06-13T00:00:00Z",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    decisions_path = out_dir / "decisions.jsonl"
    ledger_path = out_dir / "governed_transition_ledger.jsonl"
    summary_path = out_dir / "proof_summary.md"
    decisions = _read_jsonl(decisions_path)
    ledger_entries = read_ledger_entries(ledger_path)

    assert exit_code == 0
    assert payload["clean"] is True
    assert payload["fixture_count"] == 10
    assert decisions_path.exists()
    assert ledger_path.exists()
    assert summary_path.exists()
    assert len(decisions) == 10
    assert len(ledger_entries) == 10
    assert all(row["passed"] is True for row in decisions)
    assert any(row["actual_decision"] == "BLOCK_DUPLICATE" for row in decisions)
    assert any(row["actual_decision"] == "DEFER_UNRESOLVED_TENSION" for row in decisions)
    assert any(row["actual_decision"] == "REJECT_SELF_CERTIFICATION" for row in decisions)
    assert "duplicate_transition" in summary_path.read_text(encoding="utf-8")
    assert verify_ledger(ledger_path)["clean"] is True

