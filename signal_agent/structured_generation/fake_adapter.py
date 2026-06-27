from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ValidationError

from .contracts import GenerationReceipt, StructuredGenerationError, StructuredResult, T


class FakeStructuredGenerator:
    """Deterministic structured generator for tests; never calls a provider."""

    def __init__(
        self,
        prepared_response: BaseModel,
        *,
        provider: str = "fake",
        model: str = "fake",
    ) -> None:
        if not isinstance(prepared_response, BaseModel):
            raise StructuredGenerationError("FakeStructuredGenerator requires a Pydantic response object.")
        self._prepared_response = prepared_response
        self._provider = provider
        self._model = model

    def generate(
        self,
        prompt: str,
        schema: type[T],
        *,
        authorization: object | None = None,
        budget_policy: object | None = None,
    ) -> StructuredResult[T]:
        del authorization, budget_policy
        if not prompt:
            raise StructuredGenerationError("Prompt must be non-empty.")

        try:
            value = (
                self._prepared_response
                if isinstance(self._prepared_response, schema)
                else schema.model_validate(self._prepared_response.model_dump())
            )
        except ValidationError as exc:
            raise StructuredGenerationError(
                f"Fake response does not validate as {schema.__name__}."
            ) from exc

        return StructuredResult(
            value=value,
            receipt=GenerationReceipt(
                provider=self._provider,
                model=self._model,
                schema_name=schema.__name__,
                timestamp=datetime.now(timezone.utc),
            ),
        )
