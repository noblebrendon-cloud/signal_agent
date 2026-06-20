from __future__ import annotations

from importlib import import_module
from pathlib import Path


def test_operator_required_runtime_modules_import_from_committed_source() -> None:
    intent = import_module("signal_agent.operator.intent")
    planner = import_module("signal_agent.operator.planner")
    registry = import_module("signal_agent.operator.registry")
    capture_routing_status = import_module("signal_agent.operator.capture_routing_status")
    routing_queue_backlog = import_module("signal_agent.operator.routing_queue_backlog")
    routing_lineage_drilldown = import_module("signal_agent.operator.routing_lineage_drilldown")
    lineage_status = import_module("signal_agent.content.lineage_status")
    runtime = import_module("signal_agent.operator.runtime")

    assert hasattr(intent, "IntentParser")
    assert hasattr(intent, "ParsedIntent")
    assert hasattr(planner, "OperatorPlanner")
    assert hasattr(planner, "OperatorPlan")
    assert hasattr(planner, "PlanStep")
    assert hasattr(registry, "OperatorRegistry")
    assert hasattr(registry, "ToolDefinition")
    assert hasattr(registry, "WorkflowDefinition")
    assert hasattr(capture_routing_status, "build_capture_routing_status_tool_result")
    assert hasattr(routing_queue_backlog, "build_routing_queue_backlog_tool_result")
    assert hasattr(routing_lineage_drilldown, "build_routing_lineage_drilldown_tool_result")
    assert hasattr(lineage_status, "load_content_lifecycle_view")
    assert hasattr(runtime, "OperatorRuntime")


def test_operator_registry_config_is_committed_and_loadable() -> None:
    registry = import_module("signal_agent.operator.registry")
    repo_root = Path(__file__).resolve().parents[1]

    assert (repo_root / "config" / "operator" / "intents.yaml").exists()
    assert (repo_root / "config" / "operator" / "tools.yaml").exists()
    assert (repo_root / "config" / "operator" / "workflows.yaml").exists()

    loaded = registry.OperatorRegistry.load(repo_root)

    assert loaded.intents
    assert loaded.tools
    assert loaded.workflows
