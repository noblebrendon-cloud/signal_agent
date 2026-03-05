from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None  # type: ignore


class ProviderRegistry:
    def __init__(self, config: dict[str, Any]):
        self._config = config

    def get_default_provider_name(self) -> str:
        return str(self._config.get("default_provider", "unknown"))

    def get_provider_profile(self, name: str) -> dict[str, Any]:
        providers = self._config.get("providers", {})
        if not isinstance(providers, dict):
            return {}
        profile = providers.get(name, {})
        return profile if isinstance(profile, dict) else {}

    def get_provider_profile_hash(self, name: str) -> str:
        profile = self.get_provider_profile(name)
        # Deterministic canonical JSON: sort keys, no whitespace variance.
        canonical = json.dumps(profile, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


STUB_CONFIG = {
    "default_provider": "stub",
    "providers": {
        "stub": {
            "max_attempts": 1,
            "breaker": {"failure_threshold": 1, "reset_seconds": 30},
            "deterministic_stub": True
        }
    }
}


def load_registry(config_path: Path = Path("config/model_pool.yaml")) -> ProviderRegistry:
    if not config_path.exists():
        # Fallback to safe default stub profile if file missing
        return ProviderRegistry(STUB_CONFIG)
    
    raw = config_path.read_text(encoding="utf-8")
    if config_path.suffix.lower() in {".yaml", ".yml"}:
        if yaml is None:
            raise RuntimeError("PyYAML not installed but config is .yaml")
        # Hard fail if file exists but is invalid (signals corruption)
        data = yaml.safe_load(raw)
        if data is None:
            raise ValueError(f"Config file {config_path} is empty or malformed YAML")
    else:
        # Attempt straight JSON
        data = json.loads(raw)
            
    if not isinstance(data, dict):
        raise ValueError(f"Config file {config_path} root must be a dictionary")

    return ProviderRegistry(data)
