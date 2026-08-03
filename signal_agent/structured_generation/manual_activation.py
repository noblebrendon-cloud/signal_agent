from __future__ import annotations

from dataclasses import dataclass

from .contracts import StructuredGenerator
from .factory import create_structured_generator
from .policy import GenerationBudgetPolicy, ManualLiveGenerationAuthorization


@dataclass(frozen=True)
class ManualGenerationContext:
    """Governed provider, authorization, and budget assembled for a manual request."""

    generator: StructuredGenerator
    authorization: ManualLiveGenerationAuthorization
    budget_policy: GenerationBudgetPolicy


def resolve_manual_generation_context() -> ManualGenerationContext:
    """Assemble the only production context allowed to activate live generation."""
    budget_policy = GenerationBudgetPolicy.from_environment()
    return ManualGenerationContext(
        generator=create_structured_generator(budget_policy=budget_policy),
        authorization=ManualLiveGenerationAuthorization.manual_smoke(),
        budget_policy=budget_policy,
    )
