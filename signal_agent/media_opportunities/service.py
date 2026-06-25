from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, Iterable

from signal_agent.media_opportunities.ledgers import MediaOpportunityLedgers, repo_root
from signal_agent.media_opportunities.models import (
    DEFAULT_IDENTITY_PACKET,
    NON_INDEPENDENT_COVERAGE_TYPES,
    PUBLIC_EXPORT_KEYS,
    PUBLIC_REFERENCE_COVERAGE_TYPES,
    SAFETY_FLAGS,
    OpportunityRecord,
    is_owned_public_reference_url,
    is_public_http_url,
    normalize_text,
    normalized_text_items,
    optional,
    text_hash,
    transition_allowed,
    validate_relationship,
    validate_state,
)
from signal_agent.transport.ledgers import utc_now_iso
from signal_agent.transport.schemas import derive_id


class MediaOpportunityError(RuntimeError):
    pass


class MediaOpportunityService:
    def __init__(
        self,
        ledgers: MediaOpportunityLedgers | None = None,
        *,
        clock: Callable[[], str] = utc_now_iso,
        identity_packet_path: str | Path | None = None,
    ) -> None:
        self.clock = clock
        self.ledgers = ledgers or MediaOpportunityLedgers(clock=clock)
        self.identity_packet_path = Path(identity_packet_path) if identity_packet_path else _default_identity_packet_path()
        self.identity_packet = load_identity_packet(self.identity_packet_path)

    def create_opportunity(
        self,
        *,
        opportunity_type: str,
        original_request_text: str,
        outlet_or_organization: str | None = None,
        contact_or_source_name: str | None = None,
        originating_url_or_source_ref: str | None = None,
        topic_or_subject: str | None = None,
        deadline: str | None = None,
        relationship_classification: str = "unknown",
        visibility: str = "private",
        next_action: str | None = None,
        notes: str | None = None,
        source_metadata: dict[str, Any] | None = None,
        source_fingerprint: str | None = None,
    ) -> dict[str, Any]:
        record = OpportunityRecord.create(
            created_at=self.clock(),
            opportunity_type=opportunity_type,
            original_request_text=original_request_text,
            outlet_or_organization=outlet_or_organization,
            contact_or_source_name=contact_or_source_name,
            originating_url_or_source_ref=originating_url_or_source_ref,
            topic_or_subject=topic_or_subject,
            deadline=deadline,
            relationship_classification=relationship_classification,
            visibility=visibility,
            next_action=next_action,
            notes=notes,
            source_metadata=source_metadata,
            source_fingerprint=source_fingerprint,
        )
        if self._record_row(record.opportunity_id) is not None:
            raise MediaOpportunityError(f"media_opportunity_already_exists:{record.opportunity_id}")
        record = self._write_intake_artifacts(record)
        row = self.ledgers.append(
            "opportunity_records",
            {
                "record_type": "media_opportunity_record",
                **record.to_dict(),
                **SAFETY_FLAGS,
            },
        )
        self._append_transition(None, "captured", record.opportunity_id, reason_code="opportunity_intake_created")
        return {
            "clean": True,
            "opportunity": _without_ledger_envelope(row),
            "artifact_root": str(self.artifact_root(record.opportunity_id)),
        }

    def ingest_gmail_label(self, *, label: str, source: Any | None = None, limit: int | None = None) -> dict[str, Any]:
        from signal_agent.media_opportunities.gmail import GoogleGmailReadonlySource

        gmail_source = source or GoogleGmailReadonlySource.from_environment()
        created: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        manual_review: list[str] = []
        messages = gmail_source.messages_for_label(label, limit=limit)
        seen_fingerprints: set[str] = set()
        for message in messages:
            try:
                intake = gmail_message_to_intake(message, label=label)
                fingerprint = str(intake["source_fingerprint"])
                if fingerprint in seen_fingerprints:
                    skipped.append(
                        {
                            "source_fingerprint": fingerprint,
                            "reason": "duplicate_in_label_scan",
                            "gmail_source_ref": intake["source_ref"],
                        }
                    )
                    continue
                seen_fingerprints.add(fingerprint)
                existing = self._record_by_source_fingerprint(fingerprint)
                if existing is not None:
                    skipped.append(
                        {
                            "source_fingerprint": fingerprint,
                            "reason": "already_ingested",
                            "opportunity_id": existing["opportunity_id"],
                            "gmail_source_ref": intake["source_ref"],
                        }
                    )
                    manual_review.append(str(existing["opportunity_id"]))
                    self._append_gmail_audit(label=label, status="skipped_existing", intake=intake, opportunity_id=str(existing["opportunity_id"]))
                    continue
                result = self.create_opportunity(
                    opportunity_type=intake["opportunity_type"],
                    original_request_text=intake["original_request_text"],
                    outlet_or_organization=intake.get("outlet_or_organization"),
                    contact_or_source_name=intake.get("contact_or_source_name"),
                    originating_url_or_source_ref=intake.get("source_ref"),
                    topic_or_subject=intake.get("topic_or_subject"),
                    deadline=intake.get("deadline"),
                    relationship_classification=intake["relationship_classification"],
                    visibility="private",
                    next_action="Human review required: qualify this Gmail-labeled opportunity.",
                    notes=intake["notes"],
                    source_metadata=intake["source_metadata"],
                    source_fingerprint=fingerprint,
                )
                opportunity = result["opportunity"]
                created.append(
                    {
                        "opportunity_id": opportunity["opportunity_id"],
                        "source_fingerprint": fingerprint,
                        "gmail_source_ref": intake["source_ref"],
                    }
                )
                manual_review.append(str(opportunity["opportunity_id"]))
                self._append_gmail_audit(
                    label=label,
                    status="created",
                    intake=intake,
                    opportunity_id=str(opportunity["opportunity_id"]),
                )
            except Exception as exc:
                source_ref = _gmail_source_ref(message)
                error = {"gmail_source_ref": source_ref, "error": str(exc)}
                errors.append(error)
                self._append_gmail_audit(
                    label=label,
                    status="error",
                    intake={
                        "source_ref": source_ref,
                        "source_fingerprint": _gmail_source_fingerprint(message),
                        "source_metadata": gmail_public_source_metadata(message, label=label),
                    },
                    opportunity_id=None,
                    error=str(exc),
                )
        return {
            "clean": not errors,
            "label": label,
            "message_count": len(messages),
            "created_count": len(created),
            "skipped_count": len(skipped),
            "manual_review_count": len(sorted(set(manual_review))),
            "error_count": len(errors),
            "created": created,
            "skipped": skipped,
            "manual_review_required": sorted(set(manual_review)),
            "errors": errors,
        }

    def transition_opportunity(
        self,
        opportunity_id: str,
        to_state: str,
        *,
        reason_code: str | None = None,
        next_action: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        record = self.get_opportunity(opportunity_id)
        to_state = validate_state(to_state)
        if not transition_allowed(record.current_state, to_state):
            raise MediaOpportunityError(
                f"media_opportunity_transition_not_allowed:{record.current_state}->{to_state}"
            )
        updated = replace(
            record,
            current_state=to_state,
            next_action=optional(next_action) if next_action is not None else record.next_action,
            notes=optional(notes) if notes is not None else record.notes,
        )
        transition = self._append_transition(record.current_state, to_state, opportunity_id, reason_code=reason_code)
        row = self._append_record_snapshot(updated)
        self._rewrite_record_manifest(updated)
        return {
            "clean": True,
            "opportunity": _without_ledger_envelope(row),
            "transition": _without_ledger_envelope(transition),
        }

    def approve_public_reference(
        self,
        opportunity_id: str,
        *,
        published_url: str,
        title: str,
        outlet: str,
        author: str | None = None,
        published_date: str | None = None,
        coverage_type: str,
        short_description: str,
        substantially_about: bool,
        verification_note: str | None = None,
        evidence: Iterable[str] | None = None,
        approved_by: str | None = None,
        human_approved: bool = False,
        relationship_classification: str | None = None,
        paid_placement: bool = False,
    ) -> dict[str, Any]:
        record = self.get_opportunity(opportunity_id)
        relationship = (
            validate_relationship(relationship_classification)
            if relationship_classification is not None
            else record.relationship_classification
        )
        coverage = {
            "published_url": optional(published_url),
            "title": optional(title),
            "outlet": optional(outlet),
            "author": optional(author),
            "date": optional(published_date),
            "type": optional(coverage_type),
            "short_neutral_description": optional(short_description),
            "substantially_about_brc_or_work": bool(substantially_about),
            "verification_note": optional(verification_note),
            "evidence": list(normalized_text_items(evidence)),
            "human_approved": bool(human_approved),
            "approved_by": optional(approved_by),
            "approved_timestamp": self.clock() if human_approved else None,
            "relationship_classification": relationship,
            "paid_placement": bool(paid_placement),
        }
        approval_issues = public_reference_gate_issues(record, coverage)
        if approval_issues:
            raise MediaOpportunityError(f"media_reference_approval_blocked:{','.join(approval_issues)}")
        transition_path = self._approval_transition_path(record.current_state)
        updated = replace(
            record,
            relationship_classification=relationship,
            current_state="approved_for_public_reference",
            published_url=str(coverage["published_url"]),
            verification_evidence=_coverage_evidence(coverage),
            coverage_metadata={
                "title": coverage["title"],
                "outlet": coverage["outlet"],
                "author": coverage["author"],
                "date": coverage["date"],
                "type": coverage["type"],
                "short_neutral_description": coverage["short_neutral_description"],
                "substantially_about_brc_or_work": coverage["substantially_about_brc_or_work"],
                "verification_note": coverage["verification_note"],
                "approved_by": coverage["approved_by"],
                "approved_timestamp": coverage["approved_timestamp"],
                "verification_status": "independently_verified",
            },
            visibility="public",
            next_action="Sanitized public-reference candidate is ready for later website review.",
        )
        from_state = record.current_state
        transitions = []
        for to_state in transition_path:
            transitions.append(
                _without_ledger_envelope(
                    self._append_transition(
                        from_state,
                        to_state,
                        opportunity_id,
                        reason_code="public_reference_gate_passed",
                    )
                )
            )
            from_state = to_state
        export = self._write_public_reference_export(updated)
        updated = replace(
            updated,
            artifact_links={
                **dict(updated.artifact_links),
                "media_reference_candidate_json": export["json_path"],
                "media_reference_candidate_markdown": export["markdown_path"],
            },
        )
        row = self._append_record_snapshot(updated)
        self._rewrite_record_manifest(updated)
        approval = self.ledgers.append(
            "approval_records",
            {
                "record_type": "media_reference_approval",
                "approval_id": derive_id("map", opportunity_id, coverage["approved_timestamp"], coverage["published_url"]),
                "opportunity_id": opportunity_id,
                "approved_by": coverage["approved_by"],
                "approved_at": coverage["approved_timestamp"],
                "published_url": coverage["published_url"],
                "export_id": export["export_id"],
                "approval_basis": "human_approved_independent_public_reference",
                **SAFETY_FLAGS,
            },
        )
        return {
            "clean": True,
            "opportunity": _without_ledger_envelope(row),
            "transitions": transitions,
            "approval": _without_ledger_envelope(approval),
            "export": export,
        }

    def get_opportunity(self, opportunity_id: str) -> OpportunityRecord:
        row = self._record_row(opportunity_id)
        if row is None:
            raise MediaOpportunityError(f"media_opportunity_missing:{opportunity_id}")
        return OpportunityRecord.from_record(row)

    def opportunities(self) -> tuple[OpportunityRecord, ...]:
        latest: dict[str, OpportunityRecord] = {}
        for row in self.ledgers.read("opportunity_records"):
            if row.get("record_type") == "media_opportunity_record" and row.get("opportunity_id"):
                record = OpportunityRecord.from_record(row)
                latest[record.opportunity_id] = record
        return tuple(latest[opportunity_id] for opportunity_id in sorted(latest))

    def summary(self, opportunity_id: str | None = None) -> dict[str, Any]:
        if opportunity_id:
            record = self.get_opportunity(opportunity_id)
            return {
                "clean": True,
                "opportunity": record.to_dict(),
                "transitions": [
                    _without_ledger_envelope(row)
                    for row in self.ledgers.read("state_transitions")
                    if row.get("opportunity_id") == opportunity_id
                ],
            }
        records = [record.to_dict() for record in self.opportunities()]
        return {
            "clean": True,
            "opportunity_count": len(records),
            "opportunities": records,
        }

    def artifact_root(self, opportunity_id: str) -> Path:
        return self.ledgers.root / "opportunities" / opportunity_id

    def _approval_transition_path(self, from_state: str) -> tuple[str, ...]:
        if from_state == "awaiting_outcome":
            return ("published_candidate", "independently_verified", "approved_for_public_reference")
        if from_state == "published_candidate":
            return ("independently_verified", "approved_for_public_reference")
        if from_state == "independently_verified":
            return ("approved_for_public_reference",)
        raise MediaOpportunityError(f"media_reference_approval_state_required:{from_state}")

    def _append_record_snapshot(self, record: OpportunityRecord) -> dict[str, Any]:
        return self.ledgers.append(
            "opportunity_records",
            {
                "record_type": "media_opportunity_record",
                **record.to_dict(),
                **SAFETY_FLAGS,
            },
        )

    def _append_transition(
        self,
        from_state: str | None,
        to_state: str,
        opportunity_id: str,
        *,
        reason_code: str | None,
    ) -> dict[str, Any]:
        return self.ledgers.append(
            "state_transitions",
            {
                "record_type": "media_opportunity_state_transition",
                "transition_id": derive_id("mot", opportunity_id, from_state or "missing", to_state, self.clock()),
                "opportunity_id": opportunity_id,
                "from_state": from_state,
                "to_state": to_state,
                "reason_code": optional(reason_code),
                **SAFETY_FLAGS,
            },
        )

    def _record_row(self, opportunity_id: str) -> dict[str, Any] | None:
        matched = None
        for row in self.ledgers.read("opportunity_records"):
            if row.get("record_type") == "media_opportunity_record" and row.get("opportunity_id") == opportunity_id:
                matched = row
        return matched

    def _record_by_source_fingerprint(self, source_fingerprint: str) -> dict[str, Any] | None:
        matched = None
        for row in self.ledgers.read("opportunity_records"):
            metadata = row.get("source_metadata") if isinstance(row.get("source_metadata"), dict) else {}
            if metadata.get("source_fingerprint") == source_fingerprint:
                matched = row
        return matched

    def _append_gmail_audit(
        self,
        *,
        label: str,
        status: str,
        intake: dict[str, Any],
        opportunity_id: str | None,
        error: str | None = None,
    ) -> dict[str, Any]:
        source_metadata = dict(intake.get("source_metadata") or {})
        return self.ledgers.append(
            "gmail_intake_audit",
            {
                "record_type": "gmail_media_opportunity_intake_audit",
                "audit_id": derive_id("gma", label, intake.get("source_fingerprint"), status, self.clock()),
                "label": label,
                "status": status,
                "opportunity_id": opportunity_id,
                "gmail_source_ref": intake.get("source_ref"),
                "source_fingerprint": intake.get("source_fingerprint"),
                "subject_hash": source_metadata.get("subject_hash"),
                "sender_hash": source_metadata.get("sender_hash"),
                "message_body_hash": source_metadata.get("message_body_hash"),
                "thread_id_hash": source_metadata.get("thread_id_hash"),
                "message_id_hash": source_metadata.get("message_id_hash"),
                "error": error,
                **SAFETY_FLAGS,
            },
        )

    def _write_intake_artifacts(self, record: OpportunityRecord) -> OpportunityRecord:
        root = self.artifact_root(record.opportunity_id)
        root.mkdir(parents=True, exist_ok=True)
        links = {
            "opportunity_markdown": str((root / "opportunity.md").resolve()),
            "response_draft_markdown": str((root / "response_draft.md").resolve()),
            "facts_and_links_markdown": str((root / "facts_and_links.md").resolve()),
            "evidence_checklist_markdown": str((root / "evidence_checklist.md").resolve()),
            "record_json": str((root / "record.json").resolve()),
        }
        linked = replace(record, artifact_links=links)
        (root / "opportunity.md").write_text(render_opportunity_markdown(linked), encoding="utf-8")
        (root / "response_draft.md").write_text(
            generate_response_draft(linked, self.identity_packet),
            encoding="utf-8",
        )
        (root / "facts_and_links.md").write_text(
            render_facts_and_links(self.identity_packet),
            encoding="utf-8",
        )
        (root / "evidence_checklist.md").write_text(render_evidence_checklist(linked), encoding="utf-8")
        self._rewrite_record_manifest(linked)
        return linked

    def _rewrite_record_manifest(self, record: OpportunityRecord) -> None:
        record_path = Path(record.artifact_links.get("record_json") or self.artifact_root(record.opportunity_id) / "record.json")
        record_path.parent.mkdir(parents=True, exist_ok=True)
        record_path.write_text(_json_text(record.to_dict()), encoding="utf-8")

    def _write_public_reference_export(self, record: OpportunityRecord) -> dict[str, Any]:
        export_root = self.artifact_root(record.opportunity_id)
        export_root.mkdir(parents=True, exist_ok=True)
        payload = sanitized_public_reference(record)
        json_path = export_root / "media_reference_candidate.json"
        md_path = export_root / "media_reference_candidate.md"
        json_text = _json_text(payload)
        md_text = render_public_reference_markdown(payload)
        json_path.write_text(json_text, encoding="utf-8")
        md_path.write_text(md_text, encoding="utf-8")
        export_id = derive_id("mre", record.opportunity_id, payload["public_url"], payload["approved_timestamp"])
        export_row = self.ledgers.append(
            "public_reference_exports",
            {
                "record_type": "media_reference_export",
                "export_id": export_id,
                "opportunity_id": record.opportunity_id,
                "exported_at": self.clock(),
                "json_path": str(json_path.resolve()),
                "markdown_path": str(md_path.resolve()),
                "json_hash": text_hash(json_text),
                "markdown_hash": text_hash(md_text),
                **SAFETY_FLAGS,
            },
        )
        return _without_ledger_envelope(export_row)


def load_identity_packet(path: Path | None = None) -> dict[str, Any]:
    if path is not None and path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
    return dict(DEFAULT_IDENTITY_PACKET)


def public_reference_gate_issues(record: OpportunityRecord, coverage: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    required = {
        "published_url": coverage.get("published_url"),
        "title": coverage.get("title"),
        "outlet": coverage.get("outlet"),
        "type": coverage.get("type"),
        "short_neutral_description": coverage.get("short_neutral_description"),
        "approved_by": coverage.get("approved_by"),
    }
    for key, value in required.items():
        if not str(value or "").strip():
            issues.append(f"{key}_required")
    if not is_public_http_url(coverage.get("published_url")):
        issues.append("published_url_public_http_required")
    if is_owned_public_reference_url(coverage.get("published_url")):
        issues.append("published_url_is_owned_or_self_published")
    if coverage.get("type") not in PUBLIC_REFERENCE_COVERAGE_TYPES:
        issues.append(f"coverage_type_invalid:{coverage.get('type')}")
    if coverage.get("type") in NON_INDEPENDENT_COVERAGE_TYPES:
        issues.append(f"coverage_type_not_independent:{coverage.get('type')}")
    if coverage.get("relationship_classification") != "independent":
        issues.append("independent_relationship_required")
    if record.relationship_classification not in {"independent", "unknown"} and coverage.get("relationship_classification") != "independent":
        issues.append("record_relationship_blocks_independence")
    if coverage.get("paid_placement") is True:
        issues.append("paid_placement_not_independent")
    if coverage.get("substantially_about_brc_or_work") is not True:
        issues.append("substantially_about_required")
    if not coverage.get("verification_note") and not coverage.get("evidence"):
        issues.append("verification_evidence_required")
    if coverage.get("human_approved") is not True:
        issues.append("explicit_human_approval_required")
    return sorted(set(issues))


def sanitized_public_reference(record: OpportunityRecord) -> dict[str, Any]:
    coverage = dict(record.coverage_metadata)
    payload = {
        "title": coverage.get("title"),
        "outlet": coverage.get("outlet"),
        "author": coverage.get("author"),
        "date": coverage.get("date"),
        "type": coverage.get("type"),
        "public_url": record.published_url,
        "short_neutral_description": coverage.get("short_neutral_description"),
        "verification_status": coverage.get("verification_status"),
        "approved_timestamp": coverage.get("approved_timestamp"),
    }
    return {key: payload.get(key) for key in PUBLIC_EXPORT_KEYS}


def gmail_message_to_intake(message: dict[str, Any], *, label: str) -> dict[str, Any]:
    text = _gmail_message_text(message)
    if not text:
        raise MediaOpportunityError("gmail_message_text_required")
    subject = optional(message.get("subject"))
    sender_name = optional(message.get("sender_name") or _sender_display_name(str(message.get("from") or "")))
    source_ref = _gmail_source_ref(message)
    source_fingerprint = _gmail_source_fingerprint(message)
    inferred_type = infer_opportunity_type(" ".join([subject or "", text]))
    return {
        "opportunity_type": inferred_type,
        "original_request_text": _gmail_private_text(message, text),
        "outlet_or_organization": extract_outlet(message, text),
        "contact_or_source_name": sender_name,
        "source_ref": source_ref,
        "topic_or_subject": extract_topic(subject, text),
        "deadline": extract_deadline(text),
        "relationship_classification": infer_relationship(text),
        "notes": (
            f"Created from Gmail label '{label}'. Human qualification required before any response, "
            "state transition, or public-reference review."
        ),
        "source_fingerprint": source_fingerprint,
        "source_metadata": gmail_public_source_metadata(message, label=label, source_fingerprint=source_fingerprint, text=text),
    }


def infer_opportunity_type(text: str) -> str:
    lowered = text.lower()
    patterns = (
        ("podcast_or_interview", ("podcast", "interview", "guest on", "recording", "episode", "show")),
        ("guest_essay", ("guest essay", "op-ed", "op ed", "write an essay", "contributed essay", "submission")),
        ("review", ("review copy", "book review", "review your", "review of", "would like to review")),
        ("local_reporting", ("local reporter", "local news", "news story", "reporting on", "newspaper")),
        ("organizational_feature", ("feature you", "member feature", "organization profile", "spotlight")),
        ("academic_or_writer_citation", ("cite", "citation", "quote your", "reference your work", "bibliography")),
        ("speaking_invitation", ("speak at", "speaking invitation", "keynote", "panel", "workshop", "sermon", "teach at")),
    )
    for opportunity_type, terms in patterns:
        if any(term in lowered for term in terms):
            return opportunity_type
    return "other"


def infer_relationship(text: str) -> str:
    lowered = text.lower()
    if any(term in lowered for term in ("our client", "sponsored", "paid placement", "affiliate", "partner campaign")):
        return "affiliated"
    if any(term in lowered for term in ("your own site", "your post", "repost", "self-published", "announcement from you")):
        return "self"
    if any(term in lowered for term in ("independent review", "editorially independent", "independent reporting")):
        return "independent"
    return "unknown"


def extract_outlet(message: dict[str, Any], text: str) -> str | None:
    for key in ("outlet", "organization"):
        value = optional(message.get(key))
        if value:
            return value
    match = re.search(r"\b(?:outlet|organization|publication|podcast)\s*:\s*(.+)", text, flags=re.IGNORECASE)
    if match:
        return _clean_metadata_line(match.group(1))
    return None


def extract_topic(subject: str | None, text: str) -> str | None:
    match = re.search(r"\b(?:topic|subject)\s*:\s*(.+)", text, flags=re.IGNORECASE)
    if match:
        return _clean_metadata_line(match.group(1))
    if subject:
        cleaned = re.sub(r"^(re|fwd?):\s*", "", subject, flags=re.IGNORECASE).strip()
        return cleaned or None
    return None


def extract_deadline(text: str) -> str | None:
    match = re.search(r"\b(?:deadline|due(?:\s+by)?|needed by)\s*:\s*(.+)", text, flags=re.IGNORECASE)
    if match:
        return _clean_metadata_line(match.group(1))
    iso = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", text)
    if iso:
        return iso.group(1)
    return None


def gmail_public_source_metadata(
    message: dict[str, Any],
    *,
    label: str,
    source_fingerprint: str | None = None,
    text: str | None = None,
) -> dict[str, Any]:
    body = text if text is not None else _gmail_message_text(message)
    thread_id = optional(message.get("thread_id") or message.get("threadId"))
    message_id = optional(message.get("message_id") or message.get("id"))
    subject = optional(message.get("subject"))
    sender = optional(message.get("from") or message.get("sender"))
    return {
        "source_kind": "gmail",
        "gmail_label": label,
        "source_fingerprint": source_fingerprint or _gmail_source_fingerprint(message),
        "gmail_source_ref": _gmail_source_ref(message),
        "thread_id_hash": text_hash(thread_id or ""),
        "message_id_hash": text_hash(message_id or ""),
        "subject_hash": text_hash(subject or ""),
        "sender_hash": text_hash(sender or ""),
        "message_body_hash": text_hash(body),
        "raw_gmail_ids_private": True,
        "source_email_mutated": False,
    }


def generate_response_draft(record: OpportunityRecord, identity_packet: dict[str, Any] | None = None) -> str:
    identity = identity_packet or DEFAULT_IDENTITY_PACKET
    topic = record.topic_or_subject or "the requested subject"
    outlet = record.outlet_or_organization or "your outlet"
    links = identity.get("public_work_links") or {}
    bio = identity.get("concise_grounded_bio") or DEFAULT_IDENTITY_PACKET["concise_grounded_bio"]
    lines = [
        "# Response Draft",
        "",
        "DRAFT - DO NOT SEND AUTOMATICALLY.",
        "",
        f"Opportunity ID: {record.opportunity_id}",
        f"Opportunity type: {record.opportunity_type}",
        f"Outlet or organization: {outlet}",
        "",
    ]
    if record.opportunity_type == "podcast_or_interview":
        lines.extend(
            [
                "## Draft Reply",
                "",
                f"Thank you for reaching out about {topic}. I am open to discussing whether this is a good fit.",
                "Could you share the format, expected length, audience, recording or publication timeline, and any questions you already know you want to cover?",
                "",
                "## Topic Angles",
                "",
                "- The public work already gathered at BrendonRColeman.com.",
                "- Letters of Light, Scripture-rooted reflection, and remaining present under pressure.",
                "- Practical systems work, deterministic publishing, and operational clarity.",
                "",
                "## Availability Questions",
                "",
                "- What date and time window are you considering?",
                "- Is this live, recorded, written, or edited?",
                "- Will Brendon receive the final public link after publication?",
            ]
        )
    elif record.opportunity_type == "guest_essay":
        lines.extend(
            [
                "## Proposed Thesis",
                "",
                f"A concise essay on {topic} grounded in already public work, without adding unsupported claims.",
                "",
                "## Short Abstract",
                "",
                "The piece can connect public writing, grounded identity material, and practical systems thinking while keeping claims verifiable.",
                "",
                "## Submission Questions",
                "",
                "- What word count, deadline, rights, and editorial process apply?",
                "- Will edits be shared before publication?",
                "- What public author bio and links should be used?",
            ]
        )
    elif record.opportunity_type == "review":
        lines.extend(
            [
                "## Review Boundary",
                "",
                "Thank you for considering a review. Please identify the specific work, edition or version, publication timeline, and disclosure expectations.",
                "",
                "## Checklist",
                "",
                "- Confirm exact work title and public URL.",
                "- Confirm whether the reviewer is independent.",
                "- Preserve any disclosure, comp, or relationship details privately.",
            ]
        )
    elif record.opportunity_type == "local_reporting":
        lines.extend(
            [
                "## Background Packet",
                "",
                "Thank you for reaching out. I can provide factual public background and links for review.",
                "",
                "## Quote Boundary",
                "",
                "Please share the intended topic, deadline, and whether any direct quotes will be checked for accuracy before publication.",
            ]
        )
    elif record.opportunity_type == "academic_or_writer_citation":
        lines.extend(
            [
                "## Citation Reply",
                "",
                "Thank you for the citation inquiry. Please cite the public URL, title, version or access date, and the specific work being referenced.",
                "",
                "## Attribution Request",
                "",
                "Use Brendon R. Coleman and the canonical public link unless a publication style guide requires another format.",
            ]
        )
    elif record.opportunity_type == "speaking_invitation":
        lines.extend(
            [
                "## Speaking Reply",
                "",
                f"Thank you for the invitation to speak on {topic}. I am open to reviewing the gathering, audience, date, format, and expectations.",
                "",
                "## Planning Questions",
                "",
                "- What audience and room size are expected?",
                "- What message length or teaching format do you want?",
                "- Are travel, recording, honorarium, or publication terms involved?",
            ]
        )
    else:
        lines.extend(
            [
                "## Draft Reply",
                "",
                f"Thank you for reaching out about {topic}. I am open to reviewing the details and deciding whether this is a fit.",
                "",
                "## Clarifying Questions",
                "",
                "- What format, audience, deadline, and publication path are expected?",
                "- What public links or bio material do you need?",
            ]
        )
    lines.extend(
        [
            "",
            "## Canonical Bio",
            "",
            bio,
            "",
            "## Public Links",
            "",
        ]
    )
    for label, url in sorted(links.items()):
        lines.append(f"- {label}: {url}")
    lines.extend(
        [
            "",
            "## Claim Boundary",
            "",
            "Do not add awards, client claims, follower counts, credentials, endorsements, media claims, or notable language unless independently evidenced later.",
        ]
    )
    return "\n".join(lines) + "\n"


def render_opportunity_markdown(record: OpportunityRecord) -> str:
    lines = [
            "# Media Opportunity",
            "",
            f"Opportunity ID: {record.opportunity_id}",
            f"Created: {record.created_at}",
            f"State: {record.current_state}",
            f"Type: {record.opportunity_type}",
            f"Outlet or organization: {record.outlet_or_organization or ''}",
            f"Contact or source: {record.contact_or_source_name or ''}",
            f"Originating URL or source: {record.originating_url_or_source_ref or ''}",
            f"Topic or subject: {record.topic_or_subject or ''}",
            f"Deadline: {record.deadline or ''}",
            f"Relationship: {record.relationship_classification}",
            f"Visibility: {record.visibility}",
            f"Next action: {record.next_action or ''}",
            "",
            "## Original Invitation Or Request",
            "",
            record.original_request_text,
            "",
            "## Private Notes",
            "",
            record.notes or "",
            "",
            "Private record. Do not publish this file.",
            "",
        ]
    if record.source_metadata.get("source_kind") == "gmail":
        lines.insert(2, "Source: Gmail label intake. Human qualification still required.")
        lines.insert(3, "")
    return "\n".join(lines)


def render_facts_and_links(identity_packet: dict[str, Any]) -> str:
    lines = [
        "# Facts And Links",
        "",
        "Private working packet. Public-safe facts only; verify before quoting.",
        "",
        f"Canonical site: {identity_packet.get('canonical_site')}",
        f"About page: {identity_packet.get('about_page')}",
        f"GitHub: {identity_packet.get('github_profile')}",
        f"Portrait reference: {identity_packet.get('portrait_asset_reference')}",
        "",
        "## Public Work Links",
        "",
    ]
    for label, url in sorted((identity_packet.get("public_work_links") or {}).items()):
        lines.append(f"- {label}: {url}")
    lines.extend(
        [
            "",
            "## Grounded Bio",
            "",
            str(identity_packet.get("concise_grounded_bio") or ""),
            "",
            "## Prohibited Claims",
            "",
        ]
    )
    for claim in identity_packet.get("prohibited_claims") or ():
        lines.append(f"- {claim}")
    return "\n".join(lines) + "\n"


def render_evidence_checklist(record: OpportunityRecord) -> str:
    return "\n".join(
        [
            "# Evidence Checklist",
            "",
            "Use this before any public-reference approval.",
            "",
            "- Publicly reachable published URL captured.",
            "- Outlet, author if public, and publication date if available captured.",
            "- Coverage type recorded.",
            "- Short neutral factual description written.",
            "- Relationship classification is independent.",
            "- Coverage is substantially about Brendon R. Coleman or a clearly identified work.",
            "- Verification note or evidence captured.",
            "- Human approval recorded.",
            "- Not Brendon's own website, profile, repost, paid placement, generic directory, or unverified screenshot.",
            "",
            f"Current opportunity state: {record.current_state}",
            "",
        ]
    )


def render_public_reference_markdown(payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Media Reference Candidate",
            "",
            f"Title: {payload.get('title') or ''}",
            f"Outlet: {payload.get('outlet') or ''}",
            f"Author: {payload.get('author') or ''}",
            f"Date: {payload.get('date') or ''}",
            f"Type: {payload.get('type') or ''}",
            f"Public URL: {payload.get('public_url') or ''}",
            f"Description: {payload.get('short_neutral_description') or ''}",
            f"Verification status: {payload.get('verification_status') or ''}",
            f"Approved timestamp: {payload.get('approved_timestamp') or ''}",
            "",
        ]
    )


def _coverage_evidence(coverage: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    evidence = [
        {"kind": "public_url", "value": coverage["published_url"]},
    ]
    if coverage.get("verification_note"):
        evidence.append({"kind": "verification_note", "value": coverage["verification_note"]})
    for item in coverage.get("evidence") or ():
        evidence.append({"kind": "operator_evidence", "value": item})
    return tuple(evidence)


def _default_identity_packet_path() -> Path:
    return repo_root() / "config" / "media_opportunities" / "canonical_identity_packet.json"


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


def _without_ledger_envelope(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in row.items()
        if key not in {"record_hash", "prev_hash", "sequence", "recorded_at"}
    }


def _gmail_message_text(message: dict[str, Any]) -> str:
    candidates = (
        message.get("text"),
        message.get("body_text"),
        message.get("snippet"),
        message.get("body"),
    )
    for value in candidates:
        text = normalize_text(value)
        if text:
            return text
    return ""


def _gmail_private_text(message: dict[str, Any], text: str) -> str:
    parts = [
        "Gmail-derived private intake.",
        f"Subject: {optional(message.get('subject')) or ''}",
        f"From: {optional(message.get('from') or message.get('sender')) or ''}",
        "",
        text,
    ]
    return "\n".join(parts).strip()


def _gmail_source_ref(message: dict[str, Any]) -> str:
    thread_id = optional(message.get("thread_id") or message.get("threadId"))
    message_id = optional(message.get("message_id") or message.get("id"))
    if thread_id:
        return f"gmail:thread:{thread_id}"
    if message_id:
        return f"gmail:message:{message_id}"
    return f"gmail:message-hash:{text_hash(_gmail_message_text(message))}"


def _gmail_source_fingerprint(message: dict[str, Any]) -> str:
    thread_id = optional(message.get("thread_id") or message.get("threadId"))
    message_id = optional(message.get("message_id") or message.get("id"))
    stable_ref = thread_id or message_id
    if stable_ref:
        return text_hash(f"gmail:{stable_ref}")
    return text_hash(_gmail_message_text(message))


def _sender_display_name(value: str) -> str | None:
    display = value.split("<", 1)[0].strip().strip('"')
    return display or None


def _clean_metadata_line(value: str) -> str | None:
    line = value.strip().splitlines()[0].strip()
    return optional(re.split(r"\s{2,}|\s+[|]\s+", line)[0])
