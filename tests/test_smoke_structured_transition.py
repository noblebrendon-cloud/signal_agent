from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

from pydantic import BaseModel

from signal_agent.laviathon.schemas import TransitionProposal
from signal_agent.structured_generation import FakeStructuredGenerator
from signal_agent.structured_generation.policy import (
    GenerationBudgetPolicy,
    ManualLiveGenerationAuthorization,
)
from tools import smoke_structured_transition as smoke


FORBIDDEN_MODULES = (
    "signal_agent.laviathon.transition_proposals",
    "signal_agent.laviathon.structured_transition_service",
    "signal_agent.formal_governance",
    "app.spine_observability.laviathon_store",
    "app.spine_observability.laviathon",
    "shared.state_registry",
)


class OtherResponse(BaseModel):
    label: str


class RecordingGenerator:
    def __init__(self, proposal: TransitionProposal) -> None:
        self._generator = FakeStructuredGenerator(proposal)
        self.prompt: str | None = None
        self.schema: type[BaseModel] | None = None

    def generate(
        self,
        prompt: str,
        schema: type[BaseModel],
        **kwargs: object,
    ):
        self.prompt = prompt
        self.schema = schema
        self.kwargs = kwargs
        return self._generator.generate(prompt, schema)


class FailingGenerator:
    def generate(self, prompt: str, schema: type[BaseModel], **_kwargs: object):
        del prompt, schema
        raise RuntimeError("provider failed with api_key=sk-test-secret")


def _proposal(**overrides: object) -> TransitionProposal:
    payload: dict[str, object] = {
        "entity_id": smoke.SMOKE_ENTITY_ID,
        "observed_state": smoke.SMOKE_OBSERVED_STATE,
        "recommended_route": "manual_review",
        "evidence_ids": list(smoke.SMOKE_EVIDENCE_IDS),
        "rationale": "Synthetic smoke evidence is sufficient for a schema-only proposal.",
        "uncertainty_notes": "No real facts are available in this smoke test.",
        "requires_human_review": True,
    }
    payload.update(overrides)
    return TransitionProposal.model_validate(payload)


def test_smoke_prompt_uses_only_synthetic_inputs() -> None:
    prompt = smoke.build_smoke_prompt()

    assert smoke.SMOKE_ENTITY_ID in prompt
    assert "smoke-evidence-001" in prompt
    assert "smoke-evidence-002" in prompt
    assert "admit, blocked_duplicate, manual_review" in prompt
    assert "proposal only, not a final decision" in prompt
    assert "uncertainty_notes" in prompt
    assert "ledger content" in prompt


def test_smoke_harness_requests_transition_proposal_schema() -> None:
    generator = RecordingGenerator(_proposal())

    exit_code, payload = smoke.run_smoke_test(generator)

    assert exit_code == 0
    assert generator.schema is TransitionProposal
    assert generator.prompt is not None
    assert isinstance(generator.kwargs["authorization"], ManualLiveGenerationAuthorization)
    assert isinstance(generator.kwargs["budget_policy"], GenerationBudgetPolicy)
    assert payload["status"] == "validated"


def test_fake_generator_produces_json_safe_validated_output() -> None:
    exit_code, payload = smoke.run_smoke_test(FakeStructuredGenerator(_proposal()))

    assert exit_code == 0
    assert json.loads(json.dumps(payload, sort_keys=True)) == payload
    assert payload["proposal"]["entity_id"] == smoke.SMOKE_ENTITY_ID
    assert payload["proposal"]["evidence_ids"] == list(smoke.SMOKE_EVIDENCE_IDS)
    assert payload["generation_receipt"]["schema_name"] == "TransitionProposal"
    assert "maximum_output_tokens" in payload["generation_receipt"]
    assert "cost_status" in payload["generation_receipt"]


def test_fake_generator_failure_produces_safe_failure_payload() -> None:
    exit_code, payload = smoke.run_smoke_test(FailingGenerator())

    assert exit_code == 1
    assert json.loads(json.dumps(payload, sort_keys=True)) == payload
    assert payload["status"] == "failed"
    assert payload["error_type"] == "RuntimeError"
    assert "sk-test-secret" not in payload["message"]
    assert "[redacted]" in payload["message"]


def test_smoke_script_does_not_import_forbidden_modules() -> None:
    source_path = Path(smoke.__file__).resolve()
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_modules.add(node.module)

    for forbidden in FORBIDDEN_MODULES:
        assert forbidden not in imported_modules


def test_smoke_run_imports_no_forbidden_modules_and_writes_no_files(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    before_modules = set(sys.modules)

    exit_code, payload = smoke.run_smoke_test(FakeStructuredGenerator(_proposal()))

    assert exit_code == 0
    assert payload["status"] == "validated"
    new_modules = set(sys.modules) - before_modules
    for forbidden in FORBIDDEN_MODULES:
        assert forbidden not in new_modules
    assert list(tmp_path.iterdir()) == []
