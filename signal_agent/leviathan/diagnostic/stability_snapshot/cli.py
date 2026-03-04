"""
CLI Surface for the AI Stability Snapshot and Causal Ledger.
"""
import argparse
import sys
import json
import pathlib
from dataclasses import asdict
from .engine import compute_snapshot
from .spec import QUESTIONS
from ..causality.ledger import init_ledger_entry
from .policy_gate import evaluate_gate

def run_interactive_snapshot() -> list[bool]:
    answers = []
    print("AI Stability Snapshot\nAnswer 'y' or 'n' to the following:")
    for q in QUESTIONS:
        while True:
            resp = input(f"{q['text']} (y/n): ").strip().lower()
            if resp in ('y', 'yes', '1', 'true'):
                answers.append(True)
                break
            elif resp in ('n', 'no', '0', 'false'):
                answers.append(False)
                break
            else:
                print("Please answer with 'y' or 'n'.")
    return answers


def handle_snapshot(args):
    answers = []
    if args.interactive:
        answers = run_interactive_snapshot()
    elif args.answers:
        parts = args.answers.split(",")
        if len(parts) != len(QUESTIONS):
            print(f"Error: expected {len(QUESTIONS)} answers, but got {len(parts)}", file=sys.stderr)
            sys.exit(1)
            
        for p in parts:
            val = p.strip().lower()
            answers.append(val in ('1', 'y', 'yes', 'true', 't'))
    else:
        print("Error: must provide --interactive or --answers", file=sys.stderr)
        sys.exit(1)
        
    try:
        result = compute_snapshot(answers)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
        
    if args.json:
        if args.out_dir:
            out_path = pathlib.Path(args.out_dir) / "snapshot_result.json"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)
            print(f"Wrote result to {out_path}")
        else:
            print(json.dumps(result, indent=2))
    else:
        print(f"\nScore: {result['score']}/{result['max_score']}")
        print(f"Interpretation: {result['interpretation']}")
        
def handle_init_ledger(args):
    out_dir = pathlib.Path(args.out_dir) if args.out_dir else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        
    code = init_ledger_entry(
        incident_id=args.incident_id,
        write_dir=out_dir,
        timestamp_override=args.now
    )
    sys.exit(code)
    
def handle_gate(args):
    override_payload = None
    if args.override_json:
        try:
            parsed = json.loads(args.override_json)
        except json.JSONDecodeError as exc:
            print(f"Error: invalid --override-json: {exc}", file=sys.stderr)
            sys.exit(1)

        if not isinstance(parsed, dict):
            print("Error: --override-json must decode to a JSON object", file=sys.stderr)
            sys.exit(1)
        override_payload = parsed

    try:
        decision = evaluate_gate(
            score=args.score,
            operation=args.operation,
            now_utc_iso=args.now,
            override=override_payload,
        )
    except (TypeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(asdict(decision), indent=2))

def main(argv=None):
    parser = argparse.ArgumentParser(description="Leviathan Diagnostic CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # Snapshot Command
    snap_parser = subparsers.add_parser("snapshot", help="Run the AI Stability Snapshot")
    snap_group = snap_parser.add_mutually_exclusive_group(required=True)
    snap_group.add_argument("--interactive", action="store_true", help="Interactive terminal mode")
    snap_group.add_argument("--answers", type=str, help="Comma-separated 1 or 0 for the 15 questions")
    snap_parser.add_argument("--json", action="store_true", help="Output raw JSON")
    snap_parser.add_argument("--out-dir", type=str, help="Output directory for snapshot JSON")
    
    # Init-ledger Command
    ledger_parser = subparsers.add_parser("init-ledger", help="Initialize a causal ledger entry")
    ledger_parser.add_argument("incident_id", type=str, help="ID of the incident")
    ledger_parser.add_argument("--out-dir", type=str, help="Output directory for ledger")
    ledger_parser.add_argument("--now", type=str, help="Override UTC timestamp (ISO8601)")

    # Gate Command
    gate_parser = subparsers.add_parser("gate", help="Evaluate stability invariant gate")
    gate_parser.add_argument("score", type=int, help="Snapshot score")
    gate_parser.add_argument("operation", type=str, help="Operation name to evaluate")
    gate_parser.add_argument("--now", type=str, help="Override UTC timestamp (ISO8601)")
    gate_parser.add_argument(
        "--override-json",
        type=str,
        help="JSON object containing override ledger fields",
    )
    
    args = parser.parse_args(argv)
    
    if args.command == "snapshot":
        handle_snapshot(args)
    elif args.command == "init-ledger":
        handle_init_ledger(args)
    elif args.command == "gate":
        handle_gate(args)

if __name__ == "__main__":
    main()
