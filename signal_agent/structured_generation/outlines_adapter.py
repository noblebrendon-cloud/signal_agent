from __future__ import annotations

import importlib
import inspect
from datetime import datetime, timezone
from types import ModuleType
from typing import Any

from pydantic import BaseModel, ValidationError

from .contracts import GenerationReceipt, StructuredGenerationError, StructuredResult, T
from .policy import (
    GenerationBudgetPolicy,
    ManualLiveGenerationAuthorization,
    preflight_generation_budget,
    require_manual_live_authorization,
    unavailable_usage_metadata,
)
from .provider_config import ProviderConfig, ProviderName


def _dependency(module_name: str, install_hint: str) -> ModuleType:
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name == module_name:
            raise StructuredGenerationError(
                f"Structured generation provider dependency {module_name!r} is unavailable. "
                f"{install_hint}"
            ) from exc
        raise


def normalize_provider_output(output: Any, schema: type[T]) -> T:
    """Validate provider output while keeping raw model text inside this package."""

    try:
        if isinstance(output, schema):
            return output
        if isinstance(output, BaseModel):
            return schema.model_validate(output.model_dump())
        if type(output) is dict:
            return schema.model_validate(output)
        if isinstance(output, str):
            return schema.model_validate_json(output)
    except (TypeError, ValueError, ValidationError) as exc:
        raise StructuredGenerationError(
            f"Provider output did not validate as {schema.__name__}."
        ) from exc

    raise StructuredGenerationError(
        f"Unsupported provider output type for {schema.__name__}: {type(output).__name__}."
    )


class OutlinesStructuredGenerator:
    """
    The only allowed provider-integration boundary for structured generation.

    Governance, gates, ledgers, and decision engines must depend on the
    StructuredGenerator protocol, not on Outlines or a concrete LLM provider.
    """

    def __init__(
        self,
        *,
        provider: ProviderName,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        outlines_model: Any | None = None,
        budget_policy: GenerationBudgetPolicy | None = None,
    ) -> None:
        if not model:
            raise StructuredGenerationError("Structured generation model must be configured.")
        self._provider = provider
        self._model_name = model
        self._api_key = api_key
        self._base_url = base_url
        self._outlines_model = outlines_model
        self._budget_policy = budget_policy or GenerationBudgetPolicy.from_environment()

    @classmethod
    def from_config(
        cls,
        config: ProviderConfig,
        *,
        budget_policy: GenerationBudgetPolicy | None = None,
    ) -> "OutlinesStructuredGenerator":
        if config.provider is None or config.model is None:
            raise StructuredGenerationError(
                "A provider and model must be explicitly configured before creating an Outlines adapter."
            )
        return cls(
            provider=config.provider,
            model=config.model,
            api_key=config.api_key,
            base_url=config.base_url,
            budget_policy=budget_policy,
        )

    def generate(
        self,
        prompt: str,
        schema: type[T],
        *,
        authorization: ManualLiveGenerationAuthorization | None = None,
        budget_policy: GenerationBudgetPolicy | None = None,
    ) -> StructuredResult[T]:
        if not prompt:
            raise StructuredGenerationError("Prompt must be non-empty.")

        require_manual_live_authorization(authorization)
        snapshot = preflight_generation_budget(prompt, budget_policy or self._budget_policy)
        inference_kwargs = self._inference_kwargs(snapshot.maximum_output_tokens)
        model = self._model()
        try:
            raw_output = model(prompt, schema, **inference_kwargs)
        except Exception as exc:
            raise StructuredGenerationError(
                f"{self._provider} structured generation failed before validation."
            ) from exc

        value = normalize_provider_output(raw_output, schema)
        usage_metadata = unavailable_usage_metadata()
        return StructuredResult(
            value=value,
            receipt=GenerationReceipt(
                provider=self._provider,
                model=self._model_name,
                schema_name=schema.__name__,
                timestamp=datetime.now(timezone.utc),
                **snapshot.receipt_fields(),
                **usage_metadata.receipt_fields(),
            ),
        )

    def _model(self) -> Any:
        if self._outlines_model is None:
            self._outlines_model = self._create_outlines_model()
        return self._outlines_model

    def _create_outlines_model(self) -> Any:
        outlines = _dependency("outlines", 'Install the optional "outlines" package for live adapters.')

        if self._provider == "openai":
            openai = _dependency("openai", 'Install with: pip install "outlines[openai]".')
            kwargs: dict[str, str] = {}
            if self._api_key is not None:
                kwargs["api_key"] = self._api_key
            if self._base_url is not None:
                kwargs["base_url"] = self._base_url
            return outlines.from_openai(
                openai.OpenAI(**kwargs, **_openai_no_retry_kwargs(openai.OpenAI)),
                self._model_name,
            )

        if self._provider == "ollama":
            raise StructuredGenerationError(
                "Ollama live structured generation is disabled until no-retry "
                "behavior is verified for the installed ollama client."
            )

        if self._provider == "vllm":
            openai = _dependency("openai", "Install the OpenAI Python SDK for vLLM server mode.")
            kwargs = {}
            if self._api_key is not None:
                kwargs["api_key"] = self._api_key
            if self._base_url is not None:
                kwargs["base_url"] = self._base_url
            return outlines.from_vllm(
                openai.OpenAI(**kwargs, **_openai_no_retry_kwargs(openai.OpenAI)),
                self._model_name,
            )

        raise StructuredGenerationError(f"Unsupported provider {self._provider!r}.")

    def _inference_kwargs(self, maximum_output_tokens: int) -> dict[str, object]:
        if self._provider == "openai":
            return {"max_completion_tokens": maximum_output_tokens}
        if self._provider == "vllm":
            return {"max_tokens": maximum_output_tokens}
        if self._provider == "ollama":
            raise StructuredGenerationError(
                "Ollama live structured generation is disabled until output-token "
                "and no-retry enforcement are verified for the installed ollama client."
            )
        raise StructuredGenerationError(f"Unsupported provider {self._provider!r}.")


def _openai_no_retry_kwargs(openai_constructor: object) -> dict[str, int]:
    try:
        parameters = inspect.signature(openai_constructor).parameters
    except (TypeError, ValueError) as exc:
        raise StructuredGenerationError(
            "Cannot verify OpenAI-compatible no-retry support."
        ) from exc
    if "max_retries" not in parameters:
        raise StructuredGenerationError(
            "OpenAI-compatible client does not expose max_retries; refusing live generation."
        )
    return {"max_retries": 0}
