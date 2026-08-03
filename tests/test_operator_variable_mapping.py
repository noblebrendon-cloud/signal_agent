import json
from pathlib import Path

from signal_agent.operator.registry import OperatorRegistry
from signal_agent.operator.runtime import OperatorRuntime
from signal_agent.operator.planner import OperatorPlan
from signal_agent.operator.intent import ParsedIntent
from unittest.mock import patch


def _setup_fake_root(tmp_path: Path) -> tuple[Path, OperatorRegistry, OperatorRuntime]:
    import shutil
    repo_root = Path(__file__).parent.parent
    fake_root = tmp_path / "fake_repo"
    
    (fake_root / "config" / "operator").mkdir(parents=True)
    shutil.copytree(repo_root / "config" / "operator", fake_root / "config" / "operator", dirs_exist_ok=True)
    
    registry = OperatorRegistry.load(fake_root)
    runtime = OperatorRuntime(registry, runs_dir=fake_root / "runs", state_dir=fake_root / "state")
    return fake_root, registry, runtime


def _make_plan(registry: OperatorRegistry, target: str | None = None, command: str = "run test") -> OperatorPlan:
    from signal_agent.operator.planner import PlanStep
    
    workflow = registry.workflows["intake_append_and_stage_session"]
    intent = ParsedIntent(
        command_text=command,
        intent_id=workflow.intent_ids[0] if workflow.intent_ids else "unknown",
        confidence=1.0,
        requested_target=target
    )
    
    return OperatorPlan(
        status="ready",
        intent=intent,
        workflow=workflow,
        target_workflow=workflow,
        notes=(),
        steps=tuple(PlanStep(tool_id=t, description="") for t in workflow.tool_chain)
    )


def test_valid_mapping(tmp_path: Path) -> None:
    fake_root, registry, runtime = _setup_fake_root(tmp_path)
    plan = _make_plan(registry, target="target_VALID")
    
    # Pre-assertions
    intake_path = fake_root / "data" / "intake" / "intake.jsonl"
    
    result = runtime.execute(plan)
    
    assert result.status == "ok"
    # Verify Step 1
    assert intake_path.exists()
    intake_data = json.loads(intake_path.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert intake_data["source_path"] == "target_VALID"
    
    # 2. Session State Step Executed
    run_record_path = fake_root / "runs" / f"{result.run_id}.json"
    run_record = json.loads(run_record_path.read_text(encoding="utf-8"))
    
    workflows_executed = [s["workflow_id"] for s in run_record.get("steps", [])]
    assert "session_state_update" in workflows_executed
    
    step_2 = run_record["steps"][1]["tool_result"]
    assert step_2["details"]["target"] == "target_VALID"


def test_missing_variable(tmp_path: Path) -> None:
    fake_root, registry, runtime = _setup_fake_root(tmp_path)
    # Provide no requested_target, so it will evaluate to None, thus failing closed
    plan = _make_plan(registry, target=None)
    
    result = runtime.execute(plan)
    
    assert result.status == "rejected"
    
    run_record_path = fake_root / "runs" / f"{result.run_id}.json"
    run_record = json.loads(run_record_path.read_text(encoding="utf-8"))
    
    steps = run_record.get("steps", [])
    assert len(steps) == 1
    
    step_1 = steps[0]
    assert step_1["status"] == "rejected"
    assert step_1["tool_result"]["details"]["_consistency_status"] == "rejected"
    assert step_1["tool_result"]["details"]["rejection_reason"] == "missing_required_input"
    assert "missing_required_input:" in step_1["tool_result"]["details"]["map_error"]


def test_invalid_variable(tmp_path: Path) -> None:
    fake_root, registry, runtime = _setup_fake_root(tmp_path)
    
    # Hotpatch the input_map to contain a totally unknown field
    import dataclasses
    workflow = registry.workflows["intake_append_and_stage_session"]
    patched_steps = []
    from signal_agent.operator.registry import WorkflowStepDefinition
    for s in workflow.workflow_steps:
        patched_steps.append(WorkflowStepDefinition(s.workflow_id, {"requested_target": "$invalid_field_123"}))
        
    registry.workflows["intake_append_and_stage_session"] = dataclasses.replace(
        workflow, workflow_steps=tuple(patched_steps)
    )
    
    plan = _make_plan(registry, target="not_used")
    result = runtime.execute(plan)
    
    assert result.status == "rejected"
    run_record_path = fake_root / "runs" / f"{result.run_id}.json"
    run_record = json.loads(run_record_path.read_text(encoding="utf-8"))
    
    step_1 = run_record["steps"][0]
    assert step_1["status"] == "rejected"
    assert "not in ParsedIntent" in step_1["tool_result"]["details"]["map_error"]


def test_literal_value(tmp_path: Path) -> None:
    fake_root, registry, runtime = _setup_fake_root(tmp_path)
    
    # Hotpatch the input_map to use a literal target
    import dataclasses
    workflow = registry.workflows["intake_append_and_stage_session"]
    patched_steps = []
    from signal_agent.operator.registry import WorkflowStepDefinition
    for s in workflow.workflow_steps:
        patched_steps.append(WorkflowStepDefinition(s.workflow_id, {"requested_target": "LITERAL_BOB"}))
        
    registry.workflows["intake_append_and_stage_session"] = dataclasses.replace(
        workflow, workflow_steps=tuple(patched_steps)
    )
    
    plan = _make_plan(registry, target="target_VALID")
    result = runtime.execute(plan)
    
    assert result.status == "ok"
    
    run_record_path = fake_root / "runs" / f"{result.run_id}.json"
    run_record = json.loads(run_record_path.read_text(encoding="utf-8"))
    
    assert run_record["steps"][0]["tool_result"]["details"]["source_path"] == "LITERAL_BOB"
    assert run_record["steps"][1]["tool_result"]["details"]["target"] == "LITERAL_BOB"


def test_no_leakage(tmp_path: Path) -> None:
    # A step should not receive field if it's not mapped
    fake_root, registry, runtime = _setup_fake_root(tmp_path)
    
    workflow = registry.workflows["intake_append_and_stage_session"]
    intent = ParsedIntent(
        command_text="test command",
        intent_id=workflow.intent_ids[0] if workflow.intent_ids else "unknown",
        confidence=1.0,
        requested_target="target_A",
        requested_target_kind="SECRET_KIND"  # This is NOT mapped in workflows.yaml!
    )
    
    from signal_agent.operator.planner import PlanStep
    plan = OperatorPlan(
        status="ready",
        intent=intent,
        workflow=workflow,
        target_workflow=workflow,
        notes=(),
        steps=tuple(PlanStep(tool_id=t, description="") for t in workflow.tool_chain)
    )
    
    # Intercept tool dispatch to observe the intent inside the loop
    observed_intent = None
    original_dispatch = runtime._dispatch_tool
    
    def mock_dispatch(tool_id, sub_plan, run_id, *, context_bundle=None):
        nonlocal observed_intent
        observed_intent = sub_plan.intent
        return original_dispatch(
            tool_id,
            sub_plan,
            run_id,
            context_bundle=context_bundle,
        )
        
    with patch.object(runtime, '_dispatch_tool', side_effect=mock_dispatch):
        runtime.execute(plan)
        
    assert observed_intent is not None
    assert observed_intent.requested_target == "target_A"
    assert observed_intent.requested_target_kind is None  # Should be None because it wasn't mapped!

    # Test E: Intent Immutability Assurance
    # Original ParsedIntent must not be altered
    assert intent.requested_target_kind == "SECRET_KIND"
