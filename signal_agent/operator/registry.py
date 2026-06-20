from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


def normalize_text(value: str) -> str:
    return " ".join(value.strip().lower().replace("-", " ").split())


def _string_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value)
    raise ValueError(f"Expected a string or sequence of strings, got {type(value)!r}")


def _load_yaml_document(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Operator registry file not found: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Operator registry root must be a mapping: {path}")
    return payload


@dataclass(frozen=True)
class IntentDefinition:
    intent_id: str
    description: str
    default_workflow: str | None
    match_phrases: tuple[str, ...]
    examples: tuple[str, ...]


@dataclass(frozen=True)
class ToolDefinition:
    tool_id: str
    description: str
    kind: str
    reads: tuple[str, ...]
    writes: tuple[str, ...]
    mutation_type: str | None = None
    transactional: bool = False


@dataclass(frozen=True)
class WorkflowStepDefinition:
    workflow_id: str
    input_map: dict[str, str]


@dataclass(frozen=True)
class WorkflowDefinition:
    workflow_id: str
    description: str
    intent_ids: tuple[str, ...]
    tool_chain: tuple[str, ...]
    aliases: tuple[str, ...]
    authority_paths: tuple[str, ...]
    writes_paths: tuple[str, ...]
    notes: tuple[str, ...]
    mode: str = "read_only"
    resumable: bool = False
    transition_context: dict[str, Any] | None = None
    workflow_steps: tuple[WorkflowStepDefinition, ...] = ()

    @property
    def is_placeholder(self) -> bool:
        return self.mode == "placeholder"


@dataclass(frozen=True)
class OperatorRegistry:
    repo_root: Path
    intents: dict[str, IntentDefinition]
    tools: dict[str, ToolDefinition]
    workflows: dict[str, WorkflowDefinition]
    _workflow_lookup: dict[str, str]

    @classmethod
    def load(cls, repo_root: Path) -> "OperatorRegistry":
        repo_root = repo_root.resolve()
        config_root = repo_root / "config" / "operator"
        intents_doc = _load_yaml_document(config_root / "intents.yaml")
        tools_doc = _load_yaml_document(config_root / "tools.yaml")
        workflows_doc = _load_yaml_document(config_root / "workflows.yaml")

        intents: dict[str, IntentDefinition] = {}
        for intent_id, payload in (intents_doc.get("intents") or {}).items():
            if not isinstance(payload, dict):
                raise ValueError(f"Intent definition must be a mapping: {intent_id}")
            intents[str(intent_id)] = IntentDefinition(
                intent_id=str(intent_id),
                description=str(payload.get("description", "")),
                default_workflow=str(payload["default_workflow"]) if payload.get("default_workflow") else None,
                match_phrases=_string_tuple(payload.get("match_phrases")),
                examples=_string_tuple(payload.get("examples")),
            )

        tools: dict[str, ToolDefinition] = {}
        for tool_id, payload in (tools_doc.get("tools") or {}).items():
            if not isinstance(payload, dict):
                raise ValueError(f"Tool definition must be a mapping: {tool_id}")
            tools[str(tool_id)] = ToolDefinition(
                tool_id=str(tool_id),
                description=str(payload.get("description", "")),
                kind=str(payload.get("kind", "inspector")),
                reads=_string_tuple(payload.get("reads")),
                writes=_string_tuple(payload.get("writes")),
                mutation_type=str(payload["mutation_type"]) if payload.get("mutation_type") else None,
                transactional=bool(payload.get("transactional", False)),
            )

        workflows: dict[str, WorkflowDefinition] = {}
        workflow_lookup: dict[str, str] = {}
        for workflow_id, payload in (workflows_doc.get("workflows") or {}).items():
            if not isinstance(payload, dict):
                raise ValueError(f"Workflow definition must be a mapping: {workflow_id}")
            raw_transition = payload.get("transition_context")
            transition_ctx = dict(raw_transition) if isinstance(raw_transition, dict) else None
            raw_steps = payload.get("workflow_steps", [])
            if not isinstance(raw_steps, list):
                raw_steps = []

            parsed_steps = []
            for step in raw_steps:
                if isinstance(step, str):
                    parsed_steps.append(WorkflowStepDefinition(workflow_id=step, input_map={}))
                elif isinstance(step, dict):
                    parsed_steps.append(WorkflowStepDefinition(
                        workflow_id=str(step.get("workflow_id", "")),
                        input_map={str(k): str(v) for k, v in step.get("input_map", {}).items()}
                    ))

            workflow = WorkflowDefinition(
                workflow_id=str(workflow_id),
                description=str(payload.get("description", "")),
                intent_ids=_string_tuple(payload.get("intent_ids")),
                tool_chain=_string_tuple(payload.get("tool_chain")),
                aliases=_string_tuple(payload.get("aliases")),
                authority_paths=_string_tuple(payload.get("authority_paths")),
                writes_paths=_string_tuple(payload.get("writes_paths")),
                notes=_string_tuple(payload.get("notes")),
                mode=str(payload.get("mode", "read_only")),
                resumable=bool(payload.get("resumable", False)),
                transition_context=transition_ctx,
                workflow_steps=tuple(parsed_steps),
            )
            workflows[workflow.workflow_id] = workflow
            for alias in (workflow.workflow_id, *workflow.aliases):
                workflow_lookup[normalize_text(alias)] = workflow.workflow_id

        return cls(
            repo_root=repo_root,
            intents=intents,
            tools=tools,
            workflows=workflows,
            _workflow_lookup=workflow_lookup,
        )

    def default_workflow_for_intent(self, intent_id: str) -> WorkflowDefinition | None:
        intent = self.intents.get(intent_id)
        if intent is None or intent.default_workflow is None:
            return None
        return self.workflows.get(intent.default_workflow)

    def resolve_workflow_name(self, candidate: str | None) -> WorkflowDefinition | None:
        if not candidate:
            return None
        workflow_id = self._workflow_lookup.get(normalize_text(candidate))
        if workflow_id is None:
            return None
        return self.workflows.get(workflow_id)

    def find_workflow_mention(self, text: str) -> WorkflowDefinition | None:
        normalized = normalize_text(text)
        for alias, workflow_id in sorted(self._workflow_lookup.items(), key=lambda item: len(item[0]), reverse=True):
            if alias and alias in normalized:
                return self.workflows[workflow_id]
        return None
