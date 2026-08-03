"""
shared/reactions.py — Deterministic authority-governed reaction engine.

Supports exactly one actionable event path:
    PromotionSucceeded -> route_bundle

This is a manual reaction layer. It is never auto-invoked.
Call process_promotion_events() explicitly from CLI, a scheduled task, or a test.

Evaluation pipeline (per event):
    event -> evaluate_authority -> validate_lifecycle -> idempotency_check -> act -> record

Public API:
    process_promotion_events(
        event_log_path=None,
        checkpoint_path=None,
        dry_run: bool = False,
    ) -> list[dict]

Result statuses:
    ok        — action was executed successfully
    dry_run   — described without executing
    skipped   — already applied (idempotent guard)
    blocked   — authority or lifecycle rules prevented execution
    fail      — execution attempted but failed
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from shared.result_schemas import make_reaction_result
from shared.authority import check_preconditions_for_routing
from shared.state_registry import get_state


def _get_root() -> Path:
    override = os.environ.get("SIGNAL_AGENT_ROOT")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent


def _default_checkpoint_path() -> Path:
    return _get_root() / "data" / "state" / "reaction_checkpoint.json"


def route_bundle(*args: Any, **kwargs: Any) -> Dict[str, Any]:  # type: ignore[return]
    """Thin wrapper importable at module load time so tests can patch it."""
    from app.hq.capture.router import route_bundle as _route_bundle
    return _route_bundle(*args, **kwargs)


def _router_ruleset_hash() -> str:
    """Return the hash identity used by the canonical spine router."""
    ruleset_path = _get_root() / "config" / "spine_router.yaml"
    try:
        return hashlib.sha256(ruleset_path.read_bytes()).hexdigest()[:12]
    except OSError:
        return ""


def process_promotion_events(
    event_log_path: Optional[Path] = None,
    checkpoint_path: Optional[Path] = None,
    dry_run: bool = False,
) -> List[Dict[str, Any]]:
    """
    Process unhandled PromotionSucceeded events.

    For each unprocessed event:
    - Extract bundle_path from payload
    - If dry_run=True: record the intended action without routing
    - If dry_run=False: call route_bundle() on the bundle path
    - Mark the event as processed after a handling attempt

    Args:
        event_log_path:   Override event log path (for tests)
        checkpoint_path:  Override checkpoint path (for tests)
        dry_run:          If True, describe actions without executing them

    Returns:
        List of result dicts, one per event processed.
    """
    from shared.event_reader import (
        iter_unprocessed_events,
        mark_event_processed,
        _derive_event_id,
    )

    ckpt = checkpoint_path or _default_checkpoint_path()
    results: List[Dict[str, Any]] = []

    unprocessed = iter_unprocessed_events(
        checkpoint_path=ckpt,
        event_log_path=event_log_path,
        event_type="PromotionSucceeded",
    )

    for event in unprocessed:
        artifact_id = event.get("artifact_id", "")
        payload = event.get("payload", {})
        bundle_path_str = payload.get("bundle_path", "")
        event_id = _derive_event_id(event)

        # --- REACTION DECISION LAYER ---

        # Step 1: dry_run shortcut — describe without evaluating
        if dry_run:
            result = make_reaction_result(
                event_type="PromotionSucceeded",
                artifact_id=artifact_id,
                action="route_bundle",
                status="dry_run",
                bundle_path=bundle_path_str,
                error=None,
                details={"decision": {"should_execute": False, "reason": "dry_run"}},
            )
            results.append(result)
            mark_event_processed(event_id, ckpt)
            continue

        # Step 2: Idempotency guard — check current registered state
        current_entry = get_state(artifact_id)
        current_state = current_entry.get("state") if current_entry else None
        if current_state == "routed":
            decision = {"should_execute": False, "reason": "already_applied", "authority": None, "lifecycle_valid": None}
            result = make_reaction_result(
                event_type="PromotionSucceeded",
                artifact_id=artifact_id,
                action="route_bundle",
                status="skipped",
                bundle_path=bundle_path_str,
                error="already_applied",
                details={"decision": decision},
            )
            results.append(result)
            mark_event_processed(event_id, ckpt)
            continue

        # Step 3: Authority + lifecycle evaluation
        preconditions = check_preconditions_for_routing(
            artifact_id=artifact_id,
            expected_state="promoted",
            target_state="routed",
            transition_context={
                "bundle_path": bundle_path_str,
                "router_ruleset_hash": _router_ruleset_hash(),
            },
        )
        authority_result = preconditions["authority"]
        lifecycle_valid = authority_result["authoritative_source"] != "lifecycle_rules"
        decision = {
            "should_execute": authority_result["allowed"],
            "reason": "authority_check",
            "authority": authority_result,
            "lifecycle_valid": lifecycle_valid,
        }

        if not authority_result["allowed"]:
            blocking_source = authority_result["authoritative_source"]
            if blocking_source == "coherence_guard":
                error_msg = f"coherence check failed: {authority_result['blocking_reason']}"
            elif blocking_source == "lifecycle_rules":
                error_msg = f"blocked by authority rules: invalid_transition"
            else:
                error_msg = f"blocked by authority rules: {authority_result['blocking_reason']}"

            result = make_reaction_result(
                event_type="PromotionSucceeded",
                artifact_id=artifact_id,
                action="route_bundle",
                status="blocked",
                bundle_path=bundle_path_str,
                error=error_msg,
                details={"decision": decision, "authority": authority_result},
            )
            results.append(result)
            # Advance checkpoint: a blocked reaction is a decided outcome, not a crash
            mark_event_processed(event_id, ckpt)
            continue

        # Step 4: Pre-flight bundle existence check
        bundle_path = Path(bundle_path_str) if bundle_path_str else None
        if not bundle_path or not bundle_path.exists():
            result = make_reaction_result(
                event_type="PromotionSucceeded",
                artifact_id=artifact_id,
                action="route_bundle",
                status="fail",
                bundle_path=bundle_path_str,
                error=f"bundle_path does not exist or is empty: {bundle_path_str!r}",
                details={"decision": decision, "authority": authority_result},
            )
            results.append(result)
            mark_event_processed(event_id, ckpt)
            continue

        # Step 5: Execute routing — only checkpoint AFTER success/fail resolution
        route_error: str | None = None
        route_status = "fail"
        try:
            route_result = route_bundle(bundle_path=bundle_path)
            if route_result.get("status") in ("ok", "dry_run"):
                route_status = "ok"
            else:
                route_error = route_result.get("error")
        except Exception as exc:
            route_error = str(exc)

        result = make_reaction_result(
            event_type="PromotionSucceeded",
            artifact_id=artifact_id,
            action="route_bundle",
            status=route_status,
            bundle_path=bundle_path_str,
            error=route_error,
            details={"decision": decision, "authority": authority_result},
        )
        results.append(result)
        # Advance checkpoint after the routing attempt is resolved
        mark_event_processed(event_id, ckpt)

    return results
