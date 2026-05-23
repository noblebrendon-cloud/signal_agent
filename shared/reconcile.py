"""
shared/reconcile.py — Reconciliation report for artifact state consistency.
"""
import json
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional

from shared.state_registry import _default_registry_path
from shared.events import _default_event_log_path


def reconciliation_report(
    registry_path: Optional[Path] = None,
    event_log_path: Optional[Path] = None,
) -> Dict[str, Any]:
    reg_target = registry_path or _default_registry_path()
    evt_target = event_log_path or _default_event_log_path()

    issues = []
    reg_entries_count = 0
    evt_entries_count = 0
    missing_fs = 0
    path_mismatches = 0
    content_mismatches = 0

    if evt_target.exists():
        try:
            for raw_line in evt_target.read_text(encoding="utf-8").splitlines():
                if raw_line.strip():
                    evt_entries_count += 1
        except OSError:
            pass

    registry_state = {}
    if reg_target.exists():
        try:
            for raw_line in reg_target.read_text(encoding="utf-8").splitlines():
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    entry = json.loads(raw_line)
                    reg_entries_count += 1
                    if "artifact_id" in entry:
                        registry_state[entry["artifact_id"]] = entry
                except json.JSONDecodeError:
                    continue
        except OSError:
            pass

    for aid, entry in registry_state.items():
        state = entry.get("state")
        path_str = entry.get("path")
        expected_hash = entry.get("sha256")

        if not path_str:
            missing_fs += 1
            issues.append({
                "artifact_id": aid,
                "issue_type": "missing_filesystem_artifact",
                "registry_state": state,
                "registry_path": None,
                "filesystem_exists": False,
                "details": {"reason": "path missing in registry"},
            })
            continue

        p_obj = Path(path_str)
        exists = p_obj.exists()

        if not exists:
            missing_fs += 1
            issues.append({
                "artifact_id": aid,
                "issue_type": "missing_filesystem_artifact",
                "registry_state": state,
                "registry_path": path_str,
                "filesystem_exists": False,
                "details": {"reason": "file not found"},
            })
            if state == "routed":
                path_mismatches += 1
            continue

        if expected_hash:
            try:
                content_hash = hashlib.sha256(p_obj.read_bytes()).hexdigest()
                if content_hash != expected_hash:
                    content_mismatches += 1
                    issues.append({
                        "artifact_id": aid,
                        "issue_type": "content_mismatch",
                        "registry_state": state,
                        "registry_path": path_str,
                        "filesystem_exists": True,
                        "details": {"expected_hash": expected_hash, "actual_hash": content_hash},
                    })
            except OSError:
                pass

    return {
        "summary": {
            "registry_entries": reg_entries_count,
            "event_entries": evt_entries_count,
            "missing_filesystem_artifacts": missing_fs,
            "state_path_mismatches": path_mismatches,
            "content_mismatches": content_mismatches,
        },
        "issues": issues,
    }
