from __future__ import annotations

from dataclasses import dataclass
import re

from .registry import OperatorRegistry, normalize_text


@dataclass(frozen=True)
class ParsedIntent:
    command_text: str
    intent_id: str
    confidence: float
    matched_phrase: str | None = None
    requested_workflow: str | None = None
    requested_action: str | None = None
    requested_run_id: str | None = None
    requested_target: str | None = None
    requested_target_kind: str | None = None
    notes: tuple[str, ...] = ()


class IntentParser:
    _SHOW_ACTION_MARKERS = (
        "what files matter for ",
        "what ledgers matter for ",
        "what manifests matter for ",
        "show files for ",
        "show ledgers for ",
        "show manifests for ",
        "show what files matter for ",
        "show what ledgers matter for ",
        "show what manifests matter for ",
        "what matters for ",
    )
    _RUN_PREFIXES = (
        "run workflow ",
        "execute workflow ",
        "start workflow ",
        "run ",
        "execute ",
        "start ",
    )

    def __init__(self, registry: OperatorRegistry) -> None:
        self.registry = registry

    def parse(self, command_text: str) -> ParsedIntent:
        normalized = normalize_text(command_text)
        if not normalized:
            return ParsedIntent(
                command_text=command_text,
                intent_id="unknown",
                confidence=0.0,
                notes=("The operator command was empty.",),
            )

        intake_append_target = self._extract_intake_append_request(normalized, command_text)
        if intake_append_target:
            return ParsedIntent(
                command_text=command_text,
                intent_id="append_intake_record",
                confidence=1.0,
                requested_workflow="intake_log_append",
                requested_target=intake_append_target,
            )

        compound_append_target = self._extract_compound_intake_session_request(normalized, command_text)
        if compound_append_target:
            return ParsedIntent(
                command_text=command_text,
                intent_id="execute_compound_intake_and_session",
                confidence=1.0,
                requested_workflow="intake_append_and_stage_session",
                requested_target=compound_append_target,
            )

        if "continue" in normalized or "resume" in normalized:
            return ParsedIntent(
                command_text=command_text,
                intent_id="continue_prior_task",
                confidence=0.96,
                requested_run_id=self._extract_run_id(normalized),
            )

        if any(marker in normalized for marker in self._SHOW_ACTION_MARKERS) or (
            any(token in normalized for token in ("files", "ledgers", "manifests"))
            and "matter" in normalized
        ):
            requested_action = self._extract_requested_action(normalized)
            target_workflow = self.registry.find_workflow_mention(requested_action or normalized)
            return ParsedIntent(
                command_text=command_text,
                intent_id="show_action_surfaces",
                confidence=0.93,
                requested_action=requested_action or normalized,
                requested_workflow=target_workflow.workflow_id if target_workflow else None,
            )

        explicit_workflow = self._extract_explicit_workflow(normalized)
        if explicit_workflow is not None:
            return ParsedIntent(
                command_text=command_text,
                intent_id="run_named_workflow",
                confidence=0.97,
                requested_workflow=explicit_workflow,
            )

        if "list" in normalized and "workflow" in normalized:
            return ParsedIntent(
                command_text=command_text,
                intent_id="list_known_workflows",
                confidence=0.98,
                matched_phrase="list workflows",
            )

        if any(phrase in normalized for phrase in ("repo structure", "repository structure", "operator structure", "explain repo")):
            return ParsedIntent(
                command_text=command_text,
                intent_id="explain_repo_structure",
                confidence=0.95,
                matched_phrase="repo structure",
            )

        drilldown_request = self._extract_lineage_drilldown_request(normalized)
        if drilldown_request is not None:
            return ParsedIntent(
                command_text=command_text,
                intent_id="inspect_routing_lineage_drilldown",
                confidence=0.96,
                matched_phrase="routing_lineage_drilldown",
                requested_workflow="routing_lineage_drilldown",
                requested_target=drilldown_request[0],
                requested_target_kind=drilldown_request[1],
            )

        backlog_request = self._extract_backlog_request(normalized)
        if backlog_request is not None:
            return ParsedIntent(
                command_text=command_text,
                intent_id="inspect_routing_queue_backlog",
                confidence=0.95,
                matched_phrase="routing_queue_backlog",
                requested_workflow="routing_queue_backlog",
                requested_target=backlog_request[0],
                requested_target_kind=backlog_request[1],
            )

        mentioned_workflow = self.registry.find_workflow_mention(normalized)
        if mentioned_workflow is not None and mentioned_workflow.workflow_id == "capture_routing_status":
            return ParsedIntent(
                command_text=command_text,
                intent_id="inspect_capture_routing_status",
                confidence=0.94,
                matched_phrase=mentioned_workflow.workflow_id,
                requested_workflow=mentioned_workflow.workflow_id,
            )
        if mentioned_workflow is not None and mentioned_workflow.workflow_id == "routing_queue_backlog":
            return ParsedIntent(
                command_text=command_text,
                intent_id="inspect_routing_queue_backlog",
                confidence=0.94,
                matched_phrase=mentioned_workflow.workflow_id,
                requested_workflow=mentioned_workflow.workflow_id,
                requested_target=self._extract_freeform_target(normalized),
            )
        if mentioned_workflow is not None and mentioned_workflow.workflow_id == "routing_lineage_drilldown":
            bundle_target = self._extract_bundle_filename(normalized)
            return ParsedIntent(
                command_text=command_text,
                intent_id="inspect_routing_lineage_drilldown",
                confidence=0.94,
                matched_phrase=mentioned_workflow.workflow_id,
                requested_workflow=mentioned_workflow.workflow_id,
                requested_target=bundle_target or self._extract_freeform_target(normalized),
                requested_target_kind="bundle" if bundle_target else None,
            )

        if normalized in {"status", "show status", "system status"} or any(
            phrase in normalized for phrase in ("inspect system state", "system state", "inspect current state", "operator state")
        ):
            return ParsedIntent(
                command_text=command_text,
                intent_id="inspect_system_state",
                confidence=0.92,
                matched_phrase="system state",
            )

        telemetry_workflow = self._extract_telemetry_workflow(normalized)
        if telemetry_workflow is not None:
            return ParsedIntent(
                command_text=command_text,
                intent_id="evaluate_telemetry_placeholder",
                confidence=0.9,
                requested_workflow=telemetry_workflow,
            )

        best_match = self._fallback_match(normalized, command_text)
        if best_match is not None:
            return best_match

        return ParsedIntent(
            command_text=command_text,
            intent_id="unknown",
            confidence=0.0,
            notes=("The request did not match a supported operator intent.",),
        )

    def _extract_run_id(self, normalized: str) -> str | None:
        match = re.search(r"(operator_[0-9a-f]{16})", normalized)
        return match.group(1) if match else None

    def _extract_requested_action(self, normalized: str) -> str | None:
        for marker in self._SHOW_ACTION_MARKERS:
            if marker in normalized:
                return normalized.split(marker, 1)[1].strip(" ?.!").strip()
        return None

    def _extract_explicit_workflow(self, normalized: str) -> str | None:
        for prefix in self._RUN_PREFIXES:
            if normalized.startswith(prefix):
                candidate = normalized[len(prefix):].strip(" ?.!").removeprefix("the ").strip()
                workflow = self.registry.resolve_workflow_name(candidate)
                if workflow is not None:
                    return workflow.workflow_id
        return None

    def _extract_telemetry_workflow(self, normalized: str) -> str | None:
        mentioned = self.registry.find_workflow_mention(normalized)
        if mentioned is not None and mentioned.is_placeholder:
            return mentioned.workflow_id
        if any(term in normalized for term in ("telemetry", "observability", "promotion decision", "oil")):
            return "telemetry_evaluation"
        return None

    def _extract_backlog_request(self, normalized: str) -> tuple[str | None, str | None] | None:
        backlog_markers = (
            "queue backlog",
            "routing queue",
            "queue status",
            "queued bundles",
            "backlog",
        )
        if not any(marker in normalized for marker in backlog_markers):
            return None

        patterns: tuple[tuple[str, str | None], ...] = (
            (r"(?:show|inspect|explain)?\s*(?:the\s+)?backlog for (?P<target>.+)$", None),
            (r"(?:show|inspect|explain)?\s*(?:the\s+)?queue backlog for (?P<target>.+)$", None),
            (r"(?:show|inspect|explain)?\s*(?:the\s+)?routing queue for (?P<target>.+)$", None),
            (r"(?:show|inspect|explain)?\s*(?:the\s+)?queue for (?P<target>.+)$", None),
            (r"(?:show|inspect|explain)?\s*(?:the\s+)?lane (?P<target>[a-z0-9_ -]+) backlog$", "lane"),
        )
        for pattern, target_kind in patterns:
            match = re.search(pattern, normalized)
            if match:
                target = match.group("target").strip(" ?.!").strip()
                return (target or None, target_kind)

        return (None, None)

    def _extract_lineage_drilldown_request(self, normalized: str) -> tuple[str, str] | None:
        bundle_target = self._extract_bundle_filename(normalized)
        if bundle_target and any(
            phrase in normalized
            for phrase in (
                "inspect bundle",
                "queued bundle",
                "show lineage",
                "lineage for",
                "downstream evidence",
                "still waiting",
                "queue status for",
                "why is",
            )
        ):
            return (bundle_target, "bundle")

        bundle_patterns = (
            r"(?:inspect|show|explain)\s+bundle\s+(?P<target>bundle_[a-z0-9_]+\.md)$",
            r"(?:show|inspect|explain)\s+lineage\s+for\s+(?:queued\s+bundle\s+)?(?P<target>bundle_[a-z0-9_]+\.md)$",
            r"(?:show|inspect|explain)\s+downstream evidence for\s+(?P<target>bundle_[a-z0-9_]+\.md)$",
            r"(?:show|inspect|explain)\s+queue status for\s+(?P<target>bundle_[a-z0-9_]+\.md)$",
            r"why is\s+(?P<target>bundle_[a-z0-9_]+\.md)\s+still waiting$",
        )
        for pattern in bundle_patterns:
            match = re.search(pattern, normalized)
            if match:
                return (match.group("target").strip(), "bundle")

        destination_patterns = (
            r"(?:inspect|show|explain)\s+destination\s+(?P<target>[a-z0-9_ -]+)$",
            r"(?:inspect|show|explain)\s+destination status for\s+(?P<target>[a-z0-9_ -]+)$",
            r"drill down on\s+(?P<target>[a-z0-9_ -]+)$",
        )
        for pattern in destination_patterns:
            match = re.search(pattern, normalized)
            if match:
                return (match.group("target").strip(" ?.!").strip(), None)
        return None

    def _extract_bundle_filename(self, normalized: str) -> str | None:
        match = re.search(r"(bundle_[a-z0-9_]+\.md)", normalized)
        return match.group(1) if match else None

    def _extract_freeform_target(self, normalized: str) -> str | None:
        for marker in ("for ", "destination ", "lane "):
            if marker in normalized:
                candidate = normalized.split(marker, 1)[1].strip(" ?.!").strip()
                if candidate:
                    return candidate
        return None

    def _extract_intake_append_request(self, normalized: str, original: str) -> str | None:
        """Extract the artifact target from a strict intake append command.

        Accepted form (only):
            append intake record <artifact_id>

        The command prefix is matched against the normalized (lowered) input.
        The payload (<artifact_id>) is extracted from the ORIGINAL input to
        preserve casing.  If no payload token exists after the prefix, the
        method returns None (fail-closed).
        """
        # Single anchored pattern — no short-form, no greedy structural capture.
        match = re.match(
            r"^append\s+intake\s+record\s+(?P<target>\S+)\s*$",
            normalized,
        )
        if match is None:
            return None

        # Extract the payload from the ORIGINAL input by locating the same
        # positional token.  The prefix is always "append intake record "
        # (possibly with varied whitespace/casing), so we find the last
        # whitespace-delimited token in the stripped original.
        original_match = re.match(
            r"^append\s+intake\s+record\s+(?P<target>\S+)\s*$",
            original.strip(),
            re.IGNORECASE,
        )
        if original_match is None:
            # Defensive: if the original doesn't match the same structure,
            # fall back to the normalized value (should not happen).
            return match.group("target")

        return original_match.group("target")

    def _extract_compound_intake_session_request(self, normalized: str, original: str) -> str | None:
        """Extract the artifact target from a strict compound intake append and stage session command.

        Accepted form (only):
            append intake and stage session <target>
        """
        match = re.match(
            r"^append\s+intake\s+and\s+stage\s+session\s+(?P<target>\S+)\s*$",
            normalized,
        )
        if match is None:
            return None

        original_match = re.match(
            r"^append\s+intake\s+and\s+stage\s+session\s+(?P<target>\S+)\s*$",
            original.strip(),
            re.IGNORECASE,
        )
        if original_match is None:
            return match.group("target")

        return original_match.group("target")

    def _fallback_match(self, normalized: str, command_text: str) -> ParsedIntent | None:
        best_intent_id: str | None = None
        best_phrase: str | None = None
        best_score = 0
        for intent in self.registry.intents.values():
            for phrase in intent.match_phrases:
                normalized_phrase = normalize_text(phrase)
                if normalized_phrase and normalized_phrase in normalized and len(normalized_phrase) > best_score:
                    best_intent_id = intent.intent_id
                    best_phrase = phrase
                    best_score = len(normalized_phrase)
        if best_intent_id is None:
            return None
        return ParsedIntent(
            command_text=command_text,
            intent_id=best_intent_id,
            confidence=0.75,
            matched_phrase=best_phrase,
        )
