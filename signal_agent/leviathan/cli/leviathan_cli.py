"""
Leviathan Interaction Signals CLI entrypoint.

Usage:
  python -m leviathan.cli.leviathan_cli --text "hello world" --json
  python -m leviathan.cli.leviathan_cli --interactive
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from signal_agent.leviathan.interaction_signals.core.engine import StateStore, process_event
from signal_agent.leviathan.interaction_signals.core.types import Event


def _round_floats(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, dict):
        return {k: _round_floats(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_round_floats(v) for v in value]
    return value


def _stable_json(data: Any) -> str:
    return json.dumps(
        _round_floats(data),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _build_event(text: str, actor_id: str, thread_id: str, seq: int) -> Event:
    normalized = " ".join(text.strip().split())
    material = f"{actor_id}|{thread_id}|{seq}|{normalized}".encode("utf-8")
    event_id = f"cli_{hashlib.sha256(material).hexdigest()[:12]}"
    timestamp = f"2026-01-01T00:00:{seq % 60:02d}Z"
    return Event(
        event_id=event_id,
        actor_id=actor_id,
        thread_id=thread_id,
        timestamp=timestamp,
        text=normalized,
        meta={"source": "leviathan_cli"},
    )


def _serialize_result(event: Event, result: Any) -> dict[str, Any]:
    signal = {
        "event_id": result.signal.event_id,
        "mode": result.signal.mode,
        "confidence": result.signal.confidence,
        "p": result.signal.p,
        "reasons": sorted(result.signal.reasons),
    }
    policy = None
    if result.policy_action is not None:
        policy = {
            "reply_depth": result.policy_action.reply_depth,
            "dm_gate": result.policy_action.dm_gate,
            "off_platform_gate": result.policy_action.off_platform_gate,
            "ask_for_artifact": result.policy_action.ask_for_artifact,
            "pressure_protocol": result.policy_action.pressure_protocol,
            "notes": list(result.policy_action.notes),
            "policy_version": result.policy_action.policy_version,
            "reasons": sorted(result.policy_action.reasons),
            "metrics_snapshot": result.policy_action.metrics_snapshot,
        }

    return {
        "event": {
            "event_id": event.event_id,
            "actor_id": event.actor_id,
            "thread_id": event.thread_id,
            "timestamp": event.timestamp,
            "text": event.text,
            "meta": event.meta,
        },
        "features": {"event_id": result.features.event_id, "f": result.features.f},
        "signal": signal,
        "actor_state": {
            "actor_id": result.actor_after.actor_id,
            "trust_score": result.actor_after.trust_score,
            "collab_readiness": result.actor_after.collab_readiness,
            "integrity_index": result.actor_after.integrity_index,
            "transaction_pressure": result.actor_after.transaction_pressure,
            "pressure_integrity": result.actor_after.pressure_integrity,
            "extraction_after_trust": result.actor_after.extraction_after_trust,
            "evasion_rate_30": result.actor_after.evasion_rate_30,
            "shipping_rate_30": result.actor_after.shipping_rate_30,
            "mode_volatility_30": result.actor_after.mode_volatility_30,
            "cooldown_dm": result.actor_after.cooldown_dm,
            "cooldown_off": result.actor_after.cooldown_off,
            "mode_histogram_30": result.actor_after.mode_histogram_30,
            "transition_matrix": result.actor_after.transition_matrix,
        },
        "thread_state": {
            "thread_id": result.thread_after.thread_id,
            "working_node_score": result.thread_after.working_node_score,
            "shipping_evidence_score": result.thread_after.shipping_evidence_score,
            "drift_score": result.thread_after.drift_score,
            "leverage_score": result.thread_after.leverage_score,
            "artifact_probability": result.thread_after.artifact_probability,
            "coordination_cost": result.thread_after.coordination_cost,
            "convergence_rate": result.thread_after.convergence_rate,
            "disagreement_productivity": result.thread_after.disagreement_productivity,
        },
        "controller": {
            "V": result.V,
            "dV": result.dV,
            "pipeline_version": result.pipeline_version,
            "pipeline_order": list(result.pipeline_order),
        },
        "policy": policy,
    }


def _print_human(payload: dict[str, Any]) -> None:
    ordered_sections = (
        "event",
        "features",
        "signal",
        "actor_state",
        "thread_state",
        "controller",
        "policy",
    )
    for section in ordered_sections:
        print(f"{section}: {_stable_json(payload.get(section))}")


def run_pipeline(
    *,
    text: str,
    actor_id: str = "cli_user",
    thread_id: str = "cli_thread",
    store: StateStore | None = None,
    seq: int = 1,
    ledger_path: Path | None = None,
) -> dict[str, Any]:
    """
    Run the Leviathan interaction pipeline and return a deterministic payload.

    This is intentionally side-effect free except for optional ledger appends.
    """
    if not text or not text.strip():
        raise ValueError("empty text input")

    active_store = store or StateStore()
    event = _build_event(text=text, actor_id=actor_id, thread_id=thread_id, seq=seq)
    result = process_event(event, active_store, ledger_path=ledger_path)
    return _round_floats(_serialize_result(event, result))


def _run_once(
    *,
    text: str,
    actor_id: str,
    thread_id: str,
    store: StateStore,
    seq: int,
    as_json: bool,
    ledger_path: Path | None,
) -> int:
    try:
        payload = run_pipeline(
            text=text,
            actor_id=actor_id,
            thread_id=thread_id,
            store=store,
            seq=seq,
            ledger_path=ledger_path,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if as_json:
        print(_stable_json(payload))
    else:
        _print_human(payload)
    return 0


def _run_repl(args: argparse.Namespace) -> int:
    store = StateStore()
    seq = 1
    while True:
        try:
            line = input("> ")
        except EOFError:
            return 0
        if line is None:
            return 0
        stripped = line.strip()
        if stripped.lower() in {"exit", "quit"}:
            return 0
        if not stripped:
            continue
        code = _run_once(
            text=stripped,
            actor_id=args.actor,
            thread_id=args.thread,
            store=store,
            seq=seq,
            as_json=args.json,
            ledger_path=Path(args.ledger) if args.ledger else None,
        )
        if code != 0:
            return code
        seq += 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="leviathan_cli")
    parser.add_argument("--text", default=None, help="Single-shot text input")
    parser.add_argument("--interactive", action="store_true", help="Run interactive REPL mode")
    parser.add_argument("--actor", default="cli_user", help="Actor identifier")
    parser.add_argument("--thread", default="cli_thread", help="Thread identifier")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument("--ledger", default=None, help="Optional ledger JSONL path")
    args = parser.parse_args(argv)

    if args.interactive:
        return _run_repl(args)

    if args.text is None:
        parser.error("--text is required unless --interactive is set")

    store = StateStore()
    return _run_once(
        text=args.text,
        actor_id=args.actor,
        thread_id=args.thread,
        store=store,
        seq=1,
        as_json=args.json,
        ledger_path=Path(args.ledger) if args.ledger else None,
    )


if __name__ == "__main__":
    raise SystemExit(main())
