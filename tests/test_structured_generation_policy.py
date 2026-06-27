from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel

from signal_agent.structured_generation import FakeStructuredGenerator, StructuredGenerationError
from signal_agent.structured_generation.outlines_adapter import (
    OutlinesStructuredGenerator,
    _openai_no_retry_kwargs,
)
from signal_agent.structured_generation.policy import (
    GenerationBudgetError,
    GenerationBudgetPolicy,
    LiveGenerationAuthorizationError,
    ManualLiveGenerationAuthorization,
    MAX_OUTPUT_TOKENS,
)


class ExampleResponse(BaseModel):
    name: str
    score: int


class RecordingOutlinesModel:
    def __init__(self, response: object | None = None, *, fail: bool = False) -> None:
        self.calls = 0
        self.kwargs: dict[str, object] | None = None
        self.response = response or ExampleResponse(name="alpha", score=7)
        self.fail = fail

    def __call__(self, prompt: str, schema: type[BaseModel], **kwargs: object) -> object:
        del prompt, schema
        self.calls += 1
        self.kwargs = dict(kwargs)
        if self.fail:
            raise RuntimeError("provider failed")
        return self.response


def _manual_auth() -> ManualLiveGenerationAuthorization:
    return ManualLiveGenerationAuthorization.manual_smoke()


def test_fake_generation_still_works_without_live_authorization() -> None:
    generator = FakeStructuredGenerator(ExampleResponse(name="alpha", score=7))

    result = generator.generate("return an example response", ExampleResponse)

    assert result.value == ExampleResponse(name="alpha", score=7)
    assert result.receipt.provider == "fake"


def test_live_adapter_rejects_missing_authorization_before_provider_call() -> None:
    model = RecordingOutlinesModel()
    generator = OutlinesStructuredGenerator(
        provider="openai",
        model="test-model",
        outlines_model=model,
    )

    with pytest.raises(LiveGenerationAuthorizationError):
        generator.generate("return an example response", ExampleResponse)

    assert model.calls == 0


def test_live_adapter_rejects_non_manual_authorization_before_provider_call() -> None:
    model = RecordingOutlinesModel()
    generator = OutlinesStructuredGenerator(
        provider="openai",
        model="test-model",
        outlines_model=model,
    )

    with pytest.raises(LiveGenerationAuthorizationError):
        generator.generate(
            "return an example response",
            ExampleResponse,
            authorization=ManualLiveGenerationAuthorization(origin="daemon"),
        )

    assert model.calls == 0


def test_oversized_prompt_fails_before_provider_call() -> None:
    model = RecordingOutlinesModel()
    generator = OutlinesStructuredGenerator(
        provider="openai",
        model="test-model",
        outlines_model=model,
    )

    with pytest.raises(GenerationBudgetError, match="prompt_utf8_bytes_exceeds_limit"):
        generator.generate(
            "x" * 12,
            ExampleResponse,
            authorization=_manual_auth(),
            budget_policy=GenerationBudgetPolicy(max_prompt_utf8_bytes=10),
        )

    assert model.calls == 0


def test_over_budget_configured_cost_fails_before_provider_call() -> None:
    model = RecordingOutlinesModel()
    generator = OutlinesStructuredGenerator(
        provider="openai",
        model="test-model",
        outlines_model=model,
    )

    with pytest.raises(GenerationBudgetError, match="estimated_max_request_cost_exceeds_cap"):
        generator.generate(
            "return an example response",
            ExampleResponse,
            authorization=_manual_auth(),
            budget_policy=GenerationBudgetPolicy(
                max_output_tokens=MAX_OUTPUT_TOKENS,
                input_usd_per_million_tokens="1000",
                output_usd_per_million_tokens="1000",
                max_request_usd="0.000001",
            ),
        )

    assert model.calls == 0


def test_within_budget_preflight_sets_upper_bound_metadata() -> None:
    model = RecordingOutlinesModel()
    generator = OutlinesStructuredGenerator(
        provider="openai",
        model="test-model",
        outlines_model=model,
    )

    result = generator.generate(
        "return an example response",
        ExampleResponse,
        authorization=_manual_auth(),
        budget_policy=GenerationBudgetPolicy(
            max_output_tokens=64,
            input_usd_per_million_tokens="0.10",
            output_usd_per_million_tokens="0.20",
            max_request_usd="1.00",
        ),
    )

    assert result.receipt.prompt_utf8_bytes == len("return an example response".encode("utf-8"))
    assert result.receipt.estimated_prompt_tokens_upper_bound == result.receipt.prompt_utf8_bytes
    assert result.receipt.maximum_output_tokens == 64
    assert result.receipt.estimated_max_request_cost_usd is not None
    assert result.receipt.cost_status == "estimated_max_available"
    assert result.receipt.actual_total_tokens is None


def test_missing_rate_configuration_leaves_monetary_cost_unavailable() -> None:
    model = RecordingOutlinesModel()
    generator = OutlinesStructuredGenerator(
        provider="openai",
        model="test-model",
        outlines_model=model,
    )

    result = generator.generate(
        "return an example response",
        ExampleResponse,
        authorization=_manual_auth(),
        budget_policy=GenerationBudgetPolicy(max_output_tokens=64),
    )

    assert result.receipt.estimated_max_request_cost_usd is None
    assert result.receipt.configured_input_rate_usd_per_million is None
    assert result.receipt.configured_output_rate_usd_per_million is None
    assert result.receipt.cost_status == "unavailable"


def test_provider_failure_is_attempted_once_only() -> None:
    model = RecordingOutlinesModel(fail=True)
    generator = OutlinesStructuredGenerator(
        provider="openai",
        model="test-model",
        outlines_model=model,
    )

    with pytest.raises(Exception, match="structured generation failed"):
        generator.generate(
            "return an example response",
            ExampleResponse,
            authorization=_manual_auth(),
        )

    assert model.calls == 1


def test_openai_compatible_clients_are_configured_with_zero_retries() -> None:
    class OpenAICompatibleClient:
        def __init__(self, *, max_retries: int = 2) -> None:
            self.max_retries = max_retries

    assert _openai_no_retry_kwargs(OpenAICompatibleClient) == {"max_retries": 0}


def test_output_token_cap_is_passed_to_openai_compatible_model() -> None:
    model = RecordingOutlinesModel()
    generator = OutlinesStructuredGenerator(
        provider="openai",
        model="test-model",
        outlines_model=model,
    )

    result = generator.generate(
        "return an example response",
        ExampleResponse,
        authorization=_manual_auth(),
        budget_policy=GenerationBudgetPolicy(max_output_tokens=33),
    )

    assert result.receipt.maximum_output_tokens == 33
    assert model.kwargs == {"max_completion_tokens": 33}


def test_output_token_cap_is_passed_to_vllm_model() -> None:
    model = RecordingOutlinesModel()
    generator = OutlinesStructuredGenerator(
        provider="vllm",
        model="test-model",
        outlines_model=model,
    )

    result = generator.generate(
        "return an example response",
        ExampleResponse,
        authorization=_manual_auth(),
        budget_policy=GenerationBudgetPolicy(max_output_tokens=33),
    )

    assert result.receipt.maximum_output_tokens == 33
    assert model.kwargs == {"max_tokens": 33}


def test_ollama_fails_closed_until_retry_and_output_limits_are_verified() -> None:
    model = RecordingOutlinesModel()
    generator = OutlinesStructuredGenerator(
        provider="ollama",
        model="test-model",
        outlines_model=model,
    )

    with pytest.raises(StructuredGenerationError, match="Ollama live structured generation is disabled"):
        generator.generate(
            "return an example response",
            ExampleResponse,
            authorization=_manual_auth(),
        )

    assert model.calls == 0


def test_automated_paths_do_not_import_live_generation_activation() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    forbidden = (
        "OutlinesStructuredGenerator",
        "create_structured_generator",
        "ManualLiveGenerationAuthorization",
    )
    scanned_roots = ("app", "signal_agent", "services", "scripts", "tools")
    violations: list[str] = []
    for root_name in scanned_roots:
        root = repo_root / root_name
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            relative = path.relative_to(repo_root)
            if relative.parts[:2] == ("signal_agent", "structured_generation"):
                continue
            if relative.as_posix() == "tools/smoke_structured_transition.py":
                continue
            source = path.read_text(encoding="utf-8", errors="ignore")
            for token in forbidden:
                if token in source:
                    violations.append(f"{relative}:{token}")

    assert violations == []
