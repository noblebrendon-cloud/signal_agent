from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Generic, Protocol, TypeVar

from pydantic import BaseModel, ConfigDict, Field


T = TypeVar("T", bound=BaseModel)

if TYPE_CHECKING:
    from .policy import GenerationBudgetPolicy, ManualLiveGenerationAuthorization


class StructuredGenerationError(RuntimeError):
    """Raised when structured generation cannot return a validated schema object."""


class GenerationReceipt(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    schema_name: str = Field(min_length=1)
    timestamp: datetime
    estimated_prompt_tokens_upper_bound: int | None = None
    prompt_utf8_bytes: int | None = None
    maximum_output_tokens: int | None = None
    configured_input_rate_usd_per_million: float | None = None
    configured_output_rate_usd_per_million: float | None = None
    estimated_max_request_cost_usd: float | None = None
    actual_prompt_tokens: int | None = None
    actual_completion_tokens: int | None = None
    actual_total_tokens: int | None = None
    actual_cost_usd: float | None = None
    cost_status: str = "unavailable"


class StructuredResult(BaseModel, Generic[T]):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    value: T
    receipt: GenerationReceipt


class StructuredGenerator(Protocol):
    def generate(
        self,
        prompt: str,
        schema: type[T],
        *,
        authorization: "ManualLiveGenerationAuthorization | None" = None,
        budget_policy: "GenerationBudgetPolicy | None" = None,
    ) -> StructuredResult[T]:
        ...
