from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import yaml

from .capture_routing_status import build_capture_routing_status_tool_result
from .planner import OperatorPlan
from .registry import OperatorRegistry
from .routing_queue_backlog import build_routing_queue_backlog_tool_result
from .routing_lineage_drilldown import build_routing_lineage_drilldown_tool_result

# Governance gate — canonical lifecycle boundary.
# Imported at module level so write-mode enforcement fails loudly on import
# if the gate module is ever moved or broken.
from app.hq.governance.transition_gate import (
    validate_transition as _gate_validate_transition,
    emit_transition_event as _gate_emit_transition_event,
)
from app.utils.io_contract import append_jsonl_atomic

# Context assembly — governed memory-to-execution bridge (Phase 3A).
# Fail-safe: if import fails, context assembly degrades to empty bundles.
try:
    from signal_agent.memory.context_assembly import ContextAssembler
    from signal_agent.memory.types import ContextBundle, EMPTY_CONTEXT
    _CONTEXT_ASSEMBLY_AVAILABLE = True
except ImportError:
    _CONTEXT_ASSEMBLY_AVAILABLE = False


@dataclass(frozen=True)
class ToolExecution:
    tool_id: str
    status: str
    summary: str
    highlights: tuple[str, ...]
    authority_paths: tuple[str, ...]
    notes: tuple[str, ...]
    details: dict[str, Any]


@dataclass(frozen=True)
class OperatorRunResult:
    run_id: str
    command_text: str
    status: str
    started_at: str
    completed_at: str
    intent_id: str
    workflow_id: str | None
    target_workflow_id: str | None
    summary: str
    highlights: tuple[str, ...]
    authority_paths: tuple[str, ...]
    notes: tuple[str, ...]
    tool_results: tuple[ToolExecution, ...]
    ledger_path: str
    run_record_path: str
    continued_from: str | None = None


def _stable_json(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, default=str)


def _make_run_id(command_text: str, started_at: str) -> str:
    seed = f"{started_at}|{command_text.strip().lower()}"
    return f"operator_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:16]}"


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(text, encoding="utf-8")
    os.replace(str(tmp_path), str(path))


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    append_jsonl_atomic(path, payload)


class OperatorRuntime:
    def __init__(
        self,
        registry: OperatorRegistry,
        *,
        runs_dir: Path | None = None,
        state_dir: Path | None = None,
        canonical_ledger_path: Path | None = None,
    ) -> None:
        self.registry = registry
        self.repo_root = registry.repo_root
        self.runs_dir = (runs_dir or self.repo_root / "data" / "operator" / "runs").resolve()
        self.state_dir = (state_dir or self.repo_root / "data" / "operator" / "state").resolve()
        self.ledger_path = self.runs_dir / "operator_runs.jsonl"
        self.session_state_path = self.state_dir / "session_state.json"
        self.canonical_ledger_path = Path(canonical_ledger_path) if canonical_ledger_path is not None else None

    # ------------------------------------------------------------------
    # Governance helpers — write-mode enforcement
    # ------------------------------------------------------------------

    @staticmethod
    def _is_write_mode(plan: OperatorPlan) -> bool:
        """Return True only if the resolved workflow is explicitly write-mode."""
        return plan.workflow is not None and plan.workflow.mode == "write"

    # ------------------------------------------------------------------
    # Context assembly — governed memory injection (Phase 3A)
    # ------------------------------------------------------------------

    def _assemble_execution_context(
        self,
        plan: OperatorPlan,
        run_id: str,
    ) -> Any:
        """Assemble a policy-filtered ContextBundle for tool handler consumption.

        Runs AFTER gate validation, BEFORE handler invocation.
        Fail-closed: returns EMPTY_CONTEXT on any error.

        This is an input-preparation step only. It does NOT:
          - mutate state
          - validate transitions
          - decide dispatch eligibility
          - rewrite the plan
        """
        if not _CONTEXT_ASSEMBLY_AVAILABLE:
            return None

        try:
            policy_path = self.repo_root / "config" / "policies" / "context_assembly_policy.yaml"
            assembler = ContextAssembler(self.repo_root, policy_path)

            # Derive workflow mode from the plan.
            workflow_mode = "write" if self._is_write_mode(plan) else "read_only"
            if plan.workflow and plan.workflow.mode == "placeholder":
                workflow_mode = "placeholder"

            # Derive target artifact from the plan intent.
            artifact_id = getattr(plan.intent, "requested_target", None)

            # Derive tool_id from the first step.
            tool_id = plan.steps[0].tool_id if plan.steps else "unknown"

            return assembler.assemble(
                tool_id=tool_id,
                workflow_mode=workflow_mode,
                artifact_id=artifact_id,
                run_id=run_id,
            )
        except Exception:
            # Fail closed — assembly failure must NEVER block execution.
            return EMPTY_CONTEXT if _CONTEXT_ASSEMBLY_AVAILABLE else None

    def _validate_write_transition(
        self,
        plan: OperatorPlan,
        run_id: str,
    ) -> dict[str, Any]:
        """
        Call the canonical transition gate for write-mode workflows.

        Resolves current_state, next_state, lane_id from:
          1. The intent (if it carries explicit transition fields)
          2. The workflow's transition_context (if defined in workflows.yaml)
        Merges additional context and forwards to
        transition_gate.validate_transition().
        """
        # Workflow-level transition defaults.
        wf_tc = (plan.workflow.transition_context or {}) if plan.workflow else {}

        context: dict[str, Any] = {
            "operator_run_id": run_id,
            "workflow_id": plan.workflow.workflow_id if plan.workflow else None,
            "intent_id": plan.intent.intent_id,
            "module": "signal_agent.operator.runtime",
            "operation": "write_mode_dispatch",
        }
        # Propagate source_path from intent target for intake_policy checks.
        if plan.intent.requested_target:
            context["source_path"] = plan.intent.requested_target

        # Intent fields take priority; workflow transition_context is fallback.
        current_state = (
            getattr(plan.intent, "requested_current_state", None)
            or wf_tc.get("current_state")
        )
        next_state = (
            getattr(plan.intent, "requested_next_state", None)
            or wf_tc.get("next_state")
            or ""
        )
        lane_id = (
            getattr(plan.intent, "requested_lane_id", None)
            or wf_tc.get("lane_id")
        )

        canonical_gate_result = _gate_validate_transition(
            current_state=current_state,
            next_state=next_state,
            lane_id=lane_id,
            context=context,
        )

        # ── READ-BEFORE-WRITE DUPLICATE GATE ──
        if canonical_gate_result.get("allowed") and plan.workflow and plan.workflow.workflow_id == "intake_log_append":
            target = getattr(plan.intent, "requested_target", None)
            if target:
                intake_path = self.repo_root / "data" / "intake" / "intake.jsonl"
                is_duplicate = False
                if intake_path.exists():
                    try:
                        for line in intake_path.read_text(encoding="utf-8").strip().splitlines():
                            if not line.strip():
                                continue
                            record = json.loads(line)
                            if record.get("source_path") == target:
                                is_duplicate = True
                                break
                    except Exception:
                        pass

                if is_duplicate:
                    return {
                        "allowed": False,
                        "reason": "duplicate_record_detected",
                        "context": context,
                    }

        return canonical_gate_result

    # ------------------------------------------------------------------
    # Main execution loop
    # ------------------------------------------------------------------

    def _check_plan_contract(self, plan: OperatorPlan) -> dict[str, Any] | None:
        """
        Validate that a ready plan remains bound to registry-declared intent,
        workflow, and step surfaces even when the caller constructs the
        OperatorPlan directly.

        This keeps direct `OperatorRuntime.execute(plan)` entrypoints aligned
        with the same declarative registry the parser/planner use, without
        requiring the runtime to become parser-exclusive.
        """
        if plan.status != "ready":
            return None

        workflow = plan.workflow
        if workflow is None:
            return {
                "status": "contract_violation",
                "summary": "Ready plans must include a resolved workflow before execution.",
                "highlights": ("REJECTED: ready plan missing workflow",),
                "authority_paths": ("config/operator/intents.yaml", "config/operator/workflows.yaml"),
                "notes": ("Runtime plan contract: ready plans must stay registry-bound.",),
                "details": {
                    "violation": "missing_workflow",
                    "intent_id": plan.intent.intent_id,
                },
            }

        canonical_workflow = self.registry.workflows.get(workflow.workflow_id)
        if canonical_workflow is None:
            return {
                "status": "contract_violation",
                "summary": (
                    f"Workflow '{workflow.workflow_id}' is not present in the operator registry and cannot be executed."
                ),
                "highlights": (f"REJECTED: unknown workflow={workflow.workflow_id}",),
                "authority_paths": ("config/operator/workflows.yaml",),
                "notes": ("Runtime plan contract: workflows must resolve through the operator registry.",),
                "details": {
                    "violation": "unknown_workflow",
                    "workflow_id": workflow.workflow_id,
                    "intent_id": plan.intent.intent_id,
                },
            }

        if plan.target_workflow is not None and plan.target_workflow.workflow_id not in self.registry.workflows:
            return {
                "status": "contract_violation",
                "summary": (
                    f"Target workflow '{plan.target_workflow.workflow_id}' is not present in the operator registry."
                ),
                "highlights": (f"REJECTED: unknown target_workflow={plan.target_workflow.workflow_id}",),
                "authority_paths": ("config/operator/workflows.yaml",),
                "notes": ("Runtime plan contract: target workflows must resolve through the operator registry.",),
                "details": {
                    "violation": "unknown_target_workflow",
                    "workflow_id": workflow.workflow_id,
                    "target_workflow_id": plan.target_workflow.workflow_id,
                    "intent_id": plan.intent.intent_id,
                },
            }

        expected_steps = canonical_workflow.tool_chain
        actual_steps = tuple(step.tool_id for step in plan.steps)
        if actual_steps != expected_steps:
            return {
                "status": "contract_violation",
                "summary": (
                    f"Plan steps {list(actual_steps)} do not match the registry tool chain "
                    f"{list(expected_steps)} for workflow '{workflow.workflow_id}'."
                ),
                "highlights": (f"REJECTED: step_chain_mismatch workflow={workflow.workflow_id}",),
                "authority_paths": ("config/operator/workflows.yaml",),
                "notes": ("Runtime plan contract: execute() only dispatches the registry-declared tool chain.",),
                "details": {
                    "violation": "step_chain_mismatch",
                    "workflow_id": workflow.workflow_id,
                    "expected_steps": list(expected_steps),
                    "actual_steps": list(actual_steps),
                    "intent_id": plan.intent.intent_id,
                },
            }

        unknown_tools = [tool_id for tool_id in actual_steps if tool_id not in self.registry.tools]
        if unknown_tools:
            return {
                "status": "contract_violation",
                "summary": (
                    f"Plan references tool ids that are not present in the operator registry: {unknown_tools}."
                ),
                "highlights": ("REJECTED: unknown tool in plan",),
                "authority_paths": ("config/operator/tools.yaml", "config/operator/workflows.yaml"),
                "notes": ("Runtime plan contract: all dispatched tools must be registry-declared.",),
                "details": {
                    "violation": "unknown_tool",
                    "workflow_id": workflow.workflow_id,
                    "unknown_tools": unknown_tools,
                    "intent_id": plan.intent.intent_id,
                },
            }

        requested_workflow = getattr(plan.intent, "requested_workflow", None)
        resolved_requested = None
        if requested_workflow:
            resolved_requested = (
                self.registry.resolve_workflow_name(requested_workflow)
                or self.registry.workflows.get(str(requested_workflow))
            )
        if requested_workflow and resolved_requested is None:
            return {
                "status": "contract_violation",
                "summary": (
                    f"Requested workflow '{requested_workflow}' does not resolve in the operator registry."
                ),
                "highlights": (f"REJECTED: unresolvable requested_workflow={requested_workflow}",),
                "authority_paths": ("config/operator/workflows.yaml", "config/operator/intents.yaml"),
                "notes": ("Runtime plan contract: requested workflows must resolve through the registry.",),
                "details": {
                    "violation": "requested_workflow_unresolvable",
                    "workflow_id": workflow.workflow_id,
                    "requested_workflow": requested_workflow,
                    "intent_id": plan.intent.intent_id,
                },
            }

        if plan.target_workflow is not None and resolved_requested is not None:
            if plan.target_workflow.workflow_id != resolved_requested.workflow_id:
                return {
                    "status": "contract_violation",
                    "summary": (
                        f"Target workflow '{plan.target_workflow.workflow_id}' does not match requested workflow "
                        f"'{resolved_requested.workflow_id}'."
                    ),
                    "highlights": ("REJECTED: target_workflow/requested_workflow mismatch",),
                    "authority_paths": ("config/operator/workflows.yaml", "config/operator/intents.yaml"),
                    "notes": ("Runtime plan contract: requested and target workflows must agree.",),
                    "details": {
                        "violation": "target_workflow_mismatch",
                        "workflow_id": workflow.workflow_id,
                        "target_workflow_id": plan.target_workflow.workflow_id,
                        "requested_workflow": requested_workflow,
                        "resolved_requested_workflow_id": resolved_requested.workflow_id,
                        "intent_id": plan.intent.intent_id,
                    },
                }

        intent_def = self.registry.intents.get(plan.intent.intent_id)
        intent_binding_ok = False

        if plan.intent.intent_id in canonical_workflow.intent_ids:
            intent_binding_ok = True
        elif intent_def is not None and intent_def.default_workflow == canonical_workflow.workflow_id:
            intent_binding_ok = True
        elif resolved_requested is not None and resolved_requested.workflow_id == canonical_workflow.workflow_id:
            intent_binding_ok = True

        if not intent_binding_ok:
            return {
                "status": "contract_violation",
                "summary": (
                    f"Intent '{plan.intent.intent_id}' is not authorized to execute workflow "
                    f"'{workflow.workflow_id}' under the operator registry contract."
                ),
                "highlights": (
                    f"REJECTED: intent/workflow mismatch intent={plan.intent.intent_id} workflow={workflow.workflow_id}",
                ),
                "authority_paths": ("config/operator/intents.yaml", "config/operator/workflows.yaml"),
                "notes": ("Runtime plan contract: execute() requires registry-declared intent/workflow binding.",),
                "details": {
                    "violation": "intent_workflow_mismatch",
                    "workflow_id": workflow.workflow_id,
                    "workflow_intent_ids": list(canonical_workflow.intent_ids),
                    "requested_workflow": requested_workflow,
                    "intent_id": plan.intent.intent_id,
                },
            }

        return None

    def execute(self, plan: OperatorPlan) -> OperatorRunResult:
        started_at = datetime.now(timezone.utc).isoformat()
        run_id = _make_run_id(plan.intent.command_text, started_at)
        tool_results: list[ToolExecution] = []
        highlights: list[str] = []
        authority_paths: list[str] = list(plan.workflow.authority_paths if plan.workflow else ())
        notes: list[str] = list(plan.notes)
        continued_from: str | None = None
        gate_validation: dict[str, Any] | None = None
        plan_violation = self._check_plan_contract(plan)

        if plan_violation is not None:
            execution = ToolExecution(
                tool_id="plan_contract",
                status=str(plan_violation.get("status", "contract_violation")),
                summary=str(plan_violation.get("summary", "")),
                highlights=tuple(plan_violation.get("highlights", ())),
                authority_paths=tuple(plan_violation.get("authority_paths", ())),
                notes=tuple(plan_violation.get("notes", ())),
                details=dict(plan_violation.get("details", {})),
            )
            tool_results.append(execution)
            highlights.extend(execution.highlights)
            authority_paths.extend(execution.authority_paths)
            notes.extend(execution.notes)
            status = execution.status
            summary = execution.summary

        elif plan.status != "ready":
            status = "unsupported" if plan.status == "unsupported" else "error"
            summary = (
                "The operator did not execute a workflow because the request is outside the bounded v0 surface."
                if status == "unsupported"
                else "The operator could not build a valid workflow plan."
            )

        # ── GOVERNANCE GATE: write-mode pre-dispatch enforcement ──────
        elif self._is_write_mode(plan):
            if plan.workflow and plan.workflow.workflow_steps:
                import dataclasses
                from .planner import PlanStep

                status = "ok"
                summary = ""
                steps_completed = 0
                for step_index, sub_workflow_step in enumerate(plan.workflow.workflow_steps, start=1):
                    sub_workflow_id = sub_workflow_step.workflow_id
                    input_map = sub_workflow_step.input_map
                    sub_workflow = self.registry.workflows.get(sub_workflow_id)
                    if not sub_workflow:
                        status = "error"
                        summary = f"Sub-workflow {sub_workflow_id} not found."
                        break

                    from .intent import ParsedIntent
                    payload = dataclasses.asdict(plan.intent)
                    resolved_inputs = {}
                    map_error = None
                    for k, v in input_map.items():
                        if v.startswith("$"):
                            field_name = v[1:]
                            if field_name not in payload:
                                map_error = f"missing_required_input: '{field_name}' not in ParsedIntent"
                                break
                            val = getattr(plan.intent, field_name)
                            if val is None:
                                map_error = f"missing_required_input: '{field_name}' is None"
                                break
                            resolved_inputs[k] = val
                        else:
                            resolved_inputs[k] = v

                    if map_error:
                        status = "partial_success" if steps_completed > 0 else "rejected"
                        execution = ToolExecution(
                            tool_id=sub_workflow.tool_chain[0] if sub_workflow.tool_chain else "unknown",
                            status="rejected",
                            summary=f"Missing required input for step {step_index}.",
                            highlights=(),
                            authority_paths=(),
                            notes=(),
                            details={
                                "_consistency_status": "rejected",
                                "rejection_reason": "missing_required_input",
                                "step_index": step_index,
                                "workflow_id": sub_workflow_id,
                                "map_error": map_error,
                            }
                        )
                        tool_results.append(execution)
                        break

                    intent_kwargs = {
                        "command_text": plan.intent.command_text,
                        "intent_id": sub_workflow.intent_ids[0] if sub_workflow.intent_ids else plan.intent.intent_id,
                        "confidence": plan.intent.confidence,
                    }
                    for f in dataclasses.fields(ParsedIntent):
                        if f.name not in ("command_text", "intent_id", "confidence"):
                            intent_kwargs[f.name] = None

                    try:
                        intent_kwargs.update(resolved_inputs)
                        step_intent = ParsedIntent(**intent_kwargs)
                    except TypeError as e:
                        status = "partial_success" if steps_completed > 0 else "rejected"
                        execution = ToolExecution(
                            tool_id=sub_workflow.tool_chain[0] if sub_workflow.tool_chain else "unknown",
                            status="rejected",
                            summary=f"Invalid field mapped for step {step_index}: {e}",
                            highlights=(),
                            authority_paths=(),
                            notes=(),
                            details={
                                "_consistency_status": "rejected",
                                "rejection_reason": "invalid_mapping_field",
                                "step_index": step_index,
                                "workflow_id": sub_workflow_id,
                                "map_error": str(e),
                            }
                        )
                        tool_results.append(execution)
                        break

                    sub_plan = dataclasses.replace(
                        plan,
                        intent=step_intent,
                        workflow=sub_workflow,
                        steps=tuple(PlanStep(tool_id=t, description="Compound Step") for t in sub_workflow.tool_chain)
                    )

                    gate_validation = self._validate_write_transition(sub_plan, run_id)
                    if not gate_validation.get("allowed"):
                        gate_reason = str(gate_validation.get("reason") or "policy_rejected")
                        step_status = "rejected" if ("forbidden" in gate_reason or gate_reason == "duplicate_record_detected") else "held"
                        notes.append(f"gate_status={step_status} for layer {sub_workflow_id}")
                        notes.append(f"gate_reason={gate_reason}")

                        tool_id = sub_workflow.tool_chain[0] if sub_workflow.tool_chain else "unknown"
                        execution = ToolExecution(
                            tool_id=tool_id,
                            status=step_status,
                            summary=f"Gate denied execution of step {step_index}.",
                            highlights=(),
                            authority_paths=(),
                            notes=(),
                            details={
                                "_consistency_status": "rejected",
                                "rejection_reason": gate_reason,
                                "step_index": step_index,
                                "workflow_id": sub_workflow_id,
                            }
                        )
                        tool_results.append(execution)

                        authority_paths.append("app/hq/governance/transition_gate.py")
                        _gate_emit_transition_event(
                            gate_validation,
                            run_id=run_id,
                            context={
                                "module": "signal_agent.operator.runtime",
                                "operation": "compound_gate_rejected",
                                "sub_workflow": sub_workflow_id
                            },
                            event_type="operator_transition_rejected"
                        )
                        status = "partial_success" if steps_completed > 0 else "rejected"
                        break

                    # ── CONTEXT ASSEMBLY (after gate, before dispatch) ──
                    sub_context_bundle = self._assemble_execution_context(sub_plan, run_id)

                    step_status = "ok"
                    for step in sub_plan.steps:
                        result = self._dispatch_tool(step.tool_id, sub_plan, run_id, context_bundle=sub_context_bundle)
                        execution = ToolExecution(
                            tool_id=step.tool_id,
                            status=str(result.get("status", "ok")),
                            summary=str(result.get("summary", "")),
                            highlights=tuple(result.get("highlights", ())),
                            authority_paths=tuple(result.get("authority_paths", ())),
                            notes=tuple(result.get("notes", ())),
                            details={
                                **dict(result.get("details", {})),
                                "step_index": step_index,
                                "workflow_id": sub_workflow_id,
                            },
                        )
                        tool_results.append(execution)
                        highlights.extend(execution.highlights)
                        authority_paths.extend(execution.authority_paths)
                        notes.extend(execution.notes)
                        summary = execution.summary or summary
                        if execution.status != "ok":
                            step_status = execution.status
                            status = "partial_success" if steps_completed > 0 else execution.status
                        if execution.details.get("continued_from"):
                            continued_from = str(execution.details["continued_from"])

                    _gate_emit_transition_event(
                        gate_validation,
                        run_id=run_id,
                        context={
                            "module": "signal_agent.operator.runtime",
                            "operation": "compound_gate_allowed",
                            "sub_workflow": sub_workflow_id
                        },
                        event_type="operator_transition_allowed"
                    )

                    if step_status != "ok":
                        break
                    steps_completed += 1

                if not summary:
                    summary = "The operator completed the requested compound write-mode workflow."

            else:
                gate_validation = self._validate_write_transition(plan, run_id)

                if not gate_validation.get("allowed"):
                    # Gate rejected — do NOT dispatch any tool.
                    gate_reason = str(gate_validation.get("reason") or "policy_rejected")
                    status = "rejected" if ("forbidden" in gate_reason or gate_reason == "duplicate_record_detected") else "held"
                    summary = (
                        f"Transition gate denied write-mode execution: {gate_reason}. "
                        f"Workflow {plan.workflow.workflow_id} was not dispatched."
                    )
                    notes.append(f"gate_status={status}")
                    notes.append(f"gate_reason={gate_reason}")

                    if gate_reason == "duplicate_record_detected":
                        tool_id = plan.workflow.tool_chain[0] if (plan.workflow and plan.workflow.tool_chain) else "unknown"
                        execution = ToolExecution(
                            tool_id=tool_id,
                            status="rejected",
                            summary="Gate denied duplicate execution.",
                            highlights=(),
                            authority_paths=(),
                            notes=(),
                            details={
                                "_consistency_status": "rejected",
                                "rejection_reason": "duplicate_record_detected"
                            }
                        )
                        tool_results.append(execution)

                    authority_paths.append("app/hq/governance/transition_gate.py")
                    authority_paths.append("config/state_machine.yaml")

                    # Emit the rejected transition event for auditability.
                    _gate_emit_transition_event(
                        gate_validation,
                        run_id=run_id,
                        context={
                            "module": "signal_agent.operator.runtime",
                            "operation": "write_mode_gate_rejected",
                        },
                        event_type="operator_transition_rejected",
                    )
                else:
                    # Gate allowed — proceed with tool dispatch.
                    # ── CONTEXT ASSEMBLY (after gate, before dispatch) ──
                    context_bundle = self._assemble_execution_context(plan, run_id)

                    status = "ok"
                    summary = ""
                    for step in plan.steps:
                        result = self._dispatch_tool(step.tool_id, plan, run_id, context_bundle=context_bundle)
                        execution = ToolExecution(
                            tool_id=step.tool_id,
                            status=str(result.get("status", "ok")),
                            summary=str(result.get("summary", "")),
                            highlights=tuple(result.get("highlights", ())),
                            authority_paths=tuple(result.get("authority_paths", ())),
                            notes=tuple(result.get("notes", ())),
                            details=dict(result.get("details", {})),
                        )
                        tool_results.append(execution)
                        highlights.extend(execution.highlights)
                        authority_paths.extend(execution.authority_paths)
                        notes.extend(execution.notes)
                        summary = execution.summary or summary
                        if execution.status != "ok":
                            status = execution.status
                        if execution.details.get("continued_from"):
                            continued_from = str(execution.details["continued_from"])

                    if not summary:
                        summary = "The operator completed the requested write-mode workflow."

                    # Emit the allowed transition event for auditability.
                    _gate_emit_transition_event(
                        gate_validation,
                        run_id=run_id,
                        context={
                            "module": "signal_agent.operator.runtime",
                            "operation": "write_mode_gate_allowed",
                        },
                        event_type="operator_transition_allowed",
                    )

        # ── READ-ONLY / PLACEHOLDER: no gate required ─────────────────
        else:
            # ── CONTEXT ASSEMBLY (read-only, no gate needed) ──────────
            context_bundle = self._assemble_execution_context(plan, run_id)

            status = "ok"
            summary = ""
            for step in plan.steps:
                result = self._dispatch_tool(step.tool_id, plan, run_id, context_bundle=context_bundle)
                execution = ToolExecution(
                    tool_id=step.tool_id,
                    status=str(result.get("status", "ok")),
                    summary=str(result.get("summary", "")),
                    highlights=tuple(result.get("highlights", ())),
                    authority_paths=tuple(result.get("authority_paths", ())),
                    notes=tuple(result.get("notes", ())),
                    details=dict(result.get("details", {})),
                )
                tool_results.append(execution)
                highlights.extend(execution.highlights)
                authority_paths.extend(execution.authority_paths)
                notes.extend(execution.notes)
                summary = execution.summary or summary
                if execution.status != "ok":
                    status = execution.status
                if execution.details.get("continued_from"):
                    continued_from = str(execution.details["continued_from"])

            if not summary:
                summary = "The operator completed the requested workflow."

        completed_at = datetime.now(timezone.utc).isoformat()
        deduped_paths = tuple(dict.fromkeys(path for path in authority_paths if path))
        deduped_notes = tuple(dict.fromkeys(note for note in notes if note))
        result = OperatorRunResult(
            run_id=run_id,
            command_text=plan.intent.command_text,
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            intent_id=plan.intent.intent_id,
            workflow_id=plan.workflow.workflow_id if plan.workflow else None,
            target_workflow_id=plan.target_workflow.workflow_id if plan.target_workflow else None,
            summary=summary,
            highlights=tuple(highlights),
            authority_paths=deduped_paths,
            notes=deduped_notes,
            tool_results=tuple(tool_results),
            ledger_path=str(self.ledger_path),
            run_record_path=str(self.runs_dir / f"{run_id}.json"),
            continued_from=continued_from,
        )
        self._write_run_record(plan, result)
        self._append_ledger_entry(result)
        self._append_canonical_operator_decision(plan, result, gate_validation)
        self._write_session_state(result)
        return result

    def _should_append_canonical_operator_decision(
        self,
        plan: OperatorPlan,
        result: OperatorRunResult,
    ) -> bool:
        if self.canonical_ledger_path is None:
            return False
        if self._is_write_mode(plan):
            return True
        if result.status not in {"contract_violation", "rejected", "held"}:
            return False
        return any(
            self._tool_declares_lifecycle_writes(step.tool_id)
            for step in plan.steps
        )

    def _append_canonical_operator_decision(
        self,
        plan: OperatorPlan,
        result: OperatorRunResult,
        gate_validation: dict[str, Any] | None,
    ) -> None:
        if not self._should_append_canonical_operator_decision(plan, result):
            return

        from signal_agent.formal_governance.adapters import append_operator_decision_entry

        append_operator_decision_entry(
            self.canonical_ledger_path,
            plan=plan,
            result=result,
            gate_validation=gate_validation,
            subsystem_refs=[
                {
                    "subsystem": "operator_registry",
                    "ref_type": "workflow_manifest",
                    "path": str(self.repo_root / "config" / "operator" / "workflows.yaml"),
                    "workflow_id": result.workflow_id,
                },
                {
                    "subsystem": "operator_registry",
                    "ref_type": "tool_manifest",
                    "path": str(self.repo_root / "config" / "operator" / "tools.yaml"),
                },
            ],
        )

    # ------------------------------------------------------------------
    # Tool write contract verification
    # ------------------------------------------------------------------

    def _tool_declares_lifecycle_writes(self, tool_id: str) -> tuple[str, ...]:
        """
        Return the declared writes for a tool, excluding operator audit
        infrastructure paths.

        For non-transactional tools, paths under data/operator/ are excluded
        because they are runtime bookkeeping (runs ledger, session state).

        For transactional tools, data/operator/state/ paths ARE included
        because the tool explicitly governs that mutation.  Only the
        audit ledger (data/operator/runs/) remains excluded.
        """
        tool_def = self.registry.tools.get(tool_id)
        if tool_def is None:
            return ()

        is_txn = getattr(tool_def, "transactional", False)

        if is_txn:
            # Transactional tools: only exclude the audit ledger directory.
            return tuple(
                w for w in tool_def.writes
                if not w.startswith("data/operator/runs/")
            )
        # Non-transactional: exclude all of data/operator/.
        return tuple(
            w for w in tool_def.writes
            if not w.startswith("data/operator/")
        )

    def _check_tool_write_contract(
        self,
        tool_id: str,
        plan: OperatorPlan,
    ) -> dict[str, Any] | None:
        """
        Pre-dispatch assertion: if a tool declares lifecycle writes, the
        enclosing workflow MUST be mode="write".  If not, return a hard
        failure result that prevents execution.

        Returns None if the contract is satisfied (safe to dispatch).
        Returns a failure result dict if the contract is violated.
        """
        lifecycle_writes = self._tool_declares_lifecycle_writes(tool_id)
        if not lifecycle_writes:
            # Tool has no lifecycle writes — safe in any workflow mode.
            return None

        workflow_mode = plan.workflow.mode if plan.workflow else "read_only"
        if workflow_mode == "write":
            # Write-mode workflow — tool is allowed to declare writes.
            return None

        # CONTRACT VIOLATION: mutating tool in non-write workflow.
        return {
            "status": "contract_violation",
            "summary": (
                f"Tool '{tool_id}' declares lifecycle writes "
                f"{list(lifecycle_writes)} but workflow mode is '{workflow_mode}'. "
                f"Non-write workflows may not dispatch mutating tools."
            ),
            "highlights": (
                f"HALTED: tool={tool_id} declares writes in {workflow_mode} workflow",
            ),
            "authority_paths": (
                "config/operator/tools.yaml",
                "config/operator/workflows.yaml",
            ),
            "notes": (
                "Enforcement rule: tools with declared lifecycle writes require workflow.mode='write'.",
            ),
            "details": {
                "tool_id": tool_id,
                "declared_writes": list(lifecycle_writes),
                "workflow_mode": workflow_mode,
                "workflow_id": plan.workflow.workflow_id if plan.workflow else None,
                "violation": "non_write_workflow_with_mutating_tool",
            },
        }

    def _tool_audit_metadata(self, tool_id: str, *, evidence_level: str = "declared_only") -> dict[str, Any]:
        """
        Return audit metadata for a dispatched tool: declared reads,
        declared writes, and verification status.
        """
        tool_def = self.registry.tools.get(tool_id)
        if tool_def is None:
            return {
                "declared_reads": [],
                "declared_writes": [],
                "verification_status": "unknown_tool",
            }
        lifecycle_writes = self._tool_declares_lifecycle_writes(tool_id)
        return {
            "declared_reads": list(tool_def.reads),
            "declared_writes": list(tool_def.writes),
            "lifecycle_writes": list(lifecycle_writes),
            "verification_status": evidence_level,
        }

    def _derived_observation_parent_dirs(
        self,
        candidates: tuple[str, ...],
    ) -> tuple[str, ...]:
        """
        Derive immediate non-root parent directories for file-like declared
        surfaces so sibling file creation/deletion becomes observable.

        The helper stays intentionally bounded:
          - only immediate parents are added
          - repo root is excluded to avoid a broad top-level watch scope
          - explicitly declared directories are handled separately
        """
        derived: list[str] = []
        seen: set[str] = set()

        for rel_path in candidates:
            if not rel_path:
                continue

            full_path = self.repo_root / rel_path
            rel_obj = Path(rel_path)
            looks_file = full_path.is_file() or (
                not full_path.exists() and bool(rel_obj.suffix)
            )
            if not looks_file:
                continue

            parent_rel = str(rel_obj.parent).replace("\\", "/")
            if parent_rel in {"", "."} or parent_rel in seen:
                continue

            seen.add(parent_rel)
            derived.append(parent_rel)

        return tuple(derived)

    def _tool_observation_scope_paths(
        self,
        tool_id: str,
        plan: OperatorPlan,
    ) -> tuple[str, ...]:
        """
        Build the explicit bounded observation scope for a tool dispatch.

        The scope is bounded to already-declared repo surfaces:
          - tool reads
          - tool lifecycle writes
          - workflow authority paths
          - workflow writes paths
          - immediate non-root parent directories for declared file surfaces

        Directory paths are expanded to current descendants so changes to
        existing files inside declared directories become observable.
        Immediate parent directories derived from declared file surfaces are
        kept in scope without recursive expansion so sibling-file create/delete
        events become visible without exploding the observation set.

        This scope is used for two checks:
          - zero-write tools: reject observed mutation on declared read or
            authority surfaces
          - declared-write tools: reject observed mutation on in-scope
            surfaces outside the declared write set
        """
        tool_def = self.registry.tools.get(tool_id)
        workflow = plan.workflow
        lifecycle_writes = self._tool_declares_lifecycle_writes(tool_id)
        candidates: list[str] = []
        if tool_def is not None:
            candidates.extend(tool_def.reads)
        candidates.extend(lifecycle_writes)
        if workflow is not None:
            candidates.extend(workflow.authority_paths)
            candidates.extend(workflow.writes_paths)

        declared_directories: list[str] = []
        expanded: list[str] = []
        seen: set[str] = set()
        declared_candidates = tuple(candidates)
        for rel_path in declared_candidates:
            if not rel_path or rel_path in seen:
                continue
            seen.add(rel_path)
            expanded.append(rel_path)

            full_path = self.repo_root / rel_path
            if full_path.exists() and full_path.is_dir():
                declared_directories.append(rel_path)

        for rel_dir in self._derived_observation_parent_dirs(declared_candidates):
            if rel_dir in seen:
                continue
            seen.add(rel_dir)
            expanded.append(rel_dir)

        for rel_dir in declared_directories:
            full_dir = self.repo_root / rel_dir
            for nested in sorted(full_dir.rglob("*")):
                try:
                    nested_rel = str(nested.relative_to(self.repo_root)).replace("\\", "/")
                except ValueError:
                    continue
                if nested_rel in seen:
                    continue
                seen.add(nested_rel)
                expanded.append(nested_rel)
        return tuple(expanded)

    @staticmethod
    def _consistency_requires_rejection(consistency_status: str) -> bool:
        return consistency_status in {
            "declared_without_observation",
            "no_effect_observed",
            "undeclared_mutation",
            "undeclared_extra_mutation",
            "partial_mutation_detected",
            "undeclared_mutation_transactional",
            "transaction_corrupted",
        }

    @staticmethod
    def _observed_changes_outside_declared_writes(
        lifecycle_writes: tuple[str, ...],
        boundary_evidence: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        """
        Return observed changes that fall outside the declared lifecycle
        write set but still inside the explicit observation scope.
        """
        if not lifecycle_writes or boundary_evidence is None:
            return []

        declared = set(lifecycle_writes)
        undeclared: list[dict[str, Any]] = []
        for change in boundary_evidence.get("observed_changes", ()):
            path = str(change.get("path") or "")
            if path in declared:
                continue

            added_entries = list(change.get("added_entries", ()))
            removed_entries = list(change.get("removed_entries", ()))
            if added_entries or removed_entries:
                changed_children = []
                for entry in (*added_entries, *removed_entries):
                    normalized_entry = str(entry).rstrip("/")
                    child_path = f"{path}/{normalized_entry}" if path else normalized_entry
                    changed_children.append(child_path.replace("\\", "/"))
                # append_jsonl_atomic persists a same-path ".lock" sidecar.
                # Treat that auxiliary file as part of the declared file surface
                # rather than a rogue sibling mutation.
                if changed_children and all(
                    child in declared or child.endswith(".lock") and child[:-5] in declared
                    for child in changed_children
                ):
                    continue

            undeclared.append(dict(change))

        return undeclared

    def _make_consistency_violation(
        self,
        tool_id: str,
        result: dict[str, Any],
        consistency_status: str,
        lifecycle_writes: tuple[str, ...],
    ) -> dict[str, Any]:
        """
        Promote a post-dispatch consistency mismatch into a hard rejection.
        """
        summaries = {
            "declared_without_observation": (
                "declared write surfaces could not be observed after dispatch"
            ),
            "no_effect_observed": (
                "observed effects did not match the declared writes"
            ),
            "undeclared_mutation": (
                "observed mutation occurred on a tool with zero declared writes"
            ),
            "undeclared_extra_mutation": (
                "observed mutation occurred outside the tool's declared write set"
            ),
            "partial_mutation_detected": (
                "only part of the declared transactional mutation was observed"
            ),
            "undeclared_mutation_transactional": (
                "transactional mutation touched undeclared surfaces"
            ),
            "transaction_corrupted": (
                "the transactional post-state was classified as corrupted"
            ),
        }
        original_authority_paths = tuple(result.get("authority_paths", ()))
        original_notes = tuple(result.get("notes", ()))
        details = dict(result.get("details", {}))
        details.update(
            {
                "tool_id": tool_id,
                "violation": "observed_effects_mismatch",
                "rejection_reason": consistency_status,
                "original_status": result.get("status", "ok"),
                "original_summary": result.get("summary", ""),
                "declared_lifecycle_writes": list(lifecycle_writes),
            },
        )
        return {
            "status": "contract_violation",
            "summary": (
                f"Tool '{tool_id}' was rejected because {summaries.get(consistency_status, consistency_status)} "
                f"(consistency_status={consistency_status})."
            ),
            "highlights": (
                f"REJECTED: tool={tool_id} consistency_status={consistency_status}",
            ),
            "authority_paths": tuple(
                dict.fromkeys(
                    (
                        *original_authority_paths,
                        "config/operator/tools.yaml",
                        "config/operator/workflows.yaml",
                    ),
                ),
            ),
            "notes": tuple(
                dict.fromkeys(
                    (
                        *original_notes,
                        "Observed execution effects must match declared boundaries.",
                    ),
                ),
            ),
            "details": details,
        }

    # ------------------------------------------------------------------
    # Boundary evidence collection
    # ------------------------------------------------------------------

    def _snapshot_paths(self, paths: tuple[str, ...]) -> dict[str, dict[str, Any]]:
        """
        Snapshot file stat (exists, size_bytes, mtime) for a list of
        repo-relative paths.  Returns a dict keyed by path.

        This is a read-only operation: no files are modified.
        Cost: one stat syscall per path.
        """
        snapshots: dict[str, dict[str, Any]] = {}
        for rel_path in paths:
            full = self.repo_root / rel_path
            try:
                st = full.stat()
                if full.is_dir():
                    entries: list[str] = []
                    for nested in sorted(full.rglob("*")):
                        try:
                            nested_rel = str(nested.relative_to(full)).replace("\\", "/")
                        except ValueError:
                            continue
                        if nested.is_dir():
                            nested_rel = f"{nested_rel}/"
                        entries.append(nested_rel)
                    snapshots[rel_path] = {
                        "exists": True,
                        "is_dir": True,
                        "size_bytes": st.st_size,
                        "mtime": st.st_mtime,
                        "entries": entries,
                    }
                    continue
                snapshots[rel_path] = {
                    "exists": True,
                    "is_dir": False,
                    "size_bytes": st.st_size,
                    "mtime": st.st_mtime,
                    "entries": [],
                }
            except OSError:
                snapshots[rel_path] = {
                    "exists": False,
                    "is_dir": False,
                    "size_bytes": 0,
                    "mtime": 0.0,
                    "entries": [],
                }
        return snapshots

    @staticmethod
    def _compute_boundary_evidence(
        write_paths: tuple[str, ...],
        pre: dict[str, dict[str, Any]],
        post: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Compare pre/post snapshots and emit grounded boundary evidence.
        Does not prove all side effects occurred correctly, but does
        record whether declared write targets changed at the boundary.
        """
        observed_changes: list[dict[str, Any]] = []
        for path in write_paths:
            pre_snap = pre.get(path, {"exists": False, "size_bytes": 0, "mtime": 0.0})
            post_snap = post.get(path, {"exists": False, "size_bytes": 0, "mtime": 0.0})
            change: dict[str, Any] = {"path": path}
            pre_is_dir = bool(pre_snap.get("is_dir"))
            post_is_dir = bool(post_snap.get("is_dir"))

            if pre_is_dir or post_is_dir:
                pre_entries = set(pre_snap.get("entries", ()))
                post_entries = set(post_snap.get("entries", ()))
                added_entries = sorted(post_entries - pre_entries)
                removed_entries = sorted(pre_entries - post_entries)

                if not pre_snap["exists"] and post_snap["exists"]:
                    change["created"] = True
                    change["delta_bytes"] = 0
                    change["mtime_changed"] = True
                elif pre_snap["exists"] and not post_snap["exists"]:
                    change["created"] = False
                    change["deleted"] = True
                    change["delta_bytes"] = 0
                    change["mtime_changed"] = True
                else:
                    change["created"] = False
                    change["delta_bytes"] = 0
                    change["mtime_changed"] = post_snap["mtime"] != pre_snap["mtime"]

                if added_entries:
                    change["added_entries"] = added_entries
                if removed_entries:
                    change["removed_entries"] = removed_entries

                if (
                    change.get("created")
                    or change.get("deleted")
                    or added_entries
                    or removed_entries
                ):
                    observed_changes.append(change)
                continue

            if not pre_snap["exists"] and post_snap["exists"]:
                change["created"] = True
                change["delta_bytes"] = post_snap["size_bytes"]
                change["mtime_changed"] = True
            elif pre_snap["exists"] and post_snap["exists"]:
                change["created"] = False
                change["delta_bytes"] = post_snap["size_bytes"] - pre_snap["size_bytes"]
                change["mtime_changed"] = post_snap["mtime"] != pre_snap["mtime"]
            else:
                change["created"] = False
                change["delta_bytes"] = 0
                change["mtime_changed"] = False
            # Only include paths that actually changed.
            if change.get("created") or change.get("delta_bytes", 0) != 0 or change.get("mtime_changed"):
                observed_changes.append(change)

        return {
            "write_paths_checked": list(write_paths),
            "pre_dispatch": pre,
            "post_dispatch": post,
            "observed_changes": observed_changes,
            "evidence_level": "boundary_observable",
        }

    @staticmethod
    def _classify_consistency(
        lifecycle_writes: tuple[str, ...],
        boundary_evidence: dict[str, Any] | None,
    ) -> str:
        """
        Classify the consistency between declared writes and observed
        boundary evidence.  Returns one of:

          - "observed_as_declared"          declared writes AND observable changes
          - "declared_without_observation"  declared writes BUT no evidence collected
          - "no_effect_observed"            declared writes, evidence collected, but
                                            no file created/grew/changed
          - "undeclared_mutation"            no declared writes BUT evidence shows changes
          - "consistent_read_only"          no declared writes, no evidence (nominal)

        Dispatch converts mismatch states into hard failures.
        """
        has_declared = bool(lifecycle_writes)
        has_evidence = boundary_evidence is not None
        has_changes = bool(
            boundary_evidence.get("observed_changes")
        ) if has_evidence else False

        if has_declared and has_evidence and has_changes:
            return "observed_as_declared"
        if has_declared and has_evidence and not has_changes:
            return "no_effect_observed"
        if has_declared and not has_evidence:
            return "declared_without_observation"
        if not has_declared and has_evidence and has_changes:
            return "undeclared_mutation"
        # No declared writes, no evidence of mutation.
        return "consistent_read_only"

    # ------------------------------------------------------------------
    # Transactional snapshot & evidence (v0)
    # ------------------------------------------------------------------

    def _is_transactional_tool(self, tool_id: str) -> bool:
        """Return True if the tool is declared transactional in the registry."""
        tool_def = self.registry.tools.get(tool_id)
        return tool_def is not None and getattr(tool_def, "transactional", False)

    def _make_transaction_id(self, run_id: str, tool_id: str) -> str:
        """Generate a deterministic, unique transaction ID."""
        seed = f"{run_id}|{tool_id}|{datetime.now(timezone.utc).isoformat()}"
        return f"txn_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:16]}"

    def _create_transaction_snapshot(
        self,
        target_rel_path: str,
        transaction_id: str,
        operator_run_id: str,
    ) -> dict[str, Any]:
        """
        Create a pre-mutation snapshot for a transactional write.

        Creates:
          data/operator/state/snapshots/<transaction_id>/
            <basename>.before.json
            manifest.json

        Returns a manifest dict on success.
        Raises RuntimeError if snapshot cannot be created (aborts transaction).
        """
        target_full = self.repo_root / target_rel_path
        snapshot_dir = self.repo_root / "data" / "operator" / "state" / "snapshots" / transaction_id

        # Fail-closed: if the target doesn't exist, that's still a valid
        # pre-state ("file did not exist"), but we record it explicitly.
        target_basename = Path(target_rel_path).stem
        snapshot_filename = f"{target_basename}.before.json"
        snapshot_path = snapshot_dir / snapshot_filename

        try:
            snapshot_dir.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            raise RuntimeError(
                f"Snapshot directory already exists for transaction {transaction_id}. "
                f"Refusing to overwrite — possible duplicate transaction."
            )

        created_at = datetime.now(timezone.utc).isoformat()

        if target_full.exists():
            content = target_full.read_bytes()
            pre_hash = hashlib.sha256(content).hexdigest()
            pre_size = len(content)
            # Write the snapshot copy.
            snapshot_path.write_bytes(content)
        else:
            pre_hash = None
            pre_size = 0
            # Write an explicit "file did not exist" marker.
            snapshot_path.write_text(
                json.dumps({"_snapshot_marker": "file_did_not_exist"}, indent=2),
                encoding="utf-8",
            )

        manifest = {
            "transaction_id": transaction_id,
            "operator_run_id": operator_run_id,
            "target_path": target_rel_path,
            "snapshot_path": str(snapshot_path.relative_to(self.repo_root)),
            "pre_hash": pre_hash,
            "pre_size_bytes": pre_size,
            "created_at": created_at,
        }

        manifest_path = snapshot_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        return manifest

    def _snapshot_paths_with_hash(
        self, paths: tuple[str, ...],
    ) -> dict[str, dict[str, Any]]:
        """
        Like _snapshot_paths but includes SHA-256 content hash.
        Used for transactional tools where delta_bytes is insufficient.
        """
        snapshots: dict[str, dict[str, Any]] = {}
        for rel_path in paths:
            full = self.repo_root / rel_path
            try:
                content = full.read_bytes()
                st = full.stat()
                snapshots[rel_path] = {
                    "exists": True,
                    "size_bytes": st.st_size,
                    "mtime": st.st_mtime,
                    "content_hash": hashlib.sha256(content).hexdigest(),
                }
            except OSError:
                snapshots[rel_path] = {
                    "exists": False,
                    "size_bytes": 0,
                    "mtime": 0.0,
                    "content_hash": None,
                }
        return snapshots

    @staticmethod
    def _compute_transactional_boundary_evidence(
        write_paths: tuple[str, ...],
        pre: dict[str, dict[str, Any]],
        post: dict[str, dict[str, Any]],
        transaction_id: str,
        mutation_type: str,
    ) -> dict[str, Any]:
        """
        Hash-based boundary evidence for transactional mutations.
        Detects content changes even when file size is unchanged.
        """
        observed_changes: list[dict[str, Any]] = []
        all_paths_changed = True
        any_path_changed = False

        for path in write_paths:
            pre_snap = pre.get(path, {"exists": False, "size_bytes": 0, "content_hash": None})
            post_snap = post.get(path, {"exists": False, "size_bytes": 0, "content_hash": None})

            pre_hash = pre_snap.get("content_hash")
            post_hash = post_snap.get("content_hash")
            hash_changed = pre_hash != post_hash

            change: dict[str, Any] = {
                "path": path,
                "pre_hash": pre_hash,
                "post_hash": post_hash,
                "hash_changed": hash_changed,
                "existence_before": pre_snap["exists"],
                "existence_after": post_snap["exists"],
                "delta_bytes": post_snap["size_bytes"] - pre_snap["size_bytes"],
            }

            if hash_changed:
                any_path_changed = True
                observed_changes.append(change)
            else:
                all_paths_changed = False

        return {
            "write_paths_checked": list(write_paths),
            "pre_dispatch": pre,
            "post_dispatch": post,
            "observed_changes": observed_changes,
            "evidence_level": "transactional_boundary_observable",
            "transaction_id": transaction_id,
            "mutation_type": mutation_type,
            "all_declared_paths_changed": all_paths_changed and any_path_changed,
            "partial_mutation": any_path_changed and not all_paths_changed,
        }

    @staticmethod
    def _classify_transactional_consistency(
        lifecycle_writes: tuple[str, ...],
        boundary_evidence: dict[str, Any] | None,
    ) -> str:
        """
        Extended consistency classifier for transactional mutations.

        Returns one of:
          - "observed_as_declared_transactional"   hash changed on all declared paths
          - "partial_mutation_detected"            hash changed on some but not all
          - "no_effect_observed"                   no hash changes observed
          - "undeclared_mutation_transactional"     changes on undeclared paths
          - "transaction_corrupted"                post-state is invalid

        Dispatch converts mismatch states into hard failures.
        """
        if boundary_evidence is None:
            return "declared_without_observation"

        has_changes = bool(boundary_evidence.get("observed_changes"))
        all_changed = boundary_evidence.get("all_declared_paths_changed", False)
        partial = boundary_evidence.get("partial_mutation", False)

        if has_changes and all_changed:
            return "observed_as_declared_transactional"
        if partial:
            return "partial_mutation_detected"
        if not has_changes:
            return "no_effect_observed"
        return "undeclared_mutation_transactional"

    # ------------------------------------------------------------------
    # Tool dispatch
    # ------------------------------------------------------------------

    def _dispatch_tool(
        self,
        tool_id: str,
        plan: OperatorPlan,
        run_id: str,
        *,
        context_bundle: Any = None,
    ) -> dict[str, Any]:
        # ── PRE-DISPATCH WRITE CONTRACT CHECK ─────────────────────────
        violation = self._check_tool_write_contract(tool_id, plan)
        if violation is not None:
            return violation

        # ── DETERMINE TOOL CLASS ──────────────────────────────────────
        lifecycle_writes = self._tool_declares_lifecycle_writes(tool_id)
        is_write_workflow = self._is_write_mode(plan)
        is_transactional = self._is_transactional_tool(tool_id)
        observation_scope_paths = self._tool_observation_scope_paths(tool_id, plan)

        # ── TRANSACTIONAL SNAPSHOT (must happen BEFORE handler) ───────
        transaction_id: str | None = None
        snapshot_manifest: dict[str, Any] | None = None
        pre_hash_snapshot: dict[str, dict[str, Any]] | None = None

        if is_write_workflow and is_transactional and lifecycle_writes:
            transaction_id = self._make_transaction_id(run_id, tool_id)
            # Create snapshot for each declared write path.
            for rel_path in lifecycle_writes:
                try:
                    snapshot_manifest = self._create_transaction_snapshot(
                        rel_path, transaction_id, run_id,
                    )
                except (RuntimeError, OSError) as exc:
                    # Snapshot creation failed — ABORT. Do NOT execute handler.
                    return {
                        "status": "snapshot_failed",
                        "summary": (
                            f"Transaction snapshot failed for '{rel_path}': {exc}. "
                            f"Handler was NOT executed. No mutation occurred."
                        ),
                        "highlights": (f"ABORTED: snapshot creation failed for {rel_path}",),
                        "authority_paths": ("data/operator/state/snapshots/",),
                        "notes": (f"transaction_id={transaction_id}",),
                        "details": {
                            "tool_id": tool_id,
                            "transaction_id": transaction_id,
                            "snapshot_error": str(exc),
                        },
                    }
            # Hash-based pre-snapshot for boundary evidence.
            pre_hash_snapshot = self._snapshot_paths_with_hash(lifecycle_writes)

        # ── APPEND-ONLY BOUNDARY SNAPSHOT (existing path, unchanged) ──
        pre_snapshot: dict[str, dict[str, Any]] | None = None
        if is_write_workflow and lifecycle_writes and not is_transactional:
            pre_snapshot = self._snapshot_paths(lifecycle_writes)

        pre_observation_snapshot: dict[str, dict[str, Any]] | None = None
        if observation_scope_paths:
            pre_observation_snapshot = self._snapshot_paths(observation_scope_paths)

        handlers = {
            "inspect_system_state": self._tool_inspect_system_state,
            "capture_routing_status": self._tool_capture_routing_status,
            "routing_queue_backlog": self._tool_routing_queue_backlog,
            "routing_lineage_drilldown": self._tool_routing_lineage_drilldown,
            "explain_repo_structure": self._tool_explain_repo_structure,
            "list_workflows": self._tool_list_workflows,
            "continue_operator_task": self._tool_continue_operator_task,
            "telemetry_placeholder": self._tool_telemetry_placeholder,
            "show_action_surfaces": self._tool_show_action_surfaces,
            "record_state_append": self._tool_record_state_append,
            "intake_log_append": self._tool_intake_log_append,
            "session_state_overwrite": self._tool_session_state_overwrite,
        }
        handler = handlers.get(tool_id)
        if handler is None:
            result: dict[str, Any] = {
                "status": "error",
                "summary": f"Operator tool is not implemented: {tool_id}",
                "highlights": (),
                "authority_paths": (),
                "notes": (),
                "details": {"tool_id": tool_id},
            }
        else:
            result = handler(plan, run_id, context_bundle=context_bundle)

        # ── POST-DISPATCH: attach audit metadata + boundary evidence ──
        result.setdefault("details", {})

        boundary: dict[str, Any] | None = None
        observation_boundary: dict[str, Any] | None = None
        consistency_status = "unknown"

        if pre_observation_snapshot is not None:
            post_observation_snapshot = self._snapshot_paths(observation_scope_paths)
            observation_boundary = self._compute_boundary_evidence(
                observation_scope_paths,
                pre_observation_snapshot,
                post_observation_snapshot,
            )

        if pre_hash_snapshot is not None and transaction_id is not None:
            # ── TRANSACTIONAL boundary evidence (hash-based) ──────────
            tool_def = self.registry.tools.get(tool_id)
            mutation_type = getattr(tool_def, "mutation_type", "unknown") if tool_def else "unknown"
            post_hash_snapshot = self._snapshot_paths_with_hash(lifecycle_writes)
            boundary = self._compute_transactional_boundary_evidence(
                lifecycle_writes, pre_hash_snapshot, post_hash_snapshot,
                transaction_id, mutation_type or "unknown",
            )
            result["details"]["_boundary_evidence"] = boundary
            result["details"]["_tool_contract"] = self._tool_audit_metadata(
                tool_id, evidence_level="transactional_boundary_observable",
            )
            result["details"]["_transaction_id"] = transaction_id
            if snapshot_manifest is not None:
                result["details"]["_snapshot_manifest"] = snapshot_manifest

            # ── TRANSACTIONAL CONSISTENCY ──────────────────────────────
            consistency_status = self._classify_transactional_consistency(
                lifecycle_writes, boundary,
            )
            result["details"]["_consistency_status"] = consistency_status
        elif pre_snapshot is not None:
            # ── APPEND-ONLY boundary evidence (delta_bytes, unchanged) ─
            post_snapshot = self._snapshot_paths(lifecycle_writes)
            boundary = self._compute_boundary_evidence(
                lifecycle_writes, pre_snapshot, post_snapshot,
            )
            result["details"]["_boundary_evidence"] = boundary
            result["details"]["_tool_contract"] = self._tool_audit_metadata(
                tool_id, evidence_level="boundary_observable",
            )
            consistency_status = self._classify_consistency(
                lifecycle_writes, boundary,
            )
            result["details"]["_consistency_status"] = consistency_status
        elif observation_boundary is not None:
            boundary = observation_boundary
            consistency_status = self._classify_consistency(
                lifecycle_writes, boundary,
            )
            result["details"]["_consistency_status"] = consistency_status
            if consistency_status == "undeclared_mutation":
                result["details"]["_boundary_evidence"] = boundary
                result["details"]["_tool_contract"] = self._tool_audit_metadata(
                    tool_id, evidence_level="boundary_observable",
                )
            else:
                result["details"]["_tool_contract"] = self._tool_audit_metadata(tool_id)
        else:
            result["details"]["_tool_contract"] = self._tool_audit_metadata(tool_id)
            consistency_status = self._classify_consistency(
                lifecycle_writes, None,
            )
            result["details"]["_consistency_status"] = consistency_status

        undeclared_scope_changes = self._observed_changes_outside_declared_writes(
            lifecycle_writes,
            observation_boundary,
        )
        if undeclared_scope_changes:
            result["details"]["_observation_scope_evidence"] = observation_boundary
            result["details"]["_undeclared_observed_changes"] = undeclared_scope_changes
            consistency_status = "undeclared_extra_mutation"
            result["details"]["_consistency_status"] = consistency_status

        if self._consistency_requires_rejection(consistency_status):
            return self._make_consistency_violation(
                tool_id,
                result,
                consistency_status,
                lifecycle_writes,
            )

        return result

    def _tool_inspect_system_state(
        self, _plan: OperatorPlan, _run_id: str, *, context_bundle: Any = None,
    ) -> dict[str, Any]:
        lanes_doc = self._load_yaml_relative("config/lanes.yaml")
        state_doc = self._load_yaml_relative("config/state_machine.yaml")
        active_lanes = [
            str(lane.get("lane_id"))
            for lane in lanes_doc.get("lanes", [])
            if isinstance(lane, dict) and lane.get("status") in {"active", "partial"}
        ]
        blocked_states = [
            state_id
            for state_id, payload in (state_doc.get("states") or {}).items()
            if isinstance(payload, dict) and payload.get("blocked")
        ]
        authority_records = [
            "ARCHITECTURE.md",
            "config/lanes.yaml",
            "config/state_machine.yaml",
            "data/intake/intake.jsonl",
            "data/capture/capture_log.jsonl",
            "data/capture/promotion_log.jsonl",
            "data/capture/routing_log.jsonl",
            "data/state/artifact_registry.jsonl",
        ]
        existing_records = [path for path in authority_records if (self.repo_root / path).exists()]
        legacy_catalog_records = [
            path for path in ("data/artifact_registry.jsonl",)
            if (self.repo_root / path).exists()
        ]

        # ── Context-informed enrichment (Phase 3A) ────────────────────
        context_summary = ""
        if context_bundle is not None and hasattr(context_bundle, "artifact_facts"):
            n_facts = len(context_bundle.artifact_facts)
            n_events = len(context_bundle.recent_events)
            if n_facts or n_events:
                context_summary = (
                    f" Context assembled: {n_facts} artifact facts,"
                    f" {n_events} recent events."
                )

        summary = (
            "Inspected canonical system state from the repo authority files. "
            f"Active lanes: {', '.join(active_lanes) or 'none'}. "
            f"Blocked/control states: {', '.join(blocked_states) or 'none'}."
            f"{context_summary}"
        )
        details: dict[str, Any] = {
            "active_lanes": active_lanes,
            "blocked_states": blocked_states,
            "authority_records": existing_records,
        }
        if legacy_catalog_records:
            details["legacy_catalog_records"] = legacy_catalog_records
        if context_bundle is not None and hasattr(context_bundle, "to_audit_dict"):
            details["_context_assembly"] = context_bundle.to_audit_dict()

        return {
            "status": "ok",
            "summary": summary,
            "highlights": (
                "Canonical package root: signal_agent/.",
                f"Active lanes: {', '.join(active_lanes) or 'none'}.",
                f"Blocked/control states: {', '.join(blocked_states) or 'none'}.",
            ),
            "authority_paths": tuple(existing_records),
            "notes": (),
            "details": details,
        }

    def _tool_explain_repo_structure(self, _plan: OperatorPlan, _run_id: str, **_kwargs: Any) -> dict[str, Any]:
        surfaces = [
            {
                "path": "signal_agent/",
                "role": "canonical_package_root",
                "note": "Owns canonical runtime modules and now owns the operator implementation.",
            },
            {
                "path": "signal_agent/operator/",
                "role": "operator_control_surface",
                "note": "Registry-driven operator package for bounded chat-style control.",
            },
            {
                "path": "signal_agent/cli/operator_cli.py",
                "role": "canonical_cli_entrypoint",
                "note": "Thin module entrypoint for single-turn or interactive operator use.",
            },
            {
                "path": "app/",
                "role": "wrapper_tools",
                "note": "Operational wrappers and compatibility commands; not the canonical source of truth.",
            },
            {
                "path": "config/",
                "role": "declarative_authority",
                "note": "Lane, state-machine, policy, and operator workflow manifests live here.",
            },
            {
                "path": "data/",
                "role": "ledger_and_state",
                "note": "Append-only records, run evidence, and state snapshots live here.",
            },
            {
                "path": "docs/",
                "role": "operator_and_architecture_notes",
                "note": "Operator-facing explanations and Path 2 architecture notes live here.",
            },
            {
                "path": "services/",
                "role": "future_spine_integration",
                "note": "Typed intake and later telemetry/signal expansion seams.",
            },
            {
                "path": "orchestration_core/",
                "role": "deterministic_runtime_reference",
                "note": "Useful pattern for registry resolution, run manifests, and append-only execution logs.",
            },
        ]
        summary = (
            "Explained the repo surfaces relevant to the operator. "
            "The operator is canonical under signal_agent/, reads declarative manifests from config/, and writes audit evidence to data/operator/."
        )
        return {
            "status": "ok",
            "summary": summary,
            "highlights": (
                "signal_agent/ is the canonical package root.",
                "app/ remains a wrapper layer, not the operator source of truth.",
                "config/, data/, and docs/ remain the operator's declarative and audit surfaces.",
            ),
            "authority_paths": tuple(surface["path"] for surface in surfaces),
            "notes": (),
            "details": {"surfaces": surfaces},
        }

    def _tool_capture_routing_status(self, _plan: OperatorPlan, _run_id: str, **_kwargs: Any) -> dict[str, Any]:
        return build_capture_routing_status_tool_result(self.repo_root)

    def _tool_routing_queue_backlog(self, plan: OperatorPlan, _run_id: str, **_kwargs: Any) -> dict[str, Any]:
        return build_routing_queue_backlog_tool_result(
            self.repo_root,
            target=plan.intent.requested_target,
            target_kind=plan.intent.requested_target_kind,
        )

    def _tool_routing_lineage_drilldown(self, plan: OperatorPlan, _run_id: str, **_kwargs: Any) -> dict[str, Any]:
        return build_routing_lineage_drilldown_tool_result(
            self.repo_root,
            target=plan.intent.requested_target,
            target_kind=plan.intent.requested_target_kind,
        )

    def _tool_list_workflows(self, _plan: OperatorPlan, _run_id: str, **_kwargs: Any) -> dict[str, Any]:
        workflows = []
        for workflow in self.registry.workflows.values():
            workflows.append(
                {
                    "workflow_id": workflow.workflow_id,
                    "mode": workflow.mode,
                    "resumable": workflow.resumable,
                    "description": workflow.description,
                }
            )
        summary = "Known operator workflows: " + ", ".join(sorted(workflow["workflow_id"] for workflow in workflows)) + "."
        return {
            "status": "ok",
            "summary": summary,
            "highlights": tuple(
                f"{workflow['workflow_id']} [{workflow['mode']}]: {workflow['description']}"
                for workflow in workflows
            ),
            "authority_paths": ("config/operator/workflows.yaml", "config/operator/tools.yaml", "config/operator/intents.yaml"),
            "notes": (),
            "details": {"workflows": workflows},
        }

    def _tool_continue_operator_task(self, plan: OperatorPlan, run_id: str, **_kwargs: Any) -> dict[str, Any]:
        session_state = self._load_json(self.session_state_path)
        requested_run_id = plan.intent.requested_run_id or session_state.get("last_run_id")
        if not requested_run_id:
            return {
                "status": "ok",
                "summary": "No prior operator run is available to continue yet.",
                "highlights": ("The operator ledger has no prior run context.",),
                "authority_paths": ("data/operator/runs/operator_runs.jsonl", "data/operator/state/session_state.json"),
                "notes": ("v0 continue is read-only and only rehydrates prior context.",),
                "details": {},
            }

        record_path = self.runs_dir / f"{requested_run_id}.json"
        previous_run = self._load_json(record_path)
        if not previous_run:
            return {
                "status": "ok",
                "summary": f"Run {requested_run_id} was not found in the operator run store.",
                "highlights": (f"Requested prior run: {requested_run_id}.",),
                "authority_paths": ("data/operator/runs/operator_runs.jsonl",),
                "notes": ("v0 continue does not reconstruct missing run artifacts.",),
                "details": {"continued_from": requested_run_id},
            }

        if requested_run_id == run_id:
            return {
                "status": "ok",
                "summary": "Continue skipped because there is no earlier operator run than the current invocation.",
                "highlights": ("The current run cannot continue itself.",),
                "authority_paths": ("data/operator/state/session_state.json",),
                "notes": ("Run a non-continue workflow first, then continue it.",),
                "details": {},
            }

        prior_summary = str(previous_run.get("summary", ""))
        prior_workflow = str(previous_run.get("workflow_id", "unknown"))
        prior_paths = tuple(previous_run.get("authority_paths", ()))
        return {
            "status": "ok",
            "summary": (
                f"Loaded prior run {requested_run_id} for workflow {prior_workflow}. "
                "v0 continue rehydrates prior intent, summary, and authority files but does not replay side effects."
            ),
            "highlights": (
                f"continued_from={requested_run_id}",
                f"prior_workflow={prior_workflow}",
                f"prior_summary={prior_summary}" if prior_summary else "The prior run had no summary.",
            ),
            "authority_paths": tuple(dict.fromkeys(("data/operator/runs/operator_runs.jsonl", *prior_paths))),
            "notes": ("Continue is intentionally read-only in v0.",),
            "details": {
                "continued_from": requested_run_id,
                "prior_run": {
                    "run_id": requested_run_id,
                    "workflow_id": prior_workflow,
                    "summary": prior_summary,
                    "authority_paths": list(prior_paths),
                },
            },
        }

    def _tool_telemetry_placeholder(self, plan: OperatorPlan, _run_id: str, **_kwargs: Any) -> dict[str, Any]:
        workflow = plan.workflow
        workflow_id = workflow.workflow_id if workflow else "telemetry_evaluation"
        summary = (
            f"{workflow_id} is scaffolded as a telemetry-ready placeholder. "
            "v0 defines the control surface, authority files, and future handoff seams, but it does not consume live telemetry yet."
        )
        return {
            "status": "ok",
            "summary": summary,
            "highlights": (
                "Future handoff anchor: config/spine_router.yaml.",
                "Future signal runtime seam: signal_agent/leviathan/interaction_signals/.",
                "Future interpretation seam: signal_agent/leviathan/interaction_signals/oil_bridge.py.",
            ),
            "authority_paths": workflow.authority_paths if workflow else (),
            "notes": workflow.notes if workflow else (),
            "details": {
                "workflow_id": workflow_id,
                "placeholder": True,
                "next_handoff": [
                    "config/spine_router.yaml",
                    "signal_agent/leviathan/interaction_signals/",
                    "signal_agent/leviathan/interaction_signals/oil_bridge.py",
                    "services/clipboard_intake_spine/",
                    "services/concept_formalization_spine/",
                ],
            },
        }

    def _tool_show_action_surfaces(self, plan: OperatorPlan, _run_id: str, **_kwargs: Any) -> dict[str, Any]:
        target_workflow = plan.target_workflow or self.registry.default_workflow_for_intent("inspect_system_state")
        if target_workflow is None:
            return {
                "status": "error",
                "summary": "The operator could not resolve a workflow to describe.",
                "highlights": (),
                "authority_paths": ("config/operator/workflows.yaml",),
                "notes": (),
                "details": {},
            }
        visible_paths = target_workflow.authority_paths[:4]
        summary = (
            f"Authority surfaces for {target_workflow.workflow_id}: "
            + ", ".join(visible_paths)
            + (", ..." if len(target_workflow.authority_paths) > len(visible_paths) else ".")
        )
        return {
            "status": "ok",
            "summary": summary,
            "highlights": (
                f"workflow={target_workflow.workflow_id}",
                f"mode={target_workflow.mode}",
                f"tool_chain={', '.join(target_workflow.tool_chain)}",
            ),
            "authority_paths": target_workflow.authority_paths,
            "notes": target_workflow.notes,
            "details": {
                "workflow_id": target_workflow.workflow_id,
                "authority_paths": list(target_workflow.authority_paths),
                "writes_paths": list(target_workflow.writes_paths),
                "tool_chain": list(target_workflow.tool_chain),
                "description": target_workflow.description,
            },
        }

    def _tool_record_state_append(
        self, plan: OperatorPlan, run_id: str, *, context_bundle: Any = None,
    ) -> dict[str, Any]:
        """
        Append one state record to the canonical artifact registry.

        This is the first real write-mode tool handler.  It exercises
        the full governed mutation path:
          gate → contract → context assembly → dispatch → record_state() → boundary evidence

        Inputs:
          plan.intent.requested_target      → artifact_id (fallback: run_id)
          plan.intent.requested_target_kind → target state (fallback: "captured")
          context_bundle                    → governed memory context (Phase 3A)
        """
        artifact_id = plan.intent.requested_target or run_id
        target_state = plan.intent.requested_target_kind or "captured"
        artifact_path = str(self.runs_dir / f"{run_id}.json")

        from shared.state_registry import record_state
        record_state(
            artifact_id=artifact_id,
            state=target_state,
            path=artifact_path,
        )

        details: dict[str, Any] = {
            "artifact_id": artifact_id,
            "state": target_state,
            "path": artifact_path,
        }
        if context_bundle is not None and hasattr(context_bundle, "to_audit_dict"):
            details["_context_assembly"] = context_bundle.to_audit_dict()

        return {
            "status": "ok",
            "summary": f"Recorded state '{target_state}' for artifact '{artifact_id}'.",
            "highlights": (
                f"data/state/artifact_registry.jsonl += {artifact_id}:{target_state}",
            ),
            "authority_paths": (
                "shared/state_registry.py",
                "data/state/artifact_registry.jsonl",
            ),
            "notes": (
                f"artifact_id={artifact_id}",
                f"state={target_state}",
            ),
            "details": details,
        }

    def _tool_intake_log_append(self, plan: OperatorPlan, run_id: str, **_kwargs: Any) -> dict[str, Any]:
        """
        Append one intake record to data/intake/intake.jsonl.

        This is the second real write-mode tool handler.  It proves
        the governance pattern generalizes to a different lifecycle file.

        Inputs:
          plan.intent.requested_target      → source_path (fallback: run_id)
          plan.intent.requested_target_kind → doc_type (fallback: "operator_probe")
        """
        source_path = plan.intent.requested_target or f"operator/{run_id}"
        doc_type = plan.intent.requested_target_kind or "operator_probe"
        timestamp = datetime.now(timezone.utc).isoformat()

        record = {
            "timestamp": timestamp,
            "source_path": source_path,
            "status": "success",
            "doc_type": doc_type,
            "mode": "OPERATOR",
            "operator_run_id": run_id,
            "source_sha256": hashlib.sha256(source_path.encode()).hexdigest(),
        }

        intake_path = self.repo_root / "data" / "intake" / "intake.jsonl"
        from app.utils.io_contract import append_jsonl_atomic
        append_jsonl_atomic(intake_path, record)

        return {
            "status": "ok",
            "summary": f"Appended intake record for '{source_path}' (type={doc_type}).",
            "highlights": (
                f"intake.jsonl += {source_path}:{doc_type}",
            ),
            "authority_paths": (
                "app/intake/intake.py",
                "data/intake/intake.jsonl",
            ),
            "notes": (
                f"source_path={source_path}",
                f"doc_type={doc_type}",
            ),
            "details": {
                "source_path": source_path,
                "doc_type": doc_type,
                "timestamp": timestamp,
                "operator_run_id": run_id,
            },
        }

    def _tool_session_state_overwrite(self, plan: OperatorPlan, run_id: str, **_kwargs: Any) -> dict[str, Any]:
        """
        Overwrite session_state.json with a governed transactional mutation.

        This is the first transactional tool handler.  It creates a new
        session state payload and overwrites the file atomically.

        The snapshot has already been captured by _dispatch_tool before
        this handler is called.
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        target = plan.intent.requested_target or "operator_transactional_probe"

        new_state = {
            "last_run_id": run_id,
            "last_workflow_id": plan.workflow.workflow_id if plan.workflow else None,
            "last_completed_at": timestamp,
            "last_run_record_path": str(self.runs_dir / f"{run_id}.json"),
            "transactional_mutation": True,
            "mutation_source": target,
        }

        state_path = self.repo_root / "data" / "operator" / "state" / "session_state.json"
        _atomic_write(state_path, _stable_json(new_state))

        return {
            "status": "ok",
            "summary": f"Overwrote session_state.json (transactional, source={target}).",
            "highlights": (
                f"session_state.json overwritten (transactional)",
            ),
            "authority_paths": (
                "data/operator/state/session_state.json",
            ),
            "notes": (
                f"mutation_type=overwrite",
                f"target={target}",
            ),
            "details": {
                "target": target,
                "timestamp": timestamp,
                "operator_run_id": run_id,
            },
        }

    def _load_yaml_relative(self, relative_path: str) -> dict[str, Any]:
        path = self.repo_root / relative_path
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    def _load_json(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_run_record(self, plan: OperatorPlan, result: OperatorRunResult) -> None:
        record_path = Path(result.run_record_path)
        is_compound = bool(plan.workflow and plan.workflow.workflow_steps)
        payload = {
            "run_id": result.run_id,
            "command_text": result.command_text,
            "status": result.status,
            "started_at": result.started_at,
            "completed_at": result.completed_at,
            "intent_id": result.intent_id,
            "workflow_id": result.workflow_id,
            "target_workflow_id": result.target_workflow_id,
            "plan_status": plan.status,
            "summary": result.summary,
            "highlights": list(result.highlights),
            "authority_paths": list(result.authority_paths),
            "notes": list(result.notes),
            "continued_from": result.continued_from,
        }

        tool_results_list = [
            {
                "tool_id": execution.tool_id,
                "status": execution.status,
                "summary": execution.summary,
                "highlights": list(execution.highlights),
                "authority_paths": list(execution.authority_paths),
                "notes": list(execution.notes),
                "details": execution.details,
                "declared_reads": list(
                    (self.registry.tools.get(execution.tool_id).reads
                     if self.registry.tools.get(execution.tool_id) else ())
                ),
                "declared_writes": list(
                    (self.registry.tools.get(execution.tool_id).writes
                     if self.registry.tools.get(execution.tool_id) else ())
                ),
                "verification_status": execution.details.get(
                    "_tool_contract", {}
                ).get("verification_status", "undeclared"),
                "consistency_status": execution.details.get(
                    "_consistency_status", "unknown",
                ),
            }
            for execution in result.tool_results
        ]

        if is_compound:
            payload["compound"] = True
            steps = []
            for tr in tool_results_list:
                step_index = tr["details"].get("step_index")
                steps.append({
                    "step_index": step_index,
                    "workflow_id": tr["details"].get("workflow_id", "unknown"),
                    "status": tr["status"],
                    "tool_result": tr
                })
            payload["steps"] = steps
        else:
            payload["steps"] = [step.tool_id for step in plan.steps]
            payload["tool_results"] = tool_results_list

        _atomic_write(record_path, _stable_json(payload))

    def _append_ledger_entry(self, result: OperatorRunResult) -> None:
        _append_jsonl(
            self.ledger_path,
            {
                "run_id": result.run_id,
                "started_at": result.started_at,
                "completed_at": result.completed_at,
                "status": result.status,
                "intent_id": result.intent_id,
                "workflow_id": result.workflow_id,
                "target_workflow_id": result.target_workflow_id,
                "summary": result.summary,
                "authority_paths": list(result.authority_paths),
                "continued_from": result.continued_from,
                "run_record_path": result.run_record_path,
            },
        )

    def _write_session_state(self, result: OperatorRunResult) -> None:
        payload = {
            "last_run_id": result.run_id,
            "last_workflow_id": result.workflow_id,
            "last_completed_at": result.completed_at,
            "last_run_record_path": result.run_record_path,
        }
        _atomic_write(self.session_state_path, _stable_json(payload))
