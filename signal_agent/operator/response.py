from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .planner import OperatorPlan
from .registry import OperatorRegistry
from .runtime import OperatorRunResult


@dataclass(frozen=True)
class ResponseSection:
    title: str
    lines: tuple[str, ...]


@dataclass(frozen=True)
class OperatorResponse:
    run_id: str
    status: str
    summary: str
    sections: tuple[ResponseSection, ...]
    notes: tuple[str, ...]
    ledger_path: str

    def to_text(self) -> str:
        lines = [
            f"run_id={self.run_id}",
            f"status={self.status}",
            f"summary={self.summary}",
        ]
        for section in self.sections:
            lines.append("")
            lines.append(f"{section.title}:")
            for line in section.lines:
                lines.append(f"- {line}")
        if self.notes:
            lines.append("")
            lines.append("Notes:")
            for note in self.notes:
                lines.append(f"- {note}")
        lines.append("")
        lines.append(f"ledger={self.ledger_path}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "summary": self.summary,
            "sections": [
                {
                    "title": section.title,
                    "lines": list(section.lines),
                }
                for section in self.sections
            ],
            "notes": list(self.notes),
            "ledger_path": self.ledger_path,
        }


def build_operator_response(
    plan: OperatorPlan,
    result: OperatorRunResult,
    registry: OperatorRegistry,
) -> OperatorResponse:
    understood_lines = [
        f"intent={result.intent_id}",
        f"workflow={result.workflow_id or 'none'}",
    ]
    if result.target_workflow_id and result.target_workflow_id != result.workflow_id:
        understood_lines.append(f"target_workflow={result.target_workflow_id}")
    if plan.intent.requested_action:
        understood_lines.append(f"requested_action={plan.intent.requested_action}")
    if plan.intent.requested_target:
        understood_lines.append(f"requested_target={plan.intent.requested_target}")
    if plan.intent.requested_target_kind:
        understood_lines.append(f"requested_target_kind={plan.intent.requested_target_kind}")
    if result.continued_from:
        understood_lines.append(f"continued_from={result.continued_from}")

    sections = [ResponseSection(title="Understood", lines=tuple(understood_lines))]
    if plan.steps:
        sections.append(
            ResponseSection(
                title="Plan",
                lines=tuple(f"{step.tool_id}: {step.description}" for step in plan.steps),
            )
        )
    if result.highlights:
        sections.append(ResponseSection(title="Highlights", lines=result.highlights))
    if result.authority_paths:
        sections.append(ResponseSection(title="Relevant Files", lines=result.authority_paths))

    notes = list(result.notes)
    if result.status in {"unsupported", "error"}:
        notes.append("Supported workflows: " + ", ".join(sorted(registry.workflows.keys())))

    return OperatorResponse(
        run_id=result.run_id,
        status=result.status,
        summary=result.summary,
        sections=tuple(sections),
        notes=tuple(dict.fromkeys(note for note in notes if note)),
        ledger_path=result.ledger_path,
    )
