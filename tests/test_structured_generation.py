from __future__ import annotations

import pytest
from pydantic import BaseModel

from signal_agent.structured_generation import FakeStructuredGenerator, StructuredGenerationError
from signal_agent.structured_generation.outlines_adapter import OutlinesStructuredGenerator
from signal_agent.structured_generation.policy import ManualLiveGenerationAuthorization


class ExampleResponse(BaseModel):
    name: str
    score: int


class OtherResponse(BaseModel):
    label: str


def test_fake_structured_generator_returns_validated_schema_object() -> None:
    generator = FakeStructuredGenerator(ExampleResponse(name="alpha", score=7))

    result = generator.generate("return an example response", ExampleResponse)

    assert result.value == ExampleResponse(name="alpha", score=7)
    assert result.receipt.provider == "fake"
    assert result.receipt.schema_name == "ExampleResponse"


def test_invalid_fake_output_fails_closed() -> None:
    generator = FakeStructuredGenerator(OtherResponse(label="not compatible"))

    with pytest.raises(StructuredGenerationError):
        generator.generate("return an example response", ExampleResponse)


def test_invalid_json_provider_output_fails_closed() -> None:
    generator = OutlinesStructuredGenerator(
        provider="openai",
        model="test-model",
        outlines_model=lambda _prompt, _schema: "{not valid json",
    )

    with pytest.raises(StructuredGenerationError):
        generator.generate(
            "return an example response",
            ExampleResponse,
            authorization=ManualLiveGenerationAuthorization.manual_smoke(),
        )


def test_unsupported_provider_output_type_fails_closed() -> None:
    generator = OutlinesStructuredGenerator(
        provider="openai",
        model="test-model",
        outlines_model=lambda _prompt, _schema: ["not", "a", "model"],
    )

    with pytest.raises(StructuredGenerationError):
        generator.generate(
            "return an example response",
            ExampleResponse,
            authorization=ManualLiveGenerationAuthorization.manual_smoke(),
        )
