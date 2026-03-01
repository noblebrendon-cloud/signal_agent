"""CLI for the leviathan.causality_first_class.v1 module."""
import argparse
import datetime
import json
import pathlib
import sys

def open_ledger_entry(incident_id: str):
    """Initializes a new casual ledger entry for a specific incident."""
    module_dir = pathlib.Path(__file__).resolve().parent
    template_path = module_dir / "causal_ledger_entry.json"

    if not template_path.exists():
        print(f"Error: Template not found at {template_path}", file=sys.stderr)
        return 1
        
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            template = json.load(f)
            
        template["incident_or_change_id"] = incident_id
        template["timestamp"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        out_filename = f"{incident_id}_causal_ledger.json"
        
        with open(out_filename, "w", encoding="utf-8") as f:
            json.dump(template, f, indent=2)
            
        print(f"Initialized new causal ledger entry: {out_filename}")
        return 0
    except Exception as e:
        print(f"Failed to initialize ledger: {e}", file=sys.stderr)
        return 1

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Leviathan Causality Diagnostic CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    init_parser = subparsers.add_parser("init-ledger", help="Open a new ledger entry from an incident_id")
    init_parser.add_argument("incident_id", type=str, help="ID of the incident or change")
    
    args = parser.parse_args(argv)
    
    if args.command == "init-ledger":
        return open_ledger_entry(args.incident_id)
        
    return 0

if __name__ == "__main__":
    sys.exit(main())
