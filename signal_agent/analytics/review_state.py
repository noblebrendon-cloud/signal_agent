from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


REVIEW_ARTIFACT_VERSION = "self_observation_review_artifact.v1"
REVIEW_EVENT_VERSION = "self_observation_review_event.v1"
REVIEW_RESOLUTION_VERSION = "self_observation_review_resolution.v1"

_REQUIRED_ARTIFACT_FIELDS = (
    "review_artifact_id",
    "source_report_sha256",
    "candidate_id",
    "evidence_references",
    "non_authority_disclaimer",
    "initial_review_state",
)
_REQUIRED_DECISION_FIELDS = (
    "review_artifact_id",
    "source_report_sha256",
    "candidate_id",
    "decision_record_id",
    "decision_state",
    "decided_by",
    "decision_reason",
    "decided_at",
    "non_authority_disclaimer",
)


def resolve_review_state(
    *,
    repo_root: Path | str,
    artifact_path: Path | str,
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    artifact_file = _validate_artifact_path(root, artifact_path)
    artifact = _load_json_object(artifact_file)
    _validate_artifact(artifact)

    matching_events = _matching_decision_events(
        decision_log=root / "data" / "analytics" / "review" / "decisions.jsonl",
        artifact=artifact,
    )
    if matching_events:
        latest_line_number, latest_event = matching_events[-1]
        resolved_review_state = latest_event["decision_state"]
        latest_decision_record_id = latest_event["decision_record_id"]
        resolution_method = "latest_matching_decision_event"
    else:
        latest_line_number = None
        latest_decision_record_id = None
        resolved_review_state = artifact["initial_review_state"]
        resolution_method = "artifact_initial_review_state"

    return {
        "schema_version": REVIEW_RESOLUTION_VERSION,
        "review_artifact_id": artifact["review_artifact_id"],
        "candidate_id": artifact["candidate_id"],
        "source_report_sha256": artifact["source_report_sha256"],
        "initial_review_state": artifact["initial_review_state"],
        "resolved_review_state": resolved_review_state,
        "matching_decision_event_count": len(matching_events),
        "latest_decision_record_id": latest_decision_record_id,
        "latest_decision_line_number": latest_line_number,
        "resolution_method": resolution_method,
        "non_authority_disclaimer": artifact["non_authority_disclaimer"],
    }


def render_review_resolution_json(resolution: Mapping[str, Any]) -> str:
    return json.dumps(resolution, sort_keys=True, indent=2) + "\n"


def render_review_resolution_markdown(resolution: Mapping[str, Any]) -> str:
    lines = [
        "# Self-Observation Review Resolution",
        "",
        f"- schema_version: {_scalar(resolution.get('schema_version'))}",
        f"- review_artifact_id: {_scalar(resolution.get('review_artifact_id'))}",
        f"- candidate_id: {_scalar(resolution.get('candidate_id'))}",
        f"- source_report_sha256: {_scalar(resolution.get('source_report_sha256'))}",
        f"- initial_review_state: {_scalar(resolution.get('initial_review_state'))}",
        f"- resolved_review_state: {_scalar(resolution.get('resolved_review_state'))}",
        f"- matching_decision_event_count: {_scalar(resolution.get('matching_decision_event_count'))}",
        f"- latest_decision_record_id: {_scalar(resolution.get('latest_decision_record_id'))}",
        f"- latest_decision_line_number: {_scalar(resolution.get('latest_decision_line_number'))}",
        f"- resolution_method: {_scalar(resolution.get('resolution_method'))}",
        "",
        "## Non-Authority Disclaimer",
        "",
        _scalar(resolution.get("non_authority_disclaimer")),
        "",
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command != "resolve":
            parser.error("a command is required")
        resolution = resolve_review_state(
            repo_root=args.repo_root,
            artifact_path=args.artifact,
        )
    except (OSError, ValueError) as exc:
        print(f"self-observation review state failed: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(render_review_resolution_json(resolution), end="")
    else:
        print(render_review_resolution_markdown(resolution), end="")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Resolve read-only self-observation review state from artifacts and decisions.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    resolve = subparsers.add_parser("resolve")
    resolve.add_argument("--repo-root", default=".")
    resolve.add_argument("--artifact", required=True)
    resolve.add_argument("--format", choices=("json", "markdown"), default="json")
    return parser


def _matching_decision_events(
    *,
    decision_log: Path,
    artifact: Mapping[str, Any],
) -> list[tuple[int, dict[str, Any]]]:
    if not decision_log.exists():
        return []

    artifact_id = str(artifact["review_artifact_id"])
    seen_decision_ids: set[str] = set()
    matching_events: list[tuple[int, dict[str, Any]]] = []
    for line_number, raw_line in enumerate(decision_log.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"decision log contains malformed JSON at line {line_number}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"decision log row must be an object at line {line_number}")

        decision_record_id = row.get("decision_record_id")
        if decision_record_id:
            decision_record_id = str(decision_record_id)
            if decision_record_id in seen_decision_ids:
                raise ValueError(f"duplicate decision_record_id at line {line_number}: {decision_record_id}")
            seen_decision_ids.add(decision_record_id)

        if row.get("review_artifact_id") != artifact_id:
            continue
        _validate_matching_decision(row, line_number=line_number, artifact=artifact)
        matching_events.append((line_number, row))
    return matching_events


def _validate_artifact_path(repo_root: Path, artifact_path: Path | str) -> Path:
    artifact_root = (repo_root / "data" / "analytics" / "review" / "artifacts").resolve()
    candidate = Path(artifact_path)
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(artifact_root)
    except ValueError as exc:
        raise ValueError("artifact path must resolve inside data/analytics/review/artifacts") from exc
    if not resolved.exists():
        raise ValueError(f"artifact path does not exist: {resolved}")
    return resolved


def _validate_artifact(artifact: Mapping[str, Any]) -> None:
    if artifact.get("schema_version") != REVIEW_ARTIFACT_VERSION:
        raise ValueError("artifact must use schema_version self_observation_review_artifact.v1")
    for field_name in _REQUIRED_ARTIFACT_FIELDS:
        if not _has_required_value(artifact.get(field_name)):
            raise ValueError(f"artifact is missing required field: {field_name}")


def _validate_matching_decision(
    row: Mapping[str, Any],
    *,
    line_number: int,
    artifact: Mapping[str, Any],
) -> None:
    if row.get("schema_version") != REVIEW_EVENT_VERSION:
        raise ValueError(
            f"matching decision at line {line_number} must use schema_version "
            "self_observation_review_event.v1"
        )
    for field_name in _REQUIRED_DECISION_FIELDS:
        if not _has_required_value(row.get(field_name)):
            raise ValueError(
                f"matching decision at line {line_number} is missing required field: {field_name}"
            )
    if row.get("source_report_sha256") != artifact.get("source_report_sha256"):
        raise ValueError(f"matching decision at line {line_number} has conflicting source_report_sha256")
    if row.get("candidate_id") != artifact.get("candidate_id"):
        raise ValueError(f"matching decision at line {line_number} has conflicting candidate_id")


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"JSON document must be an object: {path}")
    return payload


def _has_required_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple, set)):
        return bool(value)
    return True


def _scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
