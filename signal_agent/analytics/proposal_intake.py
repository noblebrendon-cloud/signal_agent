from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .review_state import render_review_resolution_json, resolve_review_state


REVIEW_ARTIFACT_VERSION = "self_observation_review_artifact.v1"
REVIEW_EVENT_VERSION = "self_observation_review_event.v1"
INTAKE_CANDIDATE_VERSION = "self_observation_proposal_intake_candidate.v1"

NON_AUTHORITY_DISCLAIMER = (
    "This self-observation proposal-intake candidate is noncanonical handoff "
    "evidence only. It does not create a governed proposal, approve "
    "implementation, authorize policy changes, authorize workflow changes, "
    "authorize gate changes, execute code, or mutate canonical state."
)

_REQUIRED_ARTIFACT_FIELDS = (
    "review_artifact_id",
    "source_report_sha256",
    "source_report_schema_version",
    "candidate_id",
    "proposal_type",
    "finding_type",
    "evidence_references",
    "evidence_quality",
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
_FORBIDDEN_REPO_OUTPUT_ROOTS = {
    "app",
    "config",
    "constraints",
    "formal_governance",
    "governance",
    "signal_agent",
}
_ID_LENGTH = 24


def build_intake_candidate(
    *,
    repo_root: Path | str,
    artifact_path: Path | str,
    authorized_by: str,
    authorized_at: str,
    authorization_rationale: str,
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    artifact_file = _validate_artifact_path(root, artifact_path)
    artifact = _load_json_object(artifact_file)
    _validate_artifact(artifact)

    decision_log = root / "data" / "analytics" / "review" / "decisions.jsonl"
    if not decision_log.exists():
        raise ValueError("decisions.jsonl is required for proposal-intake candidate creation")

    resolution = resolve_review_state(repo_root=root, artifact_path=artifact_file)
    if resolution.get("resolved_review_state") != "accepted_for_proposal":
        raise ValueError("proposal intake requires resolved_review_state accepted_for_proposal")
    latest_decision_id = _require_text(
        str(resolution.get("latest_decision_record_id") or ""),
        "latest_decision_record_id",
    )
    latest_event = _latest_matching_decision_event(
        decision_log=decision_log,
        artifact=artifact,
        decision_record_id=latest_decision_id,
    )

    authorized_by = _require_text(authorized_by, "authorized_by")
    authorized_at = _require_text(authorized_at, "authorized_at")
    authorization_rationale = _require_text(
        authorization_rationale,
        "authorization_rationale",
    )
    source_resolution_sha256 = hashlib.sha256(
        render_review_resolution_json(resolution).encode("utf-8")
    ).hexdigest()
    evidence_hash = _stable_hash(artifact["evidence_references"])
    intake_candidate_id = _intake_candidate_id(
        source_review_artifact_id=artifact["review_artifact_id"],
        source_decision_record_id=latest_event["decision_record_id"],
        source_resolution_sha256=source_resolution_sha256,
        source_report_sha256=artifact["source_report_sha256"],
        candidate_id=artifact["candidate_id"],
        proposal_type=artifact["proposal_type"],
        evidence_hash=evidence_hash,
        authorized_by=authorized_by,
        authorized_at=authorized_at,
        authorization_rationale=authorization_rationale,
    )

    return {
        "intake_candidate_id": intake_candidate_id,
        "schema_version": INTAKE_CANDIDATE_VERSION,
        "source_review_artifact_id": artifact["review_artifact_id"],
        "source_decision_record_id": latest_event["decision_record_id"],
        "source_resolution_sha256": source_resolution_sha256,
        "source_report_sha256": artifact["source_report_sha256"],
        "source_report_schema_version": artifact["source_report_schema_version"],
        "candidate_id": artifact["candidate_id"],
        "proposal_type": artifact["proposal_type"],
        "finding_type": artifact["finding_type"],
        "evidence_references": artifact["evidence_references"],
        "evidence_quality": artifact["evidence_quality"],
        "resolved_review_state": "accepted_for_proposal",
        "human_intake_authorization": {
            "authorized_by": authorized_by,
            "authorized_at": authorized_at,
            "authorization_rationale": authorization_rationale,
            "authorization_scope": "intake_candidate_only",
        },
        "non_authority_to_authority_transition_rationale": authorization_rationale,
        "created_at": authorized_at,
        "created_by": authorized_by,
        "non_authority_disclaimer": NON_AUTHORITY_DISCLAIMER,
    }


def create_intake_candidate(
    *,
    repo_root: Path | str,
    artifact_path: Path | str,
    output_dir: Path | str,
    authorized_by: str,
    authorized_at: str,
    authorization_rationale: str,
) -> dict[str, str]:
    root = Path(repo_root).resolve()
    candidate = build_intake_candidate(
        repo_root=root,
        artifact_path=artifact_path,
        authorized_by=authorized_by,
        authorized_at=authorized_at,
        authorization_rationale=authorization_rationale,
    )
    output_root = _validate_intake_output_dir(root, output_dir)
    json_path = output_root / f"{candidate['intake_candidate_id']}.json"
    markdown_path = output_root / f"{candidate['intake_candidate_id']}.md"
    if json_path.exists() or markdown_path.exists():
        raise ValueError(f"proposal-intake candidate already exists: {candidate['intake_candidate_id']}")

    output_root.mkdir(parents=True, exist_ok=True)
    json_path.write_text(_stable_json(candidate), encoding="utf-8")
    markdown_path.write_text(render_intake_candidate_markdown(candidate), encoding="utf-8")
    return {
        "intake_candidate_id": candidate["intake_candidate_id"],
        "intake_candidate_json_path": str(json_path),
        "intake_candidate_markdown_path": str(markdown_path),
    }


def render_intake_candidate_markdown(candidate: Mapping[str, Any]) -> str:
    lines = [
        "# Self-Observation Proposal-Intake Candidate",
        "",
        f"- schema_version: {_scalar(candidate.get('schema_version'))}",
        f"- intake_candidate_id: {_scalar(candidate.get('intake_candidate_id'))}",
        f"- source_review_artifact_id: {_scalar(candidate.get('source_review_artifact_id'))}",
        f"- source_decision_record_id: {_scalar(candidate.get('source_decision_record_id'))}",
        f"- source_resolution_sha256: {_scalar(candidate.get('source_resolution_sha256'))}",
        f"- source_report_sha256: {_scalar(candidate.get('source_report_sha256'))}",
        f"- source_report_schema_version: {_scalar(candidate.get('source_report_schema_version'))}",
        f"- candidate_id: {_scalar(candidate.get('candidate_id'))}",
        f"- proposal_type: {_scalar(candidate.get('proposal_type'))}",
        f"- finding_type: {_scalar(candidate.get('finding_type'))}",
        f"- resolved_review_state: {_scalar(candidate.get('resolved_review_state'))}",
        f"- created_by: {_scalar(candidate.get('created_by'))}",
        f"- created_at: {_scalar(candidate.get('created_at'))}",
        "",
        "## Human Intake Authorization",
    ]
    lines.extend(_markdown_json_block(candidate.get("human_intake_authorization")))
    lines.extend(["", "## Evidence Quality"])
    lines.extend(_markdown_json_block(candidate.get("evidence_quality")))
    lines.extend(["", "## Evidence References"])
    lines.extend(_markdown_json_block(candidate.get("evidence_references")))
    lines.extend(
        [
            "",
            "## Non-Authority To Authority Transition Rationale",
            "",
            _scalar(candidate.get("non_authority_to_authority_transition_rationale")),
            "",
            "## Non-Authority Disclaimer",
            "",
            _scalar(candidate.get("non_authority_disclaimer")),
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command != "create":
            parser.error("a command is required")
        result = create_intake_candidate(
            repo_root=args.repo_root,
            artifact_path=args.artifact,
            output_dir=args.output_dir,
            authorized_by=args.authorized_by,
            authorized_at=args.authorized_at,
            authorization_rationale=args.authorization_rationale,
        )
    except (OSError, ValueError) as exc:
        print(f"self-observation proposal intake failed: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create noncanonical self-observation proposal-intake candidates.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("--repo-root", default=".")
    create.add_argument("--artifact", required=True)
    create.add_argument("--output-dir", required=True)
    create.add_argument("--authorized-by", required=True)
    create.add_argument("--authorized-at", required=True)
    create.add_argument("--authorization-rationale", required=True)
    return parser


def _latest_matching_decision_event(
    *,
    decision_log: Path,
    artifact: Mapping[str, Any],
    decision_record_id: str,
) -> dict[str, Any]:
    latest: dict[str, Any] | None = None
    for raw_line in decision_log.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            continue
        if row.get("review_artifact_id") != artifact["review_artifact_id"]:
            continue
        if row.get("decision_record_id") == decision_record_id:
            latest = row
    if latest is None:
        raise ValueError(f"latest matching decision event not found: {decision_record_id}")
    _validate_decision_event(latest, artifact=artifact)
    return latest


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


def _validate_intake_output_dir(repo_root: Path, output_dir: Path | str) -> Path:
    intake_root = (repo_root / "data" / "analytics" / "review" / "intake_candidates").resolve()
    candidate = Path(output_dir)
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    resolved = candidate.resolve()
    _reject_forbidden_repo_path(repo_root, resolved)
    try:
        resolved.relative_to(intake_root)
    except ValueError as exc:
        raise ValueError(
            "proposal-intake output directory must resolve inside data/analytics/review/intake_candidates"
        ) from exc
    return resolved


def _reject_forbidden_repo_path(repo_root: Path, resolved_path: Path) -> None:
    try:
        relative = resolved_path.relative_to(repo_root)
    except ValueError:
        return
    parts = relative.parts
    if not parts:
        return
    if parts[0] in _FORBIDDEN_REPO_OUTPUT_ROOTS:
        raise ValueError(f"proposal-intake output path is inside forbidden root: {parts[0]}")
    if parts[0] == "data" and len(parts) > 1 and parts[1] == "state":
        raise ValueError("proposal-intake output path must not be inside data/state")


def _validate_artifact(artifact: Mapping[str, Any]) -> None:
    if artifact.get("schema_version") != REVIEW_ARTIFACT_VERSION:
        raise ValueError("artifact must use schema_version self_observation_review_artifact.v1")
    for field_name in _REQUIRED_ARTIFACT_FIELDS:
        if not _has_required_value(artifact.get(field_name)):
            raise ValueError(f"artifact is missing required field: {field_name}")


def _validate_decision_event(row: Mapping[str, Any], *, artifact: Mapping[str, Any]) -> None:
    if row.get("schema_version") != REVIEW_EVENT_VERSION:
        raise ValueError("latest matching decision must use schema_version self_observation_review_event.v1")
    for field_name in _REQUIRED_DECISION_FIELDS:
        if not _has_required_value(row.get(field_name)):
            raise ValueError(f"latest matching decision is missing required field: {field_name}")
    if row.get("source_report_sha256") != artifact.get("source_report_sha256"):
        raise ValueError("latest matching decision has conflicting source_report_sha256")
    if row.get("candidate_id") != artifact.get("candidate_id"):
        raise ValueError("latest matching decision has conflicting candidate_id")
    if row.get("decision_state") != "accepted_for_proposal":
        raise ValueError("latest matching decision must be accepted_for_proposal")


def _intake_candidate_id(
    *,
    source_review_artifact_id: str,
    source_decision_record_id: str,
    source_resolution_sha256: str,
    source_report_sha256: str,
    candidate_id: str,
    proposal_type: str,
    evidence_hash: str,
    authorized_by: str,
    authorized_at: str,
    authorization_rationale: str,
) -> str:
    token = _stable_hash(
        {
            "source_review_artifact_id": source_review_artifact_id,
            "source_decision_record_id": source_decision_record_id,
            "source_resolution_sha256": source_resolution_sha256,
            "source_report_sha256": source_report_sha256,
            "candidate_id": candidate_id,
            "proposal_type": proposal_type,
            "evidence_hash": evidence_hash,
            "authorized_by": authorized_by,
            "authorized_at": authorized_at,
            "authorization_rationale": authorization_rationale,
        }
    )
    return f"soic_{token[:_ID_LENGTH]}"


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"JSON document must be an object: {path}")
    return payload


def _require_text(value: str, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required")
    return text


def _has_required_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple, set)):
        return bool(value)
    return True


def _stable_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _stable_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, indent=2) + "\n"


def _markdown_json_block(value: Any) -> list[str]:
    return ["", "```json", json.dumps(value, sort_keys=True, indent=2), "```"]


def _scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
