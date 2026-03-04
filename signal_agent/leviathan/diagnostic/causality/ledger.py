"""
Causal Ledger initialization and data operations.
Moved from causality CLI to establish a clean internal API.
"""
import datetime
import json
import pathlib

def init_ledger_entry(incident_id: str, write_dir: pathlib.Path | None = None, timestamp_override: str | None = None) -> int:
    """
    Initializes a new casual ledger entry for a specific incident.
    Returns 0 on success, 1 on failure.
    """
    module_dir = pathlib.Path(__file__).resolve().parent
    template_path = module_dir / "causal_ledger_entry.json"

    if not template_path.exists():
        print(f"Error: Template not found at {template_path}")
        return 1
        
    target_dir = write_dir.resolve() if write_dir else pathlib.Path.cwd()
    out_filename = target_dir / f"{incident_id}_causal_ledger.json"
    
    if out_filename.exists():
        print(f"Error: Ledger file already exists at {out_filename} - overwrite prevented.")
        return 1
        
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            template = json.load(f)
            
        template["incident_or_change_id"] = incident_id
        template["timestamp"] = timestamp_override or datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        with open(out_filename, "w", encoding="utf-8") as f:
            json.dump(template, f, indent=2)
            
        print(f"Initialized new causal ledger entry: {out_filename}")
        return 0
    except Exception as e:
        print(f"Failed to initialize ledger: {e}")
        return 1
