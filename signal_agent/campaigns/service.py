"""Prepare campaign handoffs through the existing provisional authoring runtime.

No function in this module approves, publishes, generates media, or changes a
canonical campaign/artifact ledger. Source-to-Series tasks remain pending.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from signal_agent.governed_authoring import GovernedAuthoringRuntime, SourcePacket
from signal_agent.governed_authoring.path_policy import PathPolicyError, classify_path, require_allowed
from signal_agent.governed_authoring.workspace import LocalAuthoringWorkspace

from .core import CampaignValidationError, evaluate_campaign, load_principles, validate_campaign


class CampaignNotReadyError(ValueError):
    def __init__(self, message: str, *, decision: dict[str, Any]) -> None:
        super().__init__(message)
        self.decision = decision


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _identity(prefix: str, value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return prefix + "." + hashlib.sha256(raw).hexdigest()[:24]


def build_handoff(campaign: dict[str, Any], *, evaluated_at: str) -> dict[str, Any]:
    """Return a deterministic, in-memory provisional handoff and real gate result."""
    context = validate_campaign(campaign)
    decision = evaluate_campaign(context, evaluated_at=evaluated_at)
    if not decision["production_eligible"]:
        raise CampaignNotReadyError(
            "This decision is not eligible for a provisional production handoff.", decision=decision,
        )
    sources = context["sources"]
    if not sources or any(not item.get("text", "").strip() for item in sources):
        raise CampaignNotReadyError(
            "Readable text is required for every production source; a URI alone is not retrieved source material.",
            decision=decision,
        )
    if not context["requested_outputs"]:
        raise CampaignNotReadyError("At least one requested output is required.", decision=decision)
    if not context["claims"]:
        raise CampaignNotReadyError(
            "At least one explicit source-linked claim is required; the campaign adapter must not invent a truncated claim.",
            decision=decision,
        )

    source_material = []
    evidence_refs: list[str] = []
    for item in sources:
        digest = hashlib.sha256(item["text"].encode("utf-8")).hexdigest()
        claimed = item.get("content_hash") or ""
        if claimed and claimed.removeprefix("sha256:") != digest:
            raise CampaignValidationError("Source content hash does not match its exact UTF-8 text.")
        source_material.append({
            "source_id": item["source_id"], "text": item["text"],
            "uri": item.get("uri", ""), "content_hash": digest,
            "evidence_refs": list(item.get("evidence_refs", [])),
        })
        evidence_refs.extend(item.get("evidence_refs", []))
    for claim in context["claims"]:
        evidence_refs.extend(claim["evidence_refs"])
    evidence_refs = list(dict.fromkeys(evidence_refs))

    tensions = [
        {"tension_id": "unverified-claim." + claim["claim_id"],
         "description": "Claim remains unverified: " + claim["statement"],
         "blocking": True, "severity": "high"}
        for claim in context["claims"] if claim["status"] == "unverified"
    ]
    source_packet = SourcePacket.from_dict({
        "schema_version": "governed_authoring.source_packet.v1",
        "source_packet_id": _identity("campaign-source", {
            "campaign_id": context["campaign_id"], "campaign_digest": decision["campaign_digest"],
        }),
        "requested_output_status": "provisional", "draft_mode": "provisional",
        "title": context["title"], "source_material": source_material,
        "claims": context["claims"], "evidence_refs": evidence_refs,
        "unresolved_tensions": tensions, "review_decision": None,
    })
    result = GovernedAuthoringRuntime().run(source_packet)
    if result.output_manifest.output_status != "provisional":
        raise CampaignNotReadyError("Existing authoring governance did not admit a provisional draft.", decision=decision)
    if result.review_decision is not None or result.canonical_ledger_entry is not None:
        raise RuntimeError("Unexpected authority or canonical write in provisional authoring result.")

    source_ids = [item["source_id"] for item in source_material]
    claim_ids = [item["claim_id"] for item in context["claims"]]
    tasks = [
        {
            "task_id": _identity("campaign-task", {"decision": decision["decision_id"], "output": output}),
            "output_id": output["output_id"], "kind": output["kind"],
            "description": output["description"], "status": "pending",
            "source_ids": list(source_ids), "claim_ids": list(claim_ids),
        }
        for output in context["requested_outputs"]
    ]
    catalog = load_principles()
    principles = {item["id"]: item for item in catalog["principles"]}
    production_packet = {
        "schema_version": "source_to_series.task_packet.v1",
        "packet_id": _identity("source-to-series", {"decision": decision["decision_id"], "tasks": tasks}),
        "executor": "source-to-series", "campaign_id": context["campaign_id"],
        "campaign_digest": decision["campaign_digest"], "decision_id": decision["decision_id"],
        "source_packet_id": source_packet.source_packet_id,
        "catalog_version": decision["catalog_version"],
        "catalog_digest": decision["catalog_digest"],
        "catalog_notice": catalog["interpretation_notice"],
        "proposed_action": decision["proposed_action"],
        "working_hypothesis": decision["working_hypothesis"],
        "lineage": context.get("lineage"),
        "purpose": context["purpose"], "constraints": list(context["constraints"]),
        "principle_ids": list(context["principle_ids"]),
        "principle_guidance": [principles[key] for key in context["principle_ids"]],
        "evidence_limits": list(decision["limitations"]),
        "source_refs": [{key: item[key] for key in ("source_id", "uri", "content_hash")} for item in source_material],
        "claim_refs": [dict(claim) for claim in context["claims"]],
        "tasks": tasks, "publication_authorized": False,
        "source_fidelity_requirements": [
            "Preserve source meaning, qualifications, and evidence references.",
            "Retain source and parent decision identifiers on every derivative.",
            "Propagate corrections to affected derivatives before release.",
            "Treat supplied claim statuses as attributed review records, not independent verification by this evaluator.",
        ],
        "execution_status": "pending_external_executor",
        "release_requirement": "Use existing human review and destination-specific release gates for actual outputs.",
    }
    material = {
        "schema_version": "campaign_handoff.v1", "campaign_id": context["campaign_id"],
        "campaign_digest": decision["campaign_digest"], "decision": decision,
        "source_packet": source_packet.to_dict(), "authoring_result": result.to_dict(),
        "production_packet": production_packet,
        "execution_status": "prepared_not_executed", "publication_authorized": False,
    }
    return {"handoff_id": _identity("campaign-handoff", material), **material}


def _safe_workspace(output_dir: Path | str, repo_root: Path | None) -> LocalAuthoringWorkspace:
    raw = Path(output_dir).expanduser()
    if ".." in raw.parts:
        raise PathPolicyError("FORBIDDEN_PARENT_TRAVERSAL", "Workspace path must not contain parent traversal.")
    candidate = raw.absolute()
    for part in (candidate, *candidate.parents):
        if part.is_symlink():
            raise PathPolicyError("AMBIGUOUS_PATH", "Workspace path must not contain symlinks.")
    root = candidate.resolve(strict=False)
    actual_repository = Path(__file__).resolve().parents[2]
    repository = Path(repo_root).resolve(strict=False) if repo_root else actual_repository
    protected = (".git", "app", "signal_agent", "config", "schemas", "tests", "docs")
    # An additional checkout supplied by a caller extends protection; it must
    # never remove the executing checkout's production/source boundaries.
    for checkout in {actual_repository, repository}:
        require_allowed(classify_path(candidate, repo_root=checkout, workspace_root=root))
        if root == checkout or any(root.is_relative_to(checkout / part) for part in protected):
            raise PathPolicyError("FORBIDDEN_OUTPUT_PATH", "Use a separate workspace, outside repository source directories.")
    if root.exists():
        raise PathPolicyError("OVERWRITE_DENIED", "Handoff export requires a new workspace directory.")
    return LocalAuthoringWorkspace.validate(root, repo_root=repository)


def _summary(context: dict[str, Any], handoff: dict[str, Any]) -> str:
    decision = handoff["decision"]
    tasks = handoff["production_packet"]["tasks"]
    lines = [
        "# Campaign production handoff", "", f"Campaign: {context['title']}", "",
        f"Purpose: {context['purpose']}", "",
        f"Proposed next action: {decision['proposed_action']}", "",
        "Status: provisional authoring metadata prepared; production tasks remain pending.",
        "Publication authority: none granted by this handoff.", "", "## Decision reasons", "",
    ]
    lines.extend("- " + reason for reason in decision["reasons"])
    lines.extend(["", "## Pending production tasks", ""])
    lines.extend(f"- {task['output_id']} ({task['kind']}): {task['description']}" for task in tasks)
    lines.extend([
        "", "## Provenance", "",
        f"Campaign digest: {handoff['campaign_digest']}",
        f"Decision: {decision['decision_id']}",
        f"Source packet: {handoff['source_packet']['source_packet_id']}",
        f"Handoff: {handoff['handoff_id']}", "",
        "The source packet preserves the exact source text and its UTF-8 SHA-256.",
        "Claim statuses are caller-supplied assessments. Output is provisional.",
        "The governed authoring runtime created metadata, not prose, images, audio, or video.",
        "Use the pending task packet with Source to Series; retain evidence, qualifications, and correction links.",
        "Actual production, human approval, delivery, and audience outcomes require separate receipts.", "",
    ])
    return "\n".join(lines)


def write_handoff(
    campaign: dict[str, Any], *, evaluated_at: str,
    output_dir: Path | str, repo_root: Path | None = None,
) -> dict[str, Any]:
    """Write a new guarded workspace; refuse overwrite and production paths."""
    context = validate_campaign(campaign)
    handoff = build_handoff(context, evaluated_at=evaluated_at)
    workspace = _safe_workspace(output_dir, repo_root)
    payloads = {
        "inputs/campaign_context.json": _json_bytes(context),
        "inputs/source_packet.json": _json_bytes(handoff["source_packet"]),
        "results/authoring_result.json": _json_bytes(handoff["authoring_result"]),
        "metadata/campaign_decision.json": _json_bytes(handoff["decision"]),
        "metadata/source_to_series_task_packet.json": _json_bytes(handoff["production_packet"]),
        "metadata/campaign_handoff.json": _json_bytes(handoff),
        "summaries/handoff.md": _summary(context, handoff).encode("utf-8"),
    }
    checksums = {name: hashlib.sha256(raw).hexdigest() for name, raw in payloads.items()}
    payloads["validation/checksums.json"] = _json_bytes({
        "schema_version": "campaign_handoff_checksums.v1",
        "handoff_id": handoff["handoff_id"], "algorithm": "sha256", "files": checksums,
    })
    # Exclusive directory creation prevents a retry or concurrent run overwriting
    # the same workspace. An interrupted export remains visibly incomplete.
    workspace.root.mkdir(parents=True, exist_ok=False)
    workspace.create_layout()
    validators = {
        "results": workspace.validate_result_path,
        "metadata": workspace.validate_metadata_path,
        "summaries": workspace.validate_summary_path,
        "validation": workspace.validate_validation_path,
    }
    destinations: dict[str, Path] = {}
    for name in payloads:
        path = workspace.root / name
        first = name.split("/", 1)[0]
        if first == "inputs":
            require_allowed(workspace.classify(path))
            if path.exists() or path.is_symlink():
                raise PathPolicyError("OVERWRITE_DENIED", "Input export already exists.")
            destinations[name] = path
        else:
            destinations[name] = validators[first](path)
    for name, path in destinations.items():
        with path.open("xb") as handle:
            handle.write(payloads[name])
    return {
        "schema_version": "campaign_export_receipt.v1",
        "workspace": str(workspace.root), "handoff_id": handoff["handoff_id"],
        "campaign_id": context["campaign_id"], "status": "prepared_not_executed",
        "files": {name: str(path) for name, path in destinations.items()},
        "sha256": {name: hashlib.sha256(raw).hexdigest() for name, raw in payloads.items()},
        "publication_authorized": False,
    }
