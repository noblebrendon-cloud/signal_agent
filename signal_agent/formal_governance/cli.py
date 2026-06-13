from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .decision import evaluate_transition
from .hashing import canonical_json
from .ledger import append_ledger_entry, read_ledger_entries
from .models import TransitionProposal


DEFAULT_PROOF_TIMESTAMP = "2026-06-13T00:00:00Z"


def _load_fixture(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if type(payload) is not dict:
        raise ValueError(f"Fixture must be an object: {path}")
    return payload


def _fixture_sort_key(path: Path) -> tuple[int, str]:
    payload = _load_fixture(path)
    run_order = payload.get("run_order")
    return (run_order if isinstance(run_order, int) else 1000, path.name)


def _guard_output_path(out_dir: Path) -> None:
    resolved = out_dir.resolve()
    cwd = Path.cwd().resolve()
    production_data = cwd / "data"
    try:
        is_production_data = resolved == production_data or production_data in resolved.parents
    except RuntimeError:
        is_production_data = False
    if is_production_data:
        raise ValueError("Formal governance proof pack must not write to production data/ ledgers.")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(canonical_json(row) + "\n" for row in rows)
    path.write_text(text, encoding="utf-8")


def _write_summary(path: Path, rows: list[dict]) -> None:
    lines = [
        "# Formal Governance Proof Summary",
        "",
        "| Fixture | Expected | Actual | Pass | Ledger Entry Written | Deterministic Decision ID |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| {fixture_name} | {expected_decision} | {actual_decision} | {passed} | {ledger_entry_written} | {deterministic_decision_id} |".format(
                **row
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_proof_pack(*, fixtures_dir: Path, out_dir: Path, timestamp: str) -> dict:
    _guard_output_path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    fixture_paths = sorted(Path(fixtures_dir).glob("*.json"), key=_fixture_sort_key)
    ledger_path = out_dir / "governed_transition_ledger.jsonl"
    decisions_path = out_dir / "decisions.jsonl"
    summary_path = out_dir / "proof_summary.md"

    rows: list[dict] = []
    for fixture_path in fixture_paths:
        fixture = _load_fixture(fixture_path)
        proposal = TransitionProposal.from_fixture(fixture)
        prior_entries = read_ledger_entries(ledger_path)
        decision = evaluate_transition(proposal, prior_entries=prior_entries)
        entry = append_ledger_entry(
            ledger_path,
            proposal=proposal,
            decision=decision,
            timestamp=timestamp,
        )
        expected = str(fixture.get("expected_decision", ""))
        actual = decision.decision.value
        rows.append(
            {
                "fixture_name": str(fixture.get("fixture_name") or fixture_path.stem),
                "fixture_path": str(fixture_path),
                "expected_decision": expected,
                "actual_decision": actual,
                "passed": expected == actual,
                "ledger_entry_written": bool(entry.get("ledger_entry_id")),
                "ledger_entry_id": entry.get("ledger_entry_id"),
                "deterministic_decision_id": decision.deterministic_decision_id,
                "decision_reason": decision.decision_reason,
            }
        )

    _write_jsonl(decisions_path, rows)
    _write_summary(summary_path, rows)

    passed = all(row["passed"] and row["ledger_entry_written"] for row in rows)
    return {
        "clean": passed,
        "fixture_count": len(rows),
        "passed_count": sum(1 for row in rows if row["passed"]),
        "failed_count": sum(1 for row in rows if not row["passed"]),
        "decisions_path": str(decisions_path),
        "ledger_path": str(ledger_path),
        "proof_summary_path": str(summary_path),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="formal-governance")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run-proof-pack")
    run.add_argument("--fixtures", required=True, type=Path)
    run.add_argument("--out", required=True, type=Path)
    run.add_argument("--timestamp", default=DEFAULT_PROOF_TIMESTAMP)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run-proof-pack":
        try:
            result = run_proof_pack(
                fixtures_dir=args.fixtures,
                out_dir=args.out,
                timestamp=args.timestamp,
            )
        except Exception as exc:
            print(canonical_json({"clean": False, "error": str(exc)}))
            return 1
        print(canonical_json(result))
        return 0 if result["clean"] else 1

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

