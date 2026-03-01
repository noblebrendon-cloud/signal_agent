"""
OIL -- Artifact and Case Verifier (v0.8)

Checks structural integrity of artifact envelopes and case bundles.

Usage:
  python -m oil.run_verify [--max-artifacts 200] [--artifacts-dir <path>]
                           [--cases-dir <path>]

Checks per artifact:
  - JSON is valid and parseable.
  - Required envelope fields present and non-empty:
    artifact_version, oil_version, created_utc, run_id, inputs_digest.
  - run_id derivable from stored (created_utc, inputs_digest) and consistent.

Checks per case bundle:
  - incident.json is valid JSON.
  - memory.json is valid JSON.
  - sha256(incident.json bytes) == sha256(original artifact bytes at
    memory["artifact_path"]) -- verifies case copy integrity.

Output:
  A deterministic JSON report to stdout:
  {
    "verified_count": N,
    "failed_count": M,
    "failures": [{"run_id": "...", "reason": "..."}]
  }

Exit codes: 0 = all verified, 1 = failures present or error.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

_OIL_ROOT = Path(__file__).resolve().parent
_DEFAULT_ARTIFACTS_DIR = _OIL_ROOT / "artifacts"
_DEFAULT_CASES_DIR = _OIL_ROOT / "cases"

_REQUIRED_ENVELOPE_FIELDS = [
    "artifact_version",
    "oil_version",
    "created_utc",
    "run_id",
    "inputs_digest",
]


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _derive_run_id(created_utc: str, inputs_digest: str) -> str:
    payload = created_utc + "|" + inputs_digest
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def verify_artifacts(
    artifacts_dir: Path,
    max_artifacts: int = 200,
) -> list[dict]:
    """Verify artifact envelopes. Returns list of failure dicts."""
    failures = []
    if not artifacts_dir.exists():
        return failures

    artifact_files = sorted(artifacts_dir.glob("incident_*.json"))[:max_artifacts]
    for af in artifact_files:
        run_id = af.stem.split("_")[-1] if "_" in af.stem else af.stem
        try:
            text = af.read_text(encoding="utf-8")
            envelope = json.loads(text)
        except (OSError, json.JSONDecodeError) as exc:
            failures.append({"run_id": run_id, "reason": f"parse_error: {exc}"})
            continue

        # Field presence check
        for field in _REQUIRED_ENVELOPE_FIELDS:
            if not envelope.get(field):
                failures.append({
                    "run_id": run_id,
                    "reason": f"missing_field: {field}",
                })
                break
        else:
            # run_id consistency check
            stored_rid = envelope.get("run_id", "")
            computed_rid = _derive_run_id(
                envelope.get("created_utc", ""),
                envelope.get("inputs_digest", ""),
            )
            if stored_rid != computed_rid:
                failures.append({
                    "run_id": stored_rid,
                    "reason": (
                        f"run_id_mismatch: stored={stored_rid} "
                        f"computed={computed_rid}"
                    ),
                })

    return failures


def verify_cases(cases_dir: Path) -> list[dict]:
    """Verify case bundles. Returns list of failure dicts."""
    failures = []
    if not cases_dir.exists():
        return failures

    for case_dir in sorted(cases_dir.iterdir()):
        if not case_dir.is_dir():
            continue
        run_id = case_dir.name
        # Skip non-run-id directories (e.g. __pycache__, .git)
        if not all(c in "0123456789abcdef" for c in run_id) or len(run_id) < 8:
            continue

        incident_path = case_dir / "incident.json"
        memory_path = case_dir / "memory.json"

        # Validate incident.json exists and parses
        if not incident_path.exists():
            failures.append({"run_id": run_id, "reason": "case_missing_incident_json"})
            continue
        try:
            incident_bytes = incident_path.read_bytes()
            json.loads(incident_bytes)
        except (OSError, json.JSONDecodeError) as exc:
            failures.append({"run_id": run_id, "reason": f"case_incident_parse_error: {exc}"})
            continue

        # Validate memory.json exists and parses
        if not memory_path.exists():
            failures.append({"run_id": run_id, "reason": "case_missing_memory_json"})
            continue
        try:
            memory = json.loads(memory_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            failures.append({"run_id": run_id, "reason": f"case_memory_parse_error: {exc}"})
            continue

        # Cross-check incident.json against original artifact
        artifact_path_str = memory.get("artifact_path", "")
        if not artifact_path_str:
            # No artifact_path in memory.json -- skip cross-check
            continue
        artifact_path = Path(artifact_path_str)
        if not artifact_path.exists():
            failures.append({
                "run_id": run_id,
                "reason": f"case_artifact_missing: {artifact_path}",
            })
            continue

        artifact_digest = _sha256_bytes(artifact_path.read_bytes())
        incident_digest = _sha256_bytes(incident_bytes)
        if artifact_digest != incident_digest:
            failures.append({
                "run_id": run_id,
                "reason": (
                    f"case_incident_digest_mismatch: "
                    f"incident={incident_digest[:12]} "
                    f"artifact={artifact_digest[:12]}"
                ),
            })

    return failures


def run_verification(
    artifacts_dir: Path,
    cases_dir: Path,
    max_artifacts: int = 200,
) -> dict:
    """Run all verification checks and return report dict."""
    artifact_failures = verify_artifacts(artifacts_dir, max_artifacts)
    case_failures = verify_cases(cases_dir)
    all_failures = artifact_failures + case_failures
    # Deduplicate failures by (run_id, reason)
    seen = set()
    deduped = []
    for f in all_failures:
        key = (f.get("run_id", ""), f.get("reason", ""))
        if key not in seen:
            seen.add(key)
            deduped.append(f)

    total_artifacts = len(list(artifacts_dir.glob("incident_*.json"))) if artifacts_dir.exists() else 0
    total_cases = sum(1 for p in cases_dir.iterdir() if p.is_dir()) if cases_dir.exists() else 0
    total_checked = min(total_artifacts, max_artifacts) + total_cases
    return {
        "verified_count": total_checked - len(deduped),
        "failed_count":   len(deduped),
        "failures":       deduped,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="oil.run_verify",
        description="OIL -- verify artifact and case bundle integrity",
    )
    parser.add_argument("--max-artifacts",  type=int, default=200)
    parser.add_argument("--artifacts-dir",  default=str(_DEFAULT_ARTIFACTS_DIR))
    parser.add_argument("--cases-dir",      default=str(_DEFAULT_CASES_DIR))
    args = parser.parse_args(argv)

    try:
        report = run_verification(
            artifacts_dir=Path(args.artifacts_dir),
            cases_dir=Path(args.cases_dir),
            max_artifacts=args.max_artifacts,
        )
        print(json.dumps(report, indent=2))
        return 0 if report["failed_count"] == 0 else 1
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
