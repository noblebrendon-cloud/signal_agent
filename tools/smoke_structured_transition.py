from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from signal_agent.laviathon.schemas import TransitionProposal
from signal_agent.structured_generation.factory import create_structured_generator


SMOKE_ENTITY_ID = "smoke-entity-001"
SMOKE_OBSERVED_STATE = "synthetic_current_state"
SMOKE_EVIDENCE_IDS = ("smoke-evidence-001", "smoke-evidence-002")
ALLOWED_ROUTES = ("admit", "blocked_duplicate", "manual_review")
CONFIG_HELP = (
    "Expected provider configuration: set STRUCTURED_GENERATION_PROVIDER to "
    "openai, ollama, or vllm; set the matching model variable "
    "(OPENAI_MODEL, OLLAMA_MODEL, VLLM_MODEL, or STRUCTURED_GENERATION_MODEL); "
    "set provider credentials or base URL only when required by that provider."
)


def build_smoke_prompt() -> str:
    prompt_payload = {
        "entity_id": SMOKE_ENTITY_ID,
        "observed_state": SMOKE_OBSERVED_STATE,
        "allowed_routes": list(ALLOWED_ROUTES),
        "evidence_ids": list(SMOKE_EVIDENCE_IDS),
        "task": "Create a proposal only. Do not create a final decision.",
        "constraints": [
            "Use only the supplied synthetic entity_id.",
            "Use only the supplied synthetic evidence_ids.",
            "Use only allowed recommended_route values.",
            "Do not infer real-world facts, identifiers, observations, ledgers, or state.",
            "Include uncertainty_notes when the synthetic facts are insufficient.",
        ],
    }
    return "\n".join(
        (
            "Generate one validated Laviathon TransitionProposal.",
            "This is a manual smoke test of structured generation only.",
            "The output is a proposal only, not a final decision or state change.",
            "Allowed routes are only: admit, blocked_duplicate, manual_review.",
            "Use uncertainty_notes whenever facts are insufficient.",
            "Use no real entity identifiers, observation IDs, source material, secrets, or ledger content.",
            json.dumps(prompt_payload, ensure_ascii=True, sort_keys=True),
        )
    )


def run_smoke_test(generator: Any) -> tuple[int, dict[str, object]]:
    try:
        result = generator.generate(build_smoke_prompt(), TransitionProposal)
        proposal = result.value
        _validate_synthetic_proposal(proposal)
        return (
            0,
            {
                "status": "validated",
                "proposal": proposal.model_dump(mode="json"),
                "generation_receipt": {
                    "provider": result.receipt.provider,
                    "model": result.receipt.model,
                    "schema_name": result.receipt.schema_name,
                    "created_at": result.receipt.timestamp.isoformat(),
                },
            },
        )
    except Exception as exc:  # noqa: BLE001 - smoke harness must fail safely for provider errors.
        return 1, _failure_payload(exc)


def main() -> int:
    try:
        generator = create_structured_generator()
    except Exception as exc:  # noqa: BLE001 - print a safe failure payload, never a traceback.
        _print_payload(_failure_payload(exc))
        return 1

    exit_code, payload = run_smoke_test(generator)
    _print_payload(payload)
    return exit_code


def _validate_synthetic_proposal(proposal: TransitionProposal) -> None:
    if proposal.entity_id != SMOKE_ENTITY_ID:
        raise ValueError("validated_proposal_entity_id_was_not_synthetic")
    if proposal.observed_state != SMOKE_OBSERVED_STATE:
        raise ValueError("validated_proposal_state_was_not_synthetic")
    unknown_evidence = [
        evidence_id
        for evidence_id in proposal.evidence_ids
        if evidence_id not in SMOKE_EVIDENCE_IDS
    ]
    if unknown_evidence:
        raise ValueError("validated_proposal_used_unknown_evidence_ids")


def _failure_payload(exc: Exception) -> dict[str, object]:
    return {
        "status": "failed",
        "error_type": type(exc).__name__,
        "message": _safe_message(exc),
    }


def _safe_message(exc: Exception) -> str:
    raw = str(exc).strip() or "Structured transition smoke test failed."
    redacted = re.sub(r"sk-[A-Za-z0-9_-]+", "[redacted]", raw)
    redacted = re.sub(
        r"(?i)(api[_-]?key|authorization|bearer)\s*[:=]\s*\S+",
        r"\1=[redacted]",
        redacted,
    )
    redacted = " ".join(redacted.split())
    if len(redacted) > 500:
        redacted = redacted[:497].rstrip() + "..."
    return f"{redacted} {CONFIG_HELP}"


def _print_payload(payload: dict[str, object]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
