from __future__ import annotations

from .contracts import StructuredGenerationError, StructuredGenerator
from .outlines_adapter import OutlinesStructuredGenerator
from .provider_config import ProviderConfig, load_provider_config


def create_structured_generator(config: ProviderConfig | None = None) -> StructuredGenerator:
    cfg = config or load_provider_config()
    if not cfg.explicitly_configured:
        raise StructuredGenerationError(
            "No structured-generation provider is explicitly configured. "
            "Use FakeStructuredGenerator in tests."
        )
    return OutlinesStructuredGenerator.from_config(cfg)
