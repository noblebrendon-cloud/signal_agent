from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


SELF_OBSERVATION_REPORT_VERSION = "self_observation_report.v1"
REVIEW_ARTIFACT_VERSION = "self_observation_review_artifact.v1"
REVIEW_EVENT_VERSION = "self_observation_review_event.v1"

ALLOWED_PROPOSAL_TYPES = {
    "instrumentation_proposal",
    "workflow_proposal",
    "policy_proposal",
    "no_action_monitor_only",
}
ALLOWED_INITIAL_REVIEW_STATES = {"observed", "queued_for_review"}
ALLOWED_DECISION_STATES = {
    "accepted_for_proposal",
    "rejected",
    "deferred",
    "superseded",
}

NON_AUTHORITY_DISCLAIMER = (
    "This self-observation review record is a non-authoritative human review "
    "input. It does not approve implementation, policy changes, workflow "
    "changes, gate changes, code execution, or canonical state mutation. "
    "Accepted review items are only eligible for later governed-proposal intake."
)

_FORBIDDEN_REPO_OUTPUT_ROOTS = {
    "app",
    "config",
    "constraints",
    "formal_governance",
    "governance",
    "signal_agent",
}
_JSON_INDENT = 2
_ID_LENGTH = 24


def build_review_artifact(
    *,
    repo_root: Path | str,
    report_path: Path | str,
    candidate_id: str,
    proposal_type: str,
    initial_review_state: str,
    created_by: str,
    created_at: str,
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    report_file = _resolve_input_path(root, report_path)
    report_bytes = report_file.read_bytes()
    report_sha256 = hashlib.sha256(report_bytes).hexdigest()
    report = _load_json_object(report_bytes, source=report_file)

    if report.get("schema_version") != SELF_OBSERVATION_REPORT_VERSION:
        raise ValueError("source report must use schema_version self_observation_report.v1")
    if proposal_type not in ALLOWED_PROPOSAL_TYPES:
        raise ValueError(f"unsupported proposal_type: {proposal_type}")
    if initial_review_state not in ALLOWED_INITIAL_REVIEW_STATES:
        raise ValueError(f"unsupported initial_review_state: {initial_review_state}")
    created_by = _require_text(created_by, "created_by")
    created_at = _require_text(created_at, "created_at")
    candidate_id = _require_text(candidate_id, "candidate_id")

    candidate = _find_candidate(report, candidate_id)
    evidence_references = _candidate_evidence_references(candidate)
    evidence_quality = _candidate_evidence_quality(candidate)
    evidence_hash = _stable_hash(evidence_references)
    artifact_id = _review_artifact_id(
        report_sha256=report_sha256,
        candidate_id=candidate_id,
        proposal_type=proposal_type,
        evidence_hash=evidence_hash,
        initial_review_state=initial_review_state,
        created_by=created_by,
        created_at=created_at,
    )

    return {
        "review_artifact_id": artifact_id,
        "schema_version": REVIEW_ARTIFACT_VERSION,
        "source_report_path": str(report_file),
        "source_report_sha256": report_sha256,
        "source_report_schema_version": report["schema_version"],
        "candidate_id": candidate_id,
        "finding_type": "subsystem_candidate",
        "proposal_type": proposal_type,
        "evidence_references": evidence_references,
        "evidence_quality": evidence_quality,
        "initial_review_state": initial_review_state,
        "created_at": created_at,
        "created_by": created_by,
        "non_authority_disclaimer": NON_AUTHORITY_DISCLAIMER,
    }


def create_review_artifact(
    *,
    repo_root: Path | str,
    report_path: Path | str,
    output_dir: Path | str,
    candidate_id: str,
    proposal_type: str,
    initial_review_state: str,
    created_by: str,
    created_at: str,
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    artifact = build_review_artifact(
        repo_root=root,
        report_path=report_path,
        candidate_id=candidate_id,
        proposal_type=proposal_type,
        initial_review_state=initial_review_state,
        created_by=created_by,
        created_at=created_at,
    )
    output_root = _validate_review_output_dir(root, output_dir)
    artifact_dir = output_root / "artifacts"
    artifact_json = artifact_dir / f"{artifact['review_artifact_id']}.json"
    artifact_markdown = artifact_dir / f"{artifact['review_artifact_id']}.md"
    if artifact_json.exists() or artifact_markdown.exists():
        raise ValueError(f"review artifact already exists: {artifact['review_artifact_id']}")

    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_json.write_text(_stable_json(artifact), encoding="utf-8")
    artifact_markdown.write_text(render_review_artifact_markdown(artifact), encoding="utf-8")
    return {
        "review_artifact_id": artifact["review_artifact_id"],
        "artifact_json_path": str(artifact_json),
        "artifact_markdown_path": str(artifact_markdown),
    }


def build_decision_event(
    *,
    artifact: Mapping[str, Any],
    decision_state: str,
    decided_by: str,
    decision_reason: str,
    decided_at: str,
) -> dict[str, Any]:
    if artifact.get("schema_version") != REVIEW_ARTIFACT_VERSION:
        raise ValueError("artifact must use schema_version self_observation_review_artifact.v1")
    if decision_state not in ALLOWED_DECISION_STATES:
        raise ValueError(f"unsupported decision_state: {decision_state}")
    decided_by = _require_text(decided_by, "decided_by")
    decision_reason = _require_text(decision_reason, "decision_reason")
    decided_at = _require_text(decided_at, "decided_at")
    review_artifact_id = _require_text(
        str(artifact.get("review_artifact_id") or ""),
        "review_artifact_id",
    )
    candidate_id = _require_text(str(artifact.get("candidate_id") or ""), "candidate_id")
    source_report_sha256 = _require_text(
        str(artifact.get("source_report_sha256") or ""),
        "source_report_sha256",
    )
    decision_record_id = _decision_record_id(
        review_artifact_id=review_artifact_id,
        decision_state=decision_state,
        decided_by=decided_by,
        decision_reason=decision_reason,
        decided_at=decided_at,
    )
    return {
        "decision_record_id": decision_record_id,
        "schema_version": REVIEW_EVENT_VERSION,
        "review_artifact_id": review_artifact_id,
        "decision_state": decision_state,
        "decided_by": decided_by,
        "decision_reason": decision_reason,
        "decided_at": decided_at,
        "source_report_sha256": source_report_sha256,
        "candidate_id": candidate_id,
        "non_authority_disclaimer": NON_AUTHORITY_DISCLAIMER,
    }


def record_review_decision(
    *,
    repo_root: Path | str,
    artifact_path: Path | str,
    output_dir: Path | str,
    decision_state: str,
    decided_by: str,
    decision_reason: str,
    decided_at: str,
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    artifact_file = _validate_review_artifact_path(root, artifact_path)
    artifact = _load_json_object(artifact_file.read_bytes(), source=artifact_file)
    event = build_decision_event(
        artifact=artifact,
        decision_state=decision_state,
        decided_by=decided_by,
        decision_reason=decision_reason,
        decided_at=decided_at,
    )
    output_root = _validate_review_output_dir(root, output_dir)
    decision_log = output_root / "decisions.jsonl"
    _append_decision_event(decision_log, event)
    return {
        "decision_record_id": event["decision_record_id"],
        "decision_log_path": str(decision_log),
    }


def render_review_artifact_markdown(artifact: Mapping[str, Any]) -> str:
    lines = [
        "# Self-Observation Review Artifact",
        "",
        f"- schema_version: {_scalar(artifact.get('schema_version'))}",
        f"- review_artifact_id: {_scalar(artifact.get('review_artifact_id'))}",
        f"- candidate_id: {_scalar(artifact.get('candidate_id'))}",
        f"- finding_type: {_scalar(artifact.get('finding_type'))}",
        f"- proposal_type: {_scalar(artifact.get('proposal_type'))}",
        f"- initial_review_state: {_scalar(artifact.get('initial_review_state'))}",
        f"- source_report_path: {_scalar(artifact.get('source_report_path'))}",
        f"- source_report_sha256: {_scalar(artifact.get('source_report_sha256'))}",
        f"- source_report_schema_version: {_scalar(artifact.get('source_report_schema_version'))}",
        f"- created_by: {_scalar(artifact.get('created_by'))}",
        f"- created_at: {_scalar(artifact.get('created_at'))}",
        "",
        "## Evidence Quality",
    ]
    lines.extend(_markdown_json_block(artifact.get("evidence_quality")))
    lines.extend(["", "## Evidence References"])
    lines.extend(_markdown_json_block(artifact.get("evidence_references")))
    lines.extend(
        [
            "",
            "## Non-Authority Disclaimer",
            "",
            _scalar(artifact.get("non_authority_disclaimer")),
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            result = create_review_artifact(
                repo_root=args.repo_root,
                report_path=args.report,
                output_dir=args.output_dir,
                candidate_id=args.candidate_id,
                proposal_type=args.proposal_type,
                initial_review_state=args.initial_review_state,
                created_by=args.created_by,
                created_at=args.created_at,
            )
        elif args.command == "decide":
            result = record_review_decision(
                repo_root=args.repo_root,
                artifact_path=args.artifact,
                output_dir=args.output_dir,
                decision_state=args.decision_state,
                decided_by=args.decided_by,
                decision_reason=args.decision_reason,
                decided_at=args.decided_at,
            )
        else:
            parser.error("a command is required")
    except (OSError, ValueError) as exc:
        print(f"self-observation review loop failed: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result, sort_keys=True, indent=_JSON_INDENT))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create governed self-observation review artifacts and decisions.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create")
    create.add_argument("--repo-root", default=".")
    create.add_argument("--report", required=True)
    create.add_argument("--output-dir", required=True)
    create.add_argument("--candidate-id", required=True)
    create.add_argument("--proposal-type", required=True, choices=sorted(ALLOWED_PROPOSAL_TYPES))
    create.add_argument(
        "--initial-review-state",
        required=True,
        choices=sorted(ALLOWED_INITIAL_REVIEW_STATES),
    )
    create.add_argument("--created-by", required=True)
    create.add_argument("--created-at", required=True)

    decide = subparsers.add_parser("decide")
    decide.add_argument("--repo-root", default=".")
    decide.add_argument("--artifact", required=True)
    decide.add_argument("--output-dir", required=True)
    decide.add_argument("--decision-state", required=True, choices=sorted(ALLOWED_DECISION_STATES))
    decide.add_argument("--decided-by", required=True)
    decide.add_argument("--decision-reason", required=True)
    decide.add_argument("--decided-at", required=True)
    return parser


def _find_candidate(report: Mapping[str, Any], candidate_id: str) -> Mapping[str, Any]:
    candidates = report.get("subsystem_candidates")
    if not isinstance(candidates, list):
        raise ValueError("source report does not contain subsystem_candidates")
    for candidate in candidates:
        if isinstance(candidate, Mapping) and candidate.get("candidate_id") == candidate_id:
            return candidate
    raise ValueError(f"candidate_id not found in source report: {candidate_id}")


def _candidate_evidence_references(candidate: Mapping[str, Any]) -> dict[str, Any]:
    evidence = candidate.get("evidence")
    involved = candidate.get("involved_files_or_events")
    has_evidence = isinstance(evidence, list) and len(evidence) > 0
    has_involved = isinstance(involved, list) and len(involved) > 0
    if not has_evidence and not has_involved:
        raise ValueError("candidate does not contain exact evidence references")
    return {
        "candidate_evidence": evidence if has_evidence else [],
        "involved_files_or_events": involved if has_involved else [],
    }


def _candidate_evidence_quality(candidate: Mapping[str, Any]) -> Any:
    if "evidence_quality" in candidate:
        return candidate["evidence_quality"]
    return {
        "status": "unavailable",
        "reason": "candidate_evidence_quality_not_present_in_report",
    }


def _validate_review_output_dir(repo_root: Path, output_dir: Path | str) -> Path:
    review_root = (repo_root / "data" / "analytics" / "review").resolve()
    candidate = Path(output_dir)
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    resolved = candidate.resolve()
    _reject_forbidden_repo_path(repo_root, resolved)
    try:
        resolved.relative_to(review_root)
    except ValueError as exc:
        raise ValueError(
            "review output directory must resolve inside data/analytics/review"
        ) from exc
    return resolved


def _validate_review_artifact_path(repo_root: Path, artifact_path: Path | str) -> Path:
    review_root = (repo_root / "data" / "analytics" / "review").resolve()
    candidate = Path(artifact_path)
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    resolved = candidate.resolve()
    _reject_forbidden_repo_path(repo_root, resolved)
    try:
        resolved.relative_to(review_root / "artifacts")
    except ValueError as exc:
        raise ValueError("artifact path must resolve inside data/analytics/review/artifacts") from exc
    if not resolved.exists():
        raise ValueError(f"artifact path does not exist: {resolved}")
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
        raise ValueError(f"review output path is inside forbidden root: {parts[0]}")
    if parts[0] == "data" and len(parts) > 1 and parts[1] == "state":
        raise ValueError("review output path must not be inside data/state")


def _resolve_input_path(repo_root: Path, input_path: Path | str) -> Path:
    candidate = Path(input_path)
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    resolved = candidate.resolve()
    if not resolved.exists():
        raise ValueError(f"input path does not exist: {resolved}")
    return resolved


def _append_decision_event(decision_log: Path, event: Mapping[str, Any]) -> None:
    if _decision_record_exists(decision_log, str(event["decision_record_id"])):
        raise ValueError(f"decision record already exists: {event['decision_record_id']}")
    decision_log.parent.mkdir(parents=True, exist_ok=True)
    with open(decision_log, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _decision_record_exists(decision_log: Path, decision_record_id: str) -> bool:
    if not decision_log.exists():
        return False
    for line_number, raw_line in enumerate(decision_log.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"decision log contains malformed JSON at line {line_number}"
            ) from exc
        if isinstance(row, Mapping) and row.get("decision_record_id") == decision_record_id:
            return True
    return False


def _review_artifact_id(
    *,
    report_sha256: str,
    candidate_id: str,
    proposal_type: str,
    evidence_hash: str,
    initial_review_state: str,
    created_by: str,
    created_at: str,
) -> str:
    token = _stable_hash(
        {
            "report_sha256": report_sha256,
            "candidate_id": candidate_id,
            "proposal_type": proposal_type,
            "evidence_hash": evidence_hash,
            "initial_review_state": initial_review_state,
            "created_by": created_by,
            "created_at": created_at,
        }
    )
    return f"sora_{token[:_ID_LENGTH]}"


def _decision_record_id(
    *,
    review_artifact_id: str,
    decision_state: str,
    decided_by: str,
    decision_reason: str,
    decided_at: str,
) -> str:
    token = _stable_hash(
        {
            "review_artifact_id": review_artifact_id,
            "decision_state": decision_state,
            "decided_by": decided_by,
            "decision_reason": decision_reason,
            "decided_at": decided_at,
        }
    )
    return f"sord_{token[:_ID_LENGTH]}"


def _load_json_object(raw_bytes: bytes, *, source: Path) -> dict[str, Any]:
    try:
        payload = json.loads(raw_bytes.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {source}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"JSON document must be an object: {source}")
    return payload


def _require_text(value: str, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required")
    return text


def _stable_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _stable_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, indent=_JSON_INDENT) + "\n"


def _markdown_json_block(value: Any) -> list[str]:
    return ["", "```json", json.dumps(value, sort_keys=True, indent=_JSON_INDENT), "```"]


def _scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
