from __future__ import annotations

import os
from typing import Literal, Mapping

from pydantic import BaseModel, ConfigDict

from .contracts import StructuredGenerationError


ProviderName = Literal["openai", "ollama", "vllm"]
SUPPORTED_PROVIDERS: tuple[ProviderName, ...] = ("openai", "ollama", "vllm")


class ProviderConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: ProviderName | None = None
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    explicitly_configured: bool = False


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _provider_model(provider: ProviderName, environ: Mapping[str, str]) -> str | None:
    default_model = _clean(environ.get("STRUCTURED_GENERATION_MODEL"))
    if provider == "openai":
        return _clean(environ.get("OPENAI_MODEL")) or default_model
    if provider == "ollama":
        return _clean(environ.get("OLLAMA_MODEL")) or default_model
    if provider == "vllm":
        return _clean(environ.get("VLLM_MODEL")) or default_model
    return default_model


def load_provider_config(environ: Mapping[str, str] | None = None) -> ProviderConfig:
    env = os.environ if environ is None else environ
    configured = _clean(env.get("STRUCTURED_GENERATION_PROVIDER"))
    if configured is None:
        return ProviderConfig()

    provider = configured.lower()
    if provider not in SUPPORTED_PROVIDERS:
        raise StructuredGenerationError(
            "Unsupported structured-generation provider "
            f"{configured!r}; supported providers are {', '.join(SUPPORTED_PROVIDERS)}."
        )

    if provider == "openai":
        return ProviderConfig(
            provider="openai",
            model=_provider_model("openai", env),
            api_key=_clean(env.get("OPENAI_API_KEY")),
            base_url=_clean(env.get("OPENAI_BASE_URL")),
            explicitly_configured=True,
        )
    if provider == "ollama":
        return ProviderConfig(
            provider="ollama",
            model=_provider_model("ollama", env),
            base_url=_clean(env.get("OLLAMA_HOST")),
            explicitly_configured=True,
        )
    return ProviderConfig(
        provider="vllm",
        model=_provider_model("vllm", env),
        api_key=_clean(env.get("VLLM_API_KEY")),
        base_url=_clean(env.get("VLLM_BASE_URL")),
        explicitly_configured=True,
    )
