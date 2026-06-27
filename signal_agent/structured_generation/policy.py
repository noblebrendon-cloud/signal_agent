from __future__ import annotations

import os
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .contracts import StructuredGenerationError


MAX_EVIDENCE_ITEMS = 20
MAX_EVIDENCE_SUMMARY_CHARS = 500
MAX_PROMPT_UTF8_BYTES = 12000
MAX_OUTPUT_TOKENS = 512
MANUAL_SMOKE_ORIGIN = "manual_smoke"


class GenerationBudgetError(StructuredGenerationError):
    """Raised before provider activation when a generation budget is exceeded."""


class LiveGenerationAuthorizationError(StructuredGenerationError):
    """Raised before provider activation when live authorization is missing."""


class ManualLiveGenerationAuthorization(BaseModel):
    model_config = ConfigDict(frozen=True)

    origin: str = Field(min_length=1)

    @classmethod
    def manual_smoke(cls) -> "ManualLiveGenerationAuthorization":
        return cls(origin=MANUAL_SMOKE_ORIGIN)


class GenerationBudgetPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_evidence_items: int = MAX_EVIDENCE_ITEMS
    max_evidence_summary_chars: int = MAX_EVIDENCE_SUMMARY_CHARS
    max_prompt_utf8_bytes: int = MAX_PROMPT_UTF8_BYTES
    max_output_tokens: int = MAX_OUTPUT_TOKENS
    input_usd_per_million_tokens: Decimal | None = None
    output_usd_per_million_tokens: Decimal | None = None
    max_request_usd: Decimal | None = None

    @field_validator(
        "max_evidence_items",
        "max_evidence_summary_chars",
        "max_prompt_utf8_bytes",
        "max_output_tokens",
    )
    @classmethod
    def _positive_int(cls, value: int) -> int:
        if value < 1:
            raise ValueError("budget limit must be positive")
        return value

    @field_validator("max_output_tokens")
    @classmethod
    def _within_hard_output_ceiling(cls, value: int) -> int:
        if value > MAX_OUTPUT_TOKENS:
            raise ValueError(f"max_output_tokens_exceeds_hard_ceiling:{MAX_OUTPUT_TOKENS}")
        return value

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> "GenerationBudgetPolicy":
        env = os.environ if environ is None else environ
        rates = _rate_config_from_environment(env)
        return cls(**rates)


class GenerationBudgetSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    estimated_prompt_tokens_upper_bound: int
    prompt_utf8_bytes: int
    maximum_output_tokens: int
    configured_input_rate_usd_per_million: float | None = None
    configured_output_rate_usd_per_million: float | None = None
    estimated_max_request_cost_usd: float | None = None
    cost_status: str

    def receipt_fields(self) -> dict[str, object]:
        return self.model_dump(mode="json")


class GenerationUsageMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    actual_prompt_tokens: int | None = None
    actual_completion_tokens: int | None = None
    actual_total_tokens: int | None = None
    actual_cost_usd: float | None = None

    def receipt_fields(self) -> dict[str, object]:
        return self.model_dump(mode="json")


def require_manual_live_authorization(
    authorization: ManualLiveGenerationAuthorization | None,
) -> None:
    if authorization is None:
        raise LiveGenerationAuthorizationError("missing_manual_live_generation_authorization")
    if authorization.origin != MANUAL_SMOKE_ORIGIN:
        raise LiveGenerationAuthorizationError(
            f"unsupported_live_generation_authorization_origin:{authorization.origin}"
        )


def preflight_generation_budget(
    prompt: str,
    policy: GenerationBudgetPolicy | None = None,
) -> GenerationBudgetSnapshot:
    active_policy = policy or GenerationBudgetPolicy.from_environment()
    prompt_utf8_bytes = len(prompt.encode("utf-8"))
    estimated_prompt_tokens_upper_bound = prompt_utf8_bytes
    if prompt_utf8_bytes > active_policy.max_prompt_utf8_bytes:
        raise GenerationBudgetError(
            "prompt_utf8_bytes_exceeds_limit:"
            f"{prompt_utf8_bytes}:{active_policy.max_prompt_utf8_bytes}"
        )

    cost_fields = _estimated_cost_fields(
        estimated_prompt_tokens_upper_bound=estimated_prompt_tokens_upper_bound,
        maximum_output_tokens=active_policy.max_output_tokens,
        policy=active_policy,
    )
    snapshot = GenerationBudgetSnapshot(
        estimated_prompt_tokens_upper_bound=estimated_prompt_tokens_upper_bound,
        prompt_utf8_bytes=prompt_utf8_bytes,
        maximum_output_tokens=active_policy.max_output_tokens,
        **cost_fields,
    )
    if (
        active_policy.max_request_usd is not None
        and snapshot.estimated_max_request_cost_usd is not None
        and Decimal(str(snapshot.estimated_max_request_cost_usd)) > active_policy.max_request_usd
    ):
        raise GenerationBudgetError(
            "estimated_max_request_cost_exceeds_cap:"
            f"{snapshot.estimated_max_request_cost_usd}:{float(active_policy.max_request_usd)}"
        )
    return snapshot


def unavailable_usage_metadata() -> GenerationUsageMetadata:
    return GenerationUsageMetadata()


def _rate_config_from_environment(env: Mapping[str, str]) -> dict[str, Decimal]:
    keys = {
        "input_usd_per_million_tokens": "STRUCTURED_GENERATION_INPUT_USD_PER_MILLION_TOKENS",
        "output_usd_per_million_tokens": "STRUCTURED_GENERATION_OUTPUT_USD_PER_MILLION_TOKENS",
        "max_request_usd": "STRUCTURED_GENERATION_MAX_REQUEST_USD",
    }
    present = {field: env.get(name) for field, name in keys.items() if env.get(name)}
    if not present:
        return {}
    if len(present) != len(keys):
        return {}
    parsed: dict[str, Decimal] = {}
    for field, raw_value in present.items():
        parsed[field] = _positive_decimal(field, raw_value)
    return parsed


def _positive_decimal(field: str, raw_value: str | None) -> Decimal:
    if raw_value is None:
        raise GenerationBudgetError(f"missing_{field}")
    try:
        value = Decimal(raw_value.strip())
    except (AttributeError, InvalidOperation) as exc:
        raise GenerationBudgetError(f"invalid_{field}") from exc
    if value < 0:
        raise GenerationBudgetError(f"negative_{field}")
    return value


def _estimated_cost_fields(
    *,
    estimated_prompt_tokens_upper_bound: int,
    maximum_output_tokens: int,
    policy: GenerationBudgetPolicy,
) -> dict[str, Any]:
    if (
        policy.input_usd_per_million_tokens is None
        or policy.output_usd_per_million_tokens is None
        or policy.max_request_usd is None
    ):
        return {
            "configured_input_rate_usd_per_million": None,
            "configured_output_rate_usd_per_million": None,
            "estimated_max_request_cost_usd": None,
            "cost_status": "unavailable",
        }

    million = Decimal("1000000")
    estimated_cost = (
        Decimal(estimated_prompt_tokens_upper_bound) * policy.input_usd_per_million_tokens
        + Decimal(maximum_output_tokens) * policy.output_usd_per_million_tokens
    ) / million
    return {
        "configured_input_rate_usd_per_million": float(policy.input_usd_per_million_tokens),
        "configured_output_rate_usd_per_million": float(policy.output_usd_per_million_tokens),
        "estimated_max_request_cost_usd": float(estimated_cost),
        "cost_status": "estimated_max_available",
    }
