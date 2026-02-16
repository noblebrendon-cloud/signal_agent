from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from app.utils.resilience import CircuitBreaker, call_with_resilience
from app.utils.reprojection import reproject_checkpoint, ConstraintPack
from app.utils.exceptions import ConstraintViolation
from app.audit.coherence_kernel import CoherenceKernel, Regime
import yaml


from app.providers.base import Provider
from app.providers.stub_provider import StubProvider
from app.providers.fail503_provider import Fail503Provider


@dataclass(frozen=True)
class AgentConfig:
    # Keying by provider:model per user requirement
    models: tuple[str, ...] = ("google:gemini-3-pro-high", "google:gemini-3-pro", "google:gemini-3-flash")
    max_attempts_per_model: int = 3
    base_delay_s: float = 0.5
    max_delay_s: float = 4.0
    multiplier: float = 2.0
    analytics_log: Path = Path("data/state/provider_events.jsonl")


class JsonlLogger:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def track(self, event: Dict[str, Any]) -> None:
        if "timestamp" not in event:
            event["timestamp"] = datetime.utcnow().isoformat()
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")


class SignalAgent:
    def __init__(self, config: Optional[AgentConfig] = None):
        self.config = config or AgentConfig()
        # Per-model circuit breakers, keyed by provider:model
        self.breakers = {m: CircuitBreaker() for m in self.config.models}
        self.logger = JsonlLogger(self.config.analytics_log)
        
        # Wiring providers (simulating configuration or dependency injection)
        # Mapping fully qualified keys to provider instances
        self.providers: Dict[str, Provider] = {
            "google:gemini-3-pro-high": Fail503Provider(),  # Simulate 503 on high tier
        }
        # Default fallback for others
        self._default_provider = StubProvider()
        
        # Coherence Kernel
        self.kernel = CoherenceKernel()
        # Mock session centroid for C2 (Context Drift) - effectively a template
        self.session_centroid = "Analyze the following data and provide a structured report."

    def _call_model(self, model_key: str, prompt: str) -> str:
        # model_key is "provider:model"
        provider = self.providers.get(model_key, self._default_provider)
        # parse just model name if provider expects simple name? 
        # Existing StubProvider/Fail503Provider don't care much, but let's be safe
        # providers.base.Provider.call takes (model, prompt)
        return provider.call(model_key, prompt)

    def _levenshtein(self, s1: str, s2: str) -> int:
        # Simple DP implementation for drift calculation
        if len(s1) < len(s2):
            return self._levenshtein(s2, s1)
        if len(s2) == 0:
            return len(s1)
        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row # type: ignore
        return previous_row[-1] # type: ignore

    def generate(self, prompt: str, constraint_pack_path: Optional[str] = None, request_id: Optional[str] = None) -> str:
        # 1. Entropy Sealing: Use or generate deterministic request_id
        rid = request_id or datetime.utcnow().strftime("req_%Y%m%d_%H%M%S_%f")
        track_evt = {"event": "AGENT_GENERATE_START", "prompt_chars": len(prompt), "request_id": rid}
        self.logger.track(track_evt)
        
        # Update C2: Context Drift
        dist = self._levenshtein(prompt, self.session_centroid)
        max_len = max(len(prompt), len(self.session_centroid))
        d_norm = dist / max_len if max_len > 0 else 0.0
        self.kernel.update_context_drift(d_norm)
        
        self.kernel.tick() # Advance window if needed
        
        # 2. Atomic Budget / Policy Check (Pre-Flight)
        # TODO: Hydrate snapshot from real usage state (e.g. Redis/DB)
        # For now, minimal snapshot to check GLOBAL constants
        pre_flight_snapshot = {
            "metrics": {"session_cost_usd": 0.0}, # Placeholder
            "context": {"user_id": "test_user"}
        }
        # In a real implementation:
        # result = policy_engine.resolve(action={"type": "generate", "prompt": prompt}, snapshot=pre_flight_snapshot, packs=ACTIVE_PACKS, context={})
        # if result.decision == "DENY": raise ConstraintViolation(...)

        def caller(model_key: str) -> str:
            return self._call_model(model_key, prompt)

        out = call_with_resilience(
            call_model=caller,
            models=self.config.models,
            request_id=rid,  # Deterministic seed source
            max_attempts_per_model=self.config.max_attempts_per_model,
            base_delay_s=self.config.base_delay_s,
            max_delay_s=self.config.max_delay_s,
            multiplier=self.config.multiplier,
            breakers=self.breakers,
            log=self.logger.track,
            kernel=self.kernel,
        )

        # Re-Project (Constraint Check)
        if constraint_pack_path:
            # Generate a context ID for logging if one isn't available
            ctx_id = f"gen_{datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}"
            
            # 1. Delta Check (Simulate rollback by raising on FAIL)
            # This raises ConstraintViolation on FAIL
            # This raises ConstraintViolation on FAIL
            try:
                reproject_checkpoint(out, constraint_pack_path, execution_context_id=ctx_id)
            except ConstraintViolation:
                self.kernel.record_constraint_violation()
                raise

        preview = str(out)
        self.logger.track({"event": "AGENT_GENERATE_DONE", "result_preview": preview[:120], "request_id": rid})
        return out


def main() -> None:
    agent = SignalAgent()
    try:
        print(agent.generate("hello from SignalAgent"))
    except Exception as e:
        print(f"Generation failed: {e}")


    # Example CLI hooks (would be in a proper CLI wrapper)
    import sys
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "curate":
            from app.hq.curation import brn_cmds
            target = sys.argv[2] if len(sys.argv) > 2 else "."
            brn_cmds.brn_curate_path(target)
        elif cmd == "curate.backfill":
            from app.hq.curation import brn_cmds
            brn_cmds.brn_curate_backfill()
        elif cmd == "meme.offload":
            from app.cli.brn_cmds_meme import main as meme_main
            sys.exit(meme_main(sys.argv[2:]))


if __name__ == "__main__":
    main()
