"""Interaction Signals stream runner (uses engine.py pipeline)."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

from ..core.types import Event
from ..core.engine import StateStore, process_event

_DEMO = [
    {"event_id":"e001","actor_id":"alice","thread_id":"t01","timestamp":"2026-02-28T18:00:00Z",
     "text":"I have researched this for months because the data from 3 independent studies proves it. Let me show the benchmark results.","meta":{}},
    {"event_id":"e002","actor_id":"alice","thread_id":"t01","timestamp":"2026-02-28T18:01:00Z",
     "text":"Book a call! DM me now. My clients see results. Sign up for the program today. Link in bio.","meta":{"reply_to":"let me show the benchmark"}},
    {"event_id":"e003","actor_id":"bob","thread_id":"t01","timestamp":"2026-02-28T18:02:00Z",
     "text":"Why would that work? How do you know it generalises? What edge cases might fail? Can you demonstrate?","meta":{"reply_to":"Book a call"}},
    {"event_id":"e004","actor_id":"alice","thread_id":"t01","timestamp":"2026-02-28T18:03:00Z",
     "text":"Fair point. Let me clarify. See benchmark at https://example.com (n=1200). This demonstrates precision.","meta":{"reply_to":"Why would that work"}},
    {"event_id":"e005","actor_id":"alice","thread_id":"t01","timestamp":"2026-02-28T18:04:00Z",
     "text":"Furthermore, building on what I showed, the integration of both approaches reduces cost. Moreover the synthesis suggests a convergent result.","meta":{"reply_to":"fair point"}},
]


def _ev(d: dict) -> Event:
    return Event(**{k: d.get(k, "") for k in ("event_id","actor_id","thread_id","timestamp","text")},
                  meta=d.get("meta", {}))


def run_stream(events: list[Event], ledger_path: Path | None = None, emit_actions: bool = False, self_actor_id: str = "self") -> None:
    store = StateStore(self_actor_id=self_actor_id)
    print(f"{'ID':<8} {'ACTOR':<8} {'MODE':<18} {'CONF':>6} {'V':>6} {'dV':>9} ALERT")
    print("-" * 68)
    for ev in events:
        r = process_event(ev, store, ledger_path=ledger_path)
        dv_s = f"{r.dV:+.4f}" if r.dV is not None else "        -"
        al_s = f"[{r.alert['kind']}]" if r.alert else ""
        print(f"{ev.event_id:<8} {ev.actor_id:<8} {r.mode:<18} {r.confidence:6.4f} {r.V:6.4f} {dv_s:>9} {al_s}")
        if emit_actions and r.policy_action is not None:
            pa = r.policy_action
            print(f"  policy: depth={pa.reply_depth} dm={pa.dm_gate} off={pa.off_platform_gate} "
                  f"artifact={pa.ask_for_artifact} pressure={pa.pressure_protocol}")
            for note in pa.notes:
                print(f"    · {note}")
        if r.phase_point and r.phase_region:
            pt = r.phase_point
            print(f"  phase: (T={pt.T:.2f}, Σ={pt.Σ:.2f}, V={pt.V:.2f}, Λ={pt.Λ:.2f})  region={r.phase_region}")
        if r.dyad_after:
            d = r.dyad_after
            print(f"  dyad: W={d.working_pair_score:.2f} (with {d.other_actor_id}) "
                  f"asym={d.asymmetry_penalty:.2f} ext={d.extraction_penalty:.2f}")
    print("-" * 68)
    print(f"Processed {len(events)} event(s).  Actors: {store.actor_ids}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="run_stream",
        description="Interaction Signals stream runner")
    p.add_argument("--input",  default=None, help="JSONL events file (omit = demo)")
    p.add_argument("--ledger", default=None, help="Append-only ledger output path")
    p.add_argument("--self-actor-id", default="self", help="Actor ID treated as 'self' for dyadic scoring")
    p.add_argument("--emit-actions", action="store_true",
                   help="Print PolicyAction lines below each event")
    args = p.parse_args(argv)
    if args.input:
        raw = Path(args.input).read_text(encoding="utf-8").splitlines()
        events = [_ev(json.loads(l)) for l in raw if l.strip()]
    else:
        events = [_ev(d) for d in _DEMO]
    run_stream(events, Path(args.ledger) if args.ledger else None, emit_actions=args.emit_actions, self_actor_id=args.self_actor_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
