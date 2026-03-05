"""summarize_ledger.py -- Post-hoc analytics CLI for Interaction Signals (v0.5).

Reads an append-only JSONL ledger and computes:
- Region distribution and transitions
- Alert counts and timeline
- Top dyads by working_pair_score
- Actor flip-risk ranking P(H->T)
"""
from __future__ import annotations
import argparse, json, sys, csv
from pathlib import Path
from collections import defaultdict

from signal_agent.leviathan.interaction_signals.core.policy import transition_prob


def _safe_float(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Interaction Signals Ledger Summarizer")
    p.add_argument("--ledger", required=True, help="Path to JSONL ledger")
    p.add_argument("--top-dyads", type=int, default=10, help="Number of dyads to show")
    p.add_argument("--top-actors", type=int, default=10, help="Number of actors to rank by flip-risk")
    p.add_argument("--csv-out", default=None, help="Export actor/dyad summaries to CSV prefix")
    args = p.parse_args(argv)

    ledger_path = Path(args.ledger)
    if not ledger_path.exists():
        print(f"Error: Ledger file not found at {ledger_path}", file=sys.stderr)
        return 1

    # Metrics collections
    region_counts = defaultdict(int)
    region_transitions = defaultdict(int)
    last_region_per_thread = {}
    
    alerts_timeline = []
    
    final_actor_states = {}
    final_dyad_states = {}
    
    total_events = 0

    with ledger_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            total_events += 1
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            
            ev = rec.get("event", {})
            actor_after = rec.get("actor_after", {})
            thread_id = ev.get("thread_id")
            actor_id = ev.get("actor_id")
            
            # Phase space regions
            region = rec.get("phase_region")
            if region:
                region_counts[region] += 1
                if thread_id:
                    prev_region = last_region_per_thread.get(thread_id)
                    if prev_region and prev_region != region:
                        region_transitions[f"{prev_region} -> {region}"] += 1
                    last_region_per_thread[thread_id] = region
            
            # Alerts tracking
            # policy_action notes might contain alerts, or we can look for specific v_spike/pressure texts.
            # actually, process_event logic triggers alerts and injects into notes.
            pa = rec.get("policy_action")
            if pa and pa.get("notes"):
                for note in pa["notes"]:
                    if "v_spike" in note or "pressure_integrity alert" in note or "pressure protocol" in note:
                        alerts_timeline.append({
                            "timestamp": ev.get("timestamp"),
                            "thread_id": thread_id,
                            "actor_id": actor_id,
                            "note": note
                        })
            
            # Actors flip-risk
            if actor_id and actor_after:
                final_actor_states[actor_id] = actor_after
                
            # Dyads
            dy = rec.get("dyad_after")
            if dy:
                k = (dy.get("self_actor_id"), dy.get("other_actor_id"))
                final_dyad_states[k] = dy

    # ── Print Report ───────────────────────────────────────────────────────
    
    print("=" * 60)
    print(f"Interaction Signals Ledger Summary (events={total_events})")
    print("=" * 60)
    
    print("\n[ Phase Space Regions ]")
    for r, c in sorted(region_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {r:<25} : {c} events")
        
    if region_transitions:
        print("\n[ Top Region Transitions ]")
        for t, c in sorted(region_transitions.items(), key=lambda x: x[1], reverse=True)[:5]:
            print(f"  {t:<35} : {c} times")

    print(f"\n[ Alerts Timeline ({len(alerts_timeline)} events) ]")
    for a in alerts_timeline[-10:]:  # show last 10
        print(f"  {a['timestamp']} | thread={a['thread_id']} actor={a['actor_id']}")
        print(f"    -> {a['note']}")
        
    print("\n[ Top Dyads by Working Pair Score (W) ]")
    dyad_list = list(final_dyad_states.values())
    dyad_list.sort(key=lambda d: _safe_float(d.get("working_pair_score", 0.0)), reverse=True)
    for d in dyad_list[:args.top_dyads]:
        self_id, other_id = d.get("self_actor_id"), d.get("other_actor_id")
        w = _safe_float(d.get("working_pair_score"))
        asym = _safe_float(d.get("asymmetry_penalty"))
        ext = _safe_float(d.get("extraction_penalty"))
        print(f"  {self_id} <> {other_id:<10} | W: {w:.3f}  (asym: {asym:.3f}, ext: {ext:.3f})")

    print("\n[ Actor Flip-Risk P(HONESTY -> TRANSACTION) ]")
    actor_risks = []
    for aid, st in final_actor_states.items():
        tm = st.get("transition_matrix", {})
        p = transition_prob(tm, "COGNITIVE_HONESTY", "TRANSACTION") if tm else 0.0
        actor_risks.append((aid, p, st.get("mode_volatility_30", 0.0)))
        
    actor_risks.sort(key=lambda x: x[1], reverse=True)
    for aid, p, vol in actor_risks[:args.top_actors]:
        print(f"  {aid:<15} | P(H->T): {p:.3f}  (volatility: {vol:.3f})")
        
    print("=" * 60)

    # ── CSV Export ─────────────────────────────────────────────────────────
    if args.csv_out:
        dyads_path = f"{args.csv_out}_dyads.csv"
        with open(dyads_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["self_actor", "other_actor", "W", "asymmetry_penalty", "extraction_penalty"])
            for d in dyad_list:
                w.writerow([
                    d.get("self_actor_id"), d.get("other_actor_id"), 
                    d.get("working_pair_score"), d.get("asymmetry_penalty"), d.get("extraction_penalty")
                ])
                
        actors_path = f"{args.csv_out}_actors.csv"
        with open(actors_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["actor_id", "p_h_to_t", "volatility"])
            for aid, p, vol in actor_risks:
                w.writerow([aid, p, vol])
                
        print(f"Exported CSVs to {dyads_path} and {actors_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
