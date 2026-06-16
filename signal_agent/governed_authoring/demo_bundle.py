from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .offline_harness import run_offline_verification_file, write_static_import_packet


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "governed_authoring"
PRODUCTION_DATA_DIR = ROOT / "data"
DEMO_BUNDLE_SCHEMA_VERSION = "governed_authoring.demo_proof_bundle.v1"
CANONICAL_LEDGER_FILENAME = "canonical_governed_authoring.jsonl"
PROOF_SUMMARY_FILENAME = "proof_summary.md"


@dataclass(frozen=True)
class DemoFixture:
    filename: str
    expected_status: str
    expected_review_status: str


DEMO_FIXTURES: tuple[DemoFixture, ...] = (
    DemoFixture(
        filename="static_export_valid_provisional.json",
        expected_status="provisional",
        expected_review_status="Provisional backend draft",
    ),
    DemoFixture(
        filename="static_export_valid_approved.json",
        expected_status="approved",
        expected_review_status="Approved by backend review",
    ),
    DemoFixture(
        filename="static_export_missing_evidence.json",
        expected_status="rejected",
        expected_review_status="Rejected by backend review",
    ),
    DemoFixture(
        filename="static_export_blocking_tension.json",
        expected_status="deferred",
        expected_review_status="Deferred by backend review",
    ),
    DemoFixture(
        filename="static_export_generator_self_approval.json",
        expected_status="rejected",
        expected_review_status="Rejected by backend review",
    ),
)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _resolve_output_dir(out_dir: Path) -> Path:
    output_dir = Path(out_dir).resolve()
    production_data_dir = PRODUCTION_DATA_DIR.resolve()
    if output_dir == production_data_dir or _is_relative_to(output_dir, production_data_dir):
        raise ValueError(f"demo proof bundle output must not be under production data/: {output_dir}")
    return output_dir


def _result_filename(fixture_name: str) -> str:
    return f"{Path(fixture_name).stem}.result.json"


def _planned_output_paths(output_dir: Path, canonical_ledger: bool) -> list[Path]:
    paths = [output_dir / _result_filename(fixture.filename) for fixture in DEMO_FIXTURES]
    paths.append(output_dir / PROOF_SUMMARY_FILENAME)
    if canonical_ledger:
        paths.append(output_dir / CANONICAL_LEDGER_FILENAME)
    return paths


def _reject_existing_outputs(output_dir: Path, canonical_ledger: bool) -> None:
    existing = [path for path in _planned_output_paths(output_dir, canonical_ledger) if path.exists()]
    if existing:
        names = ", ".join(path.name for path in existing)
        raise FileExistsError(f"demo proof bundle output files already exist: {names}")


def _as_mapping(value: Any) -> dict[str, Any]:
    return value if type(value) is dict else {}


def _write_proof_summary(
    path: Path,
    *,
    entries: Sequence[dict[str, Any]],
    canonical_ledger_path: Path | None,
) -> None:
    lines = [
        "# Governed Authoring Demo Proof Bundle",
        "",
        "This local proof bundle runs representative static export fixtures through the offline Governed Authoring verification path.",
        "",
        "| Fixture | Expected result | Actual result | Pass/fail | Output packet path | Canonical ledger entry present |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for entry in entries:
        lines.append(
            "| {fixture_name} | {expected_result} | {actual_result} | {pass_fail} | {output_packet_path} | {canonical_ledger_entry_present} |".format(
                fixture_name=entry["fixture_name"],
                expected_result=entry["expected_result"],
                actual_result=entry["actual_result"],
                pass_fail="pass" if entry["pass"] else "fail",
                output_packet_path=entry["output_packet_path"],
                canonical_ledger_entry_present="yes" if entry["canonical_ledger_entry_present"] else "no",
            )
        )
    lines.extend(
        [
            "",
            f"Canonical ledger path: `{canonical_ledger_path}`" if canonical_ledger_path else "Canonical ledger path: not requested.",
            "",
            "Boundary: this bundle writes only to the chosen output directory. It does not add backend submission, production writes, or default production ledger writes.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_demo_bundle(
    out_dir: Path,
    *,
    canonical_ledger: bool = False,
    fixture_dir: Path = FIXTURE_DIR,
) -> dict[str, Any]:
    output_dir = _resolve_output_dir(out_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    _reject_existing_outputs(output_dir, canonical_ledger)
    canonical_ledger_path = output_dir / CANONICAL_LEDGER_FILENAME if canonical_ledger else None

    entries: list[dict[str, Any]] = []
    for fixture in DEMO_FIXTURES:
        fixture_path = Path(fixture_dir) / fixture.filename
        result = run_offline_verification_file(
            fixture_path,
            canonical_ledger_path=canonical_ledger_path,
        )
        output_packet_path = output_dir / _result_filename(fixture.filename)
        write_static_import_packet(output_packet_path, result)

        packet = _as_mapping(result.get("static_import_packet"))
        actual_status = str(packet.get("output_status", ""))
        actual_review_status = str(packet.get("review_status", ""))
        entry = {
            "fixture_name": fixture.filename,
            "expected_result": fixture.expected_status,
            "actual_result": actual_status,
            "expected_review_status": fixture.expected_review_status,
            "actual_review_status": actual_review_status,
            "pass": actual_status == fixture.expected_status
            and actual_review_status == fixture.expected_review_status,
            "output_packet_path": str(output_packet_path),
            "canonical_ledger_entry_present": bool(packet.get("canonical_ledger_entry_id")),
            "evidence_refs": list(packet.get("evidence_refs") or []),
            "unresolved_tensions": list(packet.get("unresolved_tensions") or []),
            "review_status": actual_review_status,
            "output_status": actual_status,
        }
        entries.append(entry)

    proof_summary_path = output_dir / PROOF_SUMMARY_FILENAME
    _write_proof_summary(
        proof_summary_path,
        entries=entries,
        canonical_ledger_path=canonical_ledger_path,
    )

    return {
        "schema_version": DEMO_BUNDLE_SCHEMA_VERSION,
        "output_dir": str(output_dir),
        "canonical_ledger_enabled": canonical_ledger,
        "canonical_ledger_path": str(canonical_ledger_path) if canonical_ledger_path else None,
        "proof_summary_path": str(proof_summary_path),
        "passed": all(entry["pass"] for entry in entries),
        "results": entries,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run representative Governed Authoring static export fixtures through the local proof path.",
    )
    parser.add_argument("--out", required=True, type=Path, help="Output directory for proof bundle files.")
    parser.add_argument(
        "--canonical-ledger",
        action="store_true",
        help="Write an optional canonical ledger JSONL file inside the output directory.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    try:
        summary = run_demo_bundle(args.out, canonical_ledger=args.canonical_ledger)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
