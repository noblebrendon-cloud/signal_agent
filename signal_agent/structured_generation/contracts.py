from __future__ import annotations

from datetime import datetime
from typing import Generic, Protocol, TypeVar

from pydantic import BaseModel, ConfigDict, Field


T = TypeVar("T", bound=BaseModel)


class StructuredGenerationError(RuntimeError):
    """Raised when structured generation cannot return a validated schema object."""


class GenerationReceipt(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    schema_name: str = Field(min_length=1)
    timestamp: datetime


class StructuredResult(BaseModel, Generic[T]):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    value: T
    receipt: GenerationReceipt


class StructuredGenerator(Protocol):
    def generate(
        self,
        prompt: str,
        schema: type[T],
    ) -> StructuredResult[T]:
        ...
