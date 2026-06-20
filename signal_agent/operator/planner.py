from __future__ import annotations

from dataclasses import dataclass

from .intent import ParsedIntent
from .registry import OperatorRegistry, WorkflowDefinition


@dataclass(frozen=True)
class PlanStep:
    tool_id: str
    description: str


@dataclass(frozen=True)
class OperatorPlan:
    intent: ParsedIntent
    workflow: WorkflowDefinition | None
    target_workflow: WorkflowDefinition | None
    steps: tuple[PlanStep, ...]
    status: str
    notes: tuple[str, ...]


class OperatorPlanner:
    def __init__(self, registry: OperatorRegistry) -> None:
        self.registry = registry

    def plan(self, intent: ParsedIntent) -> OperatorPlan:
        notes = list(intent.notes)
        workflow: WorkflowDefinition | None = None
        target_workflow: WorkflowDefinition | None = None

        if intent.intent_id == "unknown":
            return OperatorPlan(
                intent=intent,
                workflow=None,
                target_workflow=None,
                steps=(),
                status="unsupported",
                notes=tuple(notes),
            )

        if intent.intent_id == "run_named_workflow":
            target_workflow = self.registry.resolve_workflow_name(intent.requested_workflow)
            workflow = target_workflow
            if workflow is None:
                notes.append(f"Unknown workflow requested: {intent.requested_workflow}")
                return OperatorPlan(
                    intent=intent,
                    workflow=None,
                    target_workflow=None,
                    steps=(),
                    status="error",
                    notes=tuple(notes),
                )
        elif intent.intent_id == "show_action_surfaces":
            workflow = self.registry.default_workflow_for_intent(intent.intent_id)
            target_workflow = self.registry.resolve_workflow_name(intent.requested_workflow)
        elif intent.intent_id == "evaluate_telemetry_placeholder":
            target_workflow = self.registry.resolve_workflow_name(intent.requested_workflow) or self.registry.resolve_workflow_name("telemetry_evaluation")
            workflow = target_workflow
        else:
            workflow = self.registry.default_workflow_for_intent(intent.intent_id)
            target_workflow = workflow

        if workflow is None:
            notes.append(f"No workflow is registered for intent: {intent.intent_id}")
            return OperatorPlan(
                intent=intent,
                workflow=None,
                target_workflow=target_workflow,
                steps=(),
                status="error",
                notes=tuple(notes),
            )

        steps = tuple(
            PlanStep(
                tool_id=tool_id,
                description=self.registry.tools.get(tool_id).description if self.registry.tools.get(tool_id) else tool_id,
            )
            for tool_id in workflow.tool_chain
        )
        return OperatorPlan(
            intent=intent,
            workflow=workflow,
            target_workflow=target_workflow,
            steps=steps,
            status="ready",
            notes=tuple(notes),
        )
