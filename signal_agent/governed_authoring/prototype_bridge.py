from __future__ import annotations

from pathlib import Path
from typing import Any

from signal_agent.formal_governance.hashing import short_hash

from .models import OutputManifest, SourcePacket
from .runtime import GovernedAuthoringRuntime


PROTOTYPE_BRIDGE_SCHEMA_VERSION = "governed_authoring.prototype_bridge.v1"
PROTOTYPE_RESULT_SCHEMA_VERSION = "governed_authoring.prototype_result.v1"


class PrototypeBridgeError(ValueError):
    """Raised when strict bridge conversion finds blocking issues."""

    def __init__(self, issues: list[dict[str, Any]]) -> None:
        super().__init__(", ".join(issue["code"] for issue in issues if issue.get("severity") == "error"))
        self.issues = issues


def _as_mapping(value: Any) -> dict[str, Any]:
    return value if type(value) is dict else {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _bool(value: Any) -> bool:
    return value if isinstance(value, bool) else False


def _first_str(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _get(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def _clean_refs(*values: Any) -> list[str]:
    refs: list[str] = []
    for value in values:
        if isinstance(value, str) and value.strip():
            refs.append(value.strip())
        elif type(value) is dict:
            ref = _first_str(
                value.get("evidence_id"),
                value.get("evidenceId"),
                value.get("ref"),
                value.get("uri"),
                value.get("id"),
            )
            if ref:
                refs.append(ref)
        else:
            for item in _as_list(value):
                refs.extend(_clean_refs(item))
    return list(dict.fromkeys(refs))


def _normalize_requested_status(value: str) -> str:
    lowered = value.strip().lower().replace("-", "_").replace(" ", "_")
    if lowered in {"approved", "approve", "publication_ready", "publish_ready", "ready_to_publish"}:
        return "approved"
    if lowered in {"provisional", "unverified", "draft"}:
        return "provisional"
    if lowered in {"rejected", "deferred"}:
        return lowered
    return "provisional"


def _normalize_draft_mode(value: str, requested_status: str) -> str:
    lowered = value.strip().lower().replace("-", "_").replace(" ", "_")
    if lowered in {"publication_ready", "publish_ready", "approved"}:
        return "publication_ready"
    if lowered in {"provisional", "unverified", "draft"}:
        return "provisional"
    return "publication_ready" if requested_status == "approved" else "provisional"


def _normalize_review_decision(value: str) -> str:
    lowered = value.strip().lower().replace("-", "_").replace(" ", "_")
    if lowered in {"approved", "approve", "ready_to_continue", "ready", "accepted"}:
        return "approved"
    if lowered in {"rejected", "reject", "blocked"}:
        return "rejected"
    if lowered in {"deferred", "defer", "usable_with_revision", "needs_revision"}:
        return "deferred"
    return lowered


def _source_text_from_intake(intake: dict[str, Any]) -> str:
    parts = []
    for label, key in (
        ("source notes", "sourceNotes"),
        ("important fragments", "importantFragments"),
        ("existing structure", "existingStructure"),
    ):
        value = _str(intake.get(key)).strip()
        if value:
            parts.append(f"{label}: {value}")
    return "\n\n".join(parts)


def _evidence_refs_from_prototype(packet: dict[str, Any]) -> list[str]:
    intake = _as_mapping(packet.get("intake"))
    evidence = _as_mapping(packet.get("evidence"))
    governance = _as_mapping(packet.get("governance"))
    refs = _clean_refs(
        packet.get("evidence_refs"),
        packet.get("evidenceRefs"),
        packet.get("evidenceReferences"),
        intake.get("evidence_refs"),
        intake.get("evidenceRefs"),
        evidence.get("refs"),
        evidence.get("evidence_refs"),
        evidence.get("evidenceRefs"),
        evidence.get("references"),
        governance.get("evidence_refs"),
        governance.get("evidenceRefs"),
    )
    for source in _as_list(packet.get("source_material")):
        refs.extend(_clean_refs(_as_mapping(source).get("evidence_refs")))
        refs.extend(_clean_refs(_as_mapping(source).get("evidenceRefs")))
    for claim in _as_list(packet.get("claims")):
        refs.extend(_clean_refs(_as_mapping(claim).get("evidence_refs")))
        refs.extend(_clean_refs(_as_mapping(claim).get("evidenceRefs")))
    return list(dict.fromkeys(refs))


def _source_material_from_prototype(packet: dict[str, Any], evidence_refs: list[str]) -> list[dict[str, Any]]:
    explicit = _as_list(packet.get("source_material")) or _as_list(packet.get("sourceMaterial"))
    if explicit:
        materials = []
        for item in explicit:
            source = _as_mapping(item)
            source_refs = _clean_refs(source.get("evidence_refs"), source.get("evidenceRefs"))
            materials.append(
                {
                    "source_id": _first_str(source.get("source_id"), source.get("sourceId"), source.get("id"))
                    or f"prototype.source.{short_hash(source)}",
                    "text": _str(source.get("text")),
                    "uri": _first_str(source.get("uri"), source.get("source_uri"), source.get("sourceUri")),
                    "content_hash": _first_str(source.get("content_hash"), source.get("contentHash")),
                    "evidence_refs": source_refs or list(evidence_refs),
                }
            )
        return materials

    intake = _as_mapping(packet.get("intake"))
    text = _source_text_from_intake(intake)
    uri = _first_str(intake.get("sourceUri"), intake.get("source_uri"), packet.get("source_uri"), packet.get("sourceUri"))
    if not text and not uri:
        return []
    source_id = _first_str(intake.get("sourceId"), intake.get("source_id"), packet.get("source_packet_id"))
    return [
        {
            "source_id": source_id or f"prototype.source.{short_hash({'text': text, 'uri': uri})}",
            "text": text,
            "uri": uri,
            "content_hash": "",
            "evidence_refs": list(evidence_refs),
        }
    ]


def _claims_from_prototype(packet: dict[str, Any], evidence_refs: list[str], requested_status: str) -> list[dict[str, Any]]:
    explicit = _as_list(packet.get("claims"))
    if explicit:
        claims = []
        for item in explicit:
            claim = _as_mapping(item)
            statement = _first_str(claim.get("statement"), claim.get("core_assertion"), claim.get("coreAssertion"))
            claim_refs = _clean_refs(claim.get("evidence_refs"), claim.get("evidenceRefs")) or list(evidence_refs)
            claims.append(
                {
                    "claim_id": _first_str(claim.get("claim_id"), claim.get("claimId"), claim.get("id"))
                    or f"prototype.claim.{short_hash(statement)}",
                    "statement": statement,
                    "evidence_refs": claim_refs,
                    "status": _first_str(claim.get("status")) or (
                        "publication_ready" if requested_status == "approved" else "provisional"
                    ),
                }
            )
        return claims

    intake = _as_mapping(packet.get("intake"))
    source_text = _source_text_from_intake(intake)
    statement = _first_str(
        intake.get("desiredOutput"),
        intake.get("whyItMatters"),
        source_text,
        packet.get("title"),
    )
    if not statement:
        return []
    return [
        {
            "claim_id": f"prototype.claim.{short_hash({'statement': statement, 'source': source_text})}",
            "statement": statement,
            "evidence_refs": list(evidence_refs),
            "status": "publication_ready" if requested_status == "approved" else "provisional",
        }
    ]


def _tensions_from_prototype(packet: dict[str, Any]) -> list[dict[str, Any]]:
    governance = _as_mapping(packet.get("governance"))
    review = _as_mapping(packet.get("review"))
    raw_tensions = (
        _as_list(packet.get("unresolved_tensions"))
        or _as_list(packet.get("unresolvedTensions"))
        or _as_list(packet.get("tensions"))
        or _as_list(governance.get("unresolved_tensions"))
        or _as_list(governance.get("unresolvedTensions"))
        or _as_list(review.get("unresolved_tensions"))
        or _as_list(review.get("unresolvedTensions"))
    )
    tensions = []
    for item in raw_tensions:
        tension = _as_mapping(item)
        description = _first_str(tension.get("description"), tension.get("note"), tension.get("message"))
        tensions.append(
            {
                "tension_id": _first_str(tension.get("tension_id"), tension.get("tensionId"), tension.get("id"))
                or f"prototype.tension.{short_hash(tension)}",
                "description": description,
                "blocking": _bool(tension.get("blocking")),
                "severity": _first_str(tension.get("severity")) or "medium",
            }
        )
    return tensions


def _review_source(packet: dict[str, Any]) -> dict[str, Any]:
    review = _as_mapping(packet.get("review"))
    for value in (
        packet.get("review_decision"),
        packet.get("reviewDecision"),
        packet.get("human_review"),
        packet.get("humanReview"),
        review.get("review_decision"),
        review.get("reviewDecision"),
        review.get("human_review"),
        review.get("humanReview"),
    ):
        source = _as_mapping(value)
        if source:
            return source
    if any(key in review for key in ("actor_id", "actorId", "actor_type", "actorType", "decision", "self_certified", "selfCertified")):
        return review
    return {}


def _review_decision_from_prototype(packet: dict[str, Any]) -> dict[str, Any] | None:
    source = _review_source(packet)
    if not source:
        return None
    review = _as_mapping(packet.get("review"))
    decision = _normalize_review_decision(
        _first_str(source.get("decision"), source.get("status"), review.get("status"))
    )
    return {
        "review_decision_id": _first_str(
            source.get("review_decision_id"),
            source.get("reviewDecisionId"),
            source.get("id"),
        )
        or f"prototype.review.{short_hash(source)}",
        "actor_id": _first_str(source.get("actor_id"), source.get("actorId"), source.get("reviewer_id"), source.get("reviewerId")),
        "actor_type": _first_str(
            source.get("actor_type"),
            source.get("actorType"),
            source.get("reviewer_type"),
            source.get("reviewerType"),
        ),
        "role": _first_str(source.get("role")) or "authoring_reviewer",
        "scope": _first_str(source.get("scope")) or "governed_authoring_output",
        "decision": decision,
        "timestamp": _first_str(
            source.get("timestamp"),
            source.get("reviewed_at"),
            source.get("reviewedAt"),
            source.get("reviewTimestamp"),
        ),
        "self_certified": _bool(source.get("self_certified")) or _bool(source.get("selfCertified")),
    }


def prototype_to_source_packet(prototype_packet: dict[str, Any], *, strict: bool = False) -> dict[str, Any]:
    """Convert a static prototype/localStorage-style packet into a backend source packet."""

    packet = _as_mapping(prototype_packet)
    intake = _as_mapping(packet.get("intake"))
    governance = _as_mapping(packet.get("governance"))
    requested_status = _normalize_requested_status(
        _first_str(
            governance.get("requested_output_status"),
            governance.get("requestedOutputStatus"),
            packet.get("requested_output_status"),
            packet.get("requestedOutputStatus"),
            packet.get("output_status"),
            packet.get("outputStatus"),
        )
    )
    draft_mode = _normalize_draft_mode(
        _first_str(
            governance.get("draft_mode"),
            governance.get("draftMode"),
            packet.get("draft_mode"),
            packet.get("draftMode"),
        ),
        requested_status,
    )
    evidence_refs = _evidence_refs_from_prototype(packet)
    source_packet = {
        "schema_version": "governed_authoring.source_packet.v1",
        "source_packet_id": _first_str(
            packet.get("source_packet_id"),
            packet.get("sourcePacketId"),
            packet.get("id"),
        )
        or f"prototype.source_packet.{short_hash(packet)}",
        "requested_output_status": requested_status,
        "draft_mode": draft_mode,
        "title": _first_str(intake.get("projectTitle"), packet.get("title")),
        "source_material": _source_material_from_prototype(packet, evidence_refs),
        "claims": _claims_from_prototype(packet, evidence_refs, requested_status),
        "evidence_refs": evidence_refs,
        "unresolved_tensions": _tensions_from_prototype(packet),
        "review_decision": _review_decision_from_prototype(packet),
    }
    if strict:
        issues = validate_source_packet_for_bridge(source_packet, prototype_packet=packet)
        errors = [issue for issue in issues if issue.get("severity") == "error"]
        if errors:
            raise PrototypeBridgeError(errors)
    return source_packet


def validate_source_packet_for_bridge(
    source_packet: dict[str, Any],
    *,
    prototype_packet: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    packet = SourcePacket.from_dict(source_packet)
    issues: list[dict[str, Any]] = []

    if not packet.has_source_material():
        issues.append(
            {
                "severity": "error",
                "code": "missing_source_material",
                "message": "Prototype packet lacks source material for backend authoring.",
            }
        )
    if packet.is_publication_ready_request() and not packet.all_evidence_refs():
        issues.append(
            {
                "severity": "error",
                "code": "missing_evidence_refs",
                "message": "Publication-ready prototype packet lacks evidence references.",
            }
        )
    if packet.review_decision is not None and packet.review_decision.is_self_approval():
        issues.append(
            {
                "severity": "error",
                "code": "generator_self_approval",
                "message": "Generator/model/self-certified review cannot satisfy human approval.",
            }
        )
    source = _as_mapping(prototype_packet or {})
    intake = _as_mapping(source.get("intake"))
    if intake and not _bool(intake.get("privacyAck")):
        issues.append(
            {
                "severity": "warning",
                "code": "privacy_ack_missing",
                "message": "Prototype intake privacy acknowledgement is not present.",
            }
        )
    return issues


def bridge_prototype_packet(prototype_packet: dict[str, Any], *, strict: bool = False) -> dict[str, Any]:
    source_packet = prototype_to_source_packet(prototype_packet)
    issues = validate_source_packet_for_bridge(source_packet, prototype_packet=prototype_packet)
    if strict:
        errors = [issue for issue in issues if issue.get("severity") == "error"]
        if errors:
            raise PrototypeBridgeError(errors)
    return {
        "schema_version": PROTOTYPE_BRIDGE_SCHEMA_VERSION,
        "source_packet": source_packet,
        "bridge_issues": issues,
    }


def output_manifest_to_prototype_result(output_manifest: OutputManifest | dict[str, Any]) -> dict[str, Any]:
    manifest = output_manifest.to_dict() if isinstance(output_manifest, OutputManifest) else _as_mapping(output_manifest)
    return {
        "schema_version": PROTOTYPE_RESULT_SCHEMA_VERSION,
        "backend_output_manifest_id": _str(manifest.get("output_manifest_id")),
        "source_packet_id": _str(manifest.get("source_packet_id")),
        "draft_candidate_id": _str(manifest.get("draft_candidate_id")),
        "review_decision_id": _str(manifest.get("review_decision_id")),
        "output_status": _str(manifest.get("output_status")),
        "decision": _str(manifest.get("decision")),
        "decision_reason": _str(manifest.get("decision_reason")),
        "review_status": _prototype_review_status(_str(manifest.get("output_status"))),
        "evidence_refs": _clean_refs(manifest.get("evidence_refs")),
        "unresolved_tensions": [dict(item) for item in _as_list(manifest.get("unresolved_tensions")) if type(item) is dict],
        "messages": [str(item) for item in _as_list(manifest.get("messages"))],
        "canonical_ledger_entry_id": _str(manifest.get("canonical_ledger_entry_id")),
    }


def _prototype_review_status(output_status: str) -> str:
    if output_status == "approved":
        return "Approved by backend review"
    if output_status == "deferred":
        return "Deferred by backend review"
    if output_status == "rejected":
        return "Rejected by backend review"
    if output_status == "provisional":
        return "Provisional backend draft"
    return "Unknown backend result"


def backend_result_to_prototype_result(result: Any) -> dict[str, Any]:
    output_manifest = getattr(result, "output_manifest", None)
    payload = output_manifest_to_prototype_result(output_manifest)
    formal_decision = getattr(result, "formal_decision", None)
    if formal_decision is not None:
        payload["deterministic_decision_id"] = formal_decision.deterministic_decision_id
    return payload


def run_prototype_bridge(
    prototype_packet: dict[str, Any],
    *,
    canonical_ledger_path: Path | None = None,
    strict: bool = False,
) -> dict[str, Any]:
    bridge_packet = bridge_prototype_packet(prototype_packet, strict=strict)
    runtime = GovernedAuthoringRuntime(canonical_ledger_path=canonical_ledger_path)
    backend_result = runtime.run(bridge_packet["source_packet"])
    return {
        "schema_version": PROTOTYPE_BRIDGE_SCHEMA_VERSION,
        "source_packet": bridge_packet["source_packet"],
        "bridge_issues": bridge_packet["bridge_issues"],
        "backend_result": backend_result.to_dict(),
        "prototype_result": backend_result_to_prototype_result(backend_result),
    }
