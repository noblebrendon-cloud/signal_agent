"""Provider-independent structured generation boundary."""
from __future__ import annotations

from .contracts import (
    GenerationReceipt,
    StructuredGenerationError,
    StructuredGenerator,
    StructuredResult,
)
from .fake_adapter import FakeStructuredGenerator
from .factory import create_structured_generator
from .provider_config import ProviderConfig, ProviderName, load_provider_config

__all__ = [
    "FakeStructuredGenerator",
    "GenerationReceipt",
    "ProviderConfig",
    "ProviderName",
    "StructuredGenerationError",
    "StructuredGenerator",
    "StructuredResult",
    "create_structured_generator",
    "load_provider_config",
]
