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
from .policy import (
    GenerationBudgetError,
    GenerationBudgetPolicy,
    GenerationBudgetSnapshot,
    GenerationUsageMetadata,
    LiveGenerationAuthorizationError,
    ManualLiveGenerationAuthorization,
)
from .provider_config import ProviderConfig, ProviderName, load_provider_config

__all__ = [
    "FakeStructuredGenerator",
    "GenerationBudgetError",
    "GenerationBudgetPolicy",
    "GenerationBudgetSnapshot",
    "GenerationReceipt",
    "GenerationUsageMetadata",
    "LiveGenerationAuthorizationError",
    "ManualLiveGenerationAuthorization",
    "ProviderConfig",
    "ProviderName",
    "StructuredGenerationError",
    "StructuredGenerator",
    "StructuredResult",
    "create_structured_generator",
    "load_provider_config",
]
