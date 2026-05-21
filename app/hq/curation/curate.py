"""Curation stages compiled artifacts into registered publishable outputs.

Boundary:
- `hq_capture` owns fragment capture, bundle assembly, and deciding when a bundle
  is ready for handoff.
- `hq_curation` owns deterministic staging, deduplication, artifact registry
  append, index refresh, and compiled-to-staged lifecycle registration after
  that handoff.
"""

import os
import shutil
import hashlib
import yaml
import json
import logging
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

from app.governor import enforce as governor_enforce
from app.utils.io_contract import append_jsonl_atomic, atomic_write_text
from app.hq.governance import (
    emit_transition_event,
    make_lifecycle_metadata,
    new_run_id,
    resolve_lane_for_route,
    validate_transition,
)

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
REGISTRY_PATH = REPO_ROOT / "data" / "artifact_registry.jsonl"
INDEX_PATH = REPO_ROOT / "data" / "INDEX_ARTIFACTS.md"
CONFIG_PATH = REPO_ROOT / "app" / "hq" / "curation" / "rules.yaml"


class CurationContractError(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _enforce_curate_governor() -> Optional[dict]:
    decision = governor_enforce(scope="curate.run")
    if decision.get("decision") == "BLOCK":
        return decision
    return None


def _resolve_repo_path(path_like: str | Path) -> Path:
    path = Path(path_like)
    if path.is_absolute():
        return path
    return (REPO_ROOT / path).resolve()


def _default_archive_path() -> Path:
    return (REPO_ROOT / "data" / "archive").resolve()


def _normalize_config_paths(config: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(config)
    routes = config.get("routes")
    if isinstance(routes, dict):
        normalized["routes"] = {
            name: str(_resolve_repo_path(raw_path))
            for name, raw_path in routes.items()
        }

    intake_roots = config.get("intake_roots")
    if isinstance(intake_roots, list):
        normalized["intake_roots"] = [str(_resolve_repo_path(root)) for root in intake_roots]

    return normalized


def load_config() -> Dict[str, Any]:
    if not CONFIG_PATH.exists():
        logger.warning(f"Config not found at {CONFIG_PATH}, utilizing defaults")
        return {}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return _normalize_config_paths(yaml.safe_load(f) or {})
    except Exception as e:
        logger.error(f"Error loading config: {e}, utilizing defaults")
        return {}

def get_file_hash(path):
    sha256_hash = hashlib.sha256()
    with open(path, "rb") as f:
        for byte_block in iter(lambda: f.read(65536), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def find_in_registry(file_hash):
    """
    Returns the canonical record if found, else None.
    Tolerates corrupt lines by skipping them.
    """
    if not REGISTRY_PATH.exists():
        return None
    
    with open(REGISTRY_PATH, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            try:
                record = json.loads(line)
                if record.get("sha256") == file_hash:
                    return record
            except json.JSONDecodeError:
                continue
    return None

def register_artifact(record):
    """
    Appends record to the registry through the shared atomic JSONL helper.
    """
    try:
        append_jsonl_atomic(REGISTRY_PATH, record)
    except Exception as e:
        logger.error(f"Failed to write to registry: {e}")
        # Critical failure if we can't log
        raise e
        
    update_index()

def _render_index(records):
    lines = [
        "# Artifact Index\n",
        "\n",
        "| Timestamp | Name | Kind | Size | Path |\n",
        "|---|---|---|---|---|\n",
    ]
    for r in records:
        lines.append(
            f"| {r.get('timestamp')} | {r.get('name')} | {r.get('kind')} | {r.get('size')} | {r.get('path')} |\n"
        )
    return "".join(lines)

def update_index():
    if not REGISTRY_PATH.exists():
        return
    
    records = []
    with open(REGISTRY_PATH, 'r', encoding="utf-8", errors="ignore") as f:
        for line in f:
            try:
                records.append(json.loads(line))
            except:
                continue
    
    # Sort by timestamp desc
    records.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    
    try:
        atomic_write_text(INDEX_PATH, _render_index(records))
    except Exception:
        logger.warning("Failed to update index markdown (non-critical)")

def sanitize_stem(stem):
    # Basic sanitization
    keep = "".join(c for c in stem if c.isalnum() or c in "._-")
    return keep.strip()


def _resolve_existing_output(existing: Dict[str, Any]) -> Path:
    existing_path = existing.get("path")
    if not existing_path:
        raise CurationContractError("registry_drift_missing_output")

    output_path = Path(existing_path)
    if not output_path.exists():
        raise CurationContractError("registry_drift_missing_output")

    return output_path


def _resolve_destination_root(config: Dict[str, Any], route_key: str) -> Path:
    routes = config.get("routes", {})
    dest_root = routes.get(route_key) or routes.get("archive")
    if dest_root:
        return Path(dest_root)
    return _default_archive_path()


def _publish_staged_artifact(source_path: Path, final_path: Path, expected_hash: str) -> Path:
    temp_path = final_path.with_name(f".tmp_{expected_hash}_{int(time.time() * 1000)}")
    if final_path.exists():
        raise CurationContractError("unregistered_existing_output")

    try:
        shutil.copy2(str(source_path), str(temp_path))
        os.replace(str(temp_path), str(final_path))
        if get_file_hash(final_path) != expected_hash:
            raise CurationContractError("integrity_check_failed")
        return final_path
    except Exception:
        if temp_path.exists():
            try:
                os.remove(str(temp_path))
            except OSError:
                pass
        raise


def _cleanup_input_file(source_path: Path, action_type: str) -> None:
    if action_type != "move":
        return
    try:
        os.remove(str(source_path))
    except Exception as e:
        logger.warning(f"Failed to remove input file {source_path}: {e}")

def curate_file(file_path, enforce_governor: bool = True):
    config: Dict[str, Any] = load_config()
    file_path = Path(file_path).resolve()
    run_id = new_run_id("curate")

    if enforce_governor:
        blocked = _enforce_curate_governor()
        if blocked is not None:
            return {
                "action": "blocked",
                "reason": blocked.get("reason"),
                "governor": blocked,
            }
    
    if not file_path.exists() or not file_path.is_file():
        logger.error(f"Invalid file: {file_path}")
        return {"action": "error", "reason": "not_found"}

    try:
        # 1. Hash (Content Addressable)
        file_hash = get_file_hash(file_path)
    except Exception as e:
        logger.error(f"Hashing failed: {e}")
        return {"action": "error", "reason": "hashing_failed"}

    # 2. Deduplication Policy A: Check Registry
    existing = find_in_registry(file_hash)
    if existing:
        try:
            existing_output = _resolve_existing_output(existing)
        except CurationContractError as e:
            logger.error(f"Registry drift detected for {file_hash}: {e.reason}")
            return {
                "action": "error",
                "reason": e.reason,
                "sha256": file_hash,
                "output_path": existing.get("path"),
                "route": existing.get("route"),
            }

        logger.info(f"DEDUP: {file_path.name} -> {existing_output}")
        return {
            "action": "deduped",
            "sha256": file_hash,
            "output_path": str(existing_output),
            "route": existing["route"],
        }

    # 3. Routing
    # Normalize extension for routing (case-insensitive)
    original_ext = file_path.suffix
    ext_lower = original_ext.lower()
    
    kind = "other"
    defaults: Dict[str, Any] = config.get("defaults", {})
    route_key = defaults.get("route", "archive")
    
    for k in config.get("kinds", []):
        if ext_lower in [e.lower() for e in k.get("ext", [])]:
            kind = k.get("kind")
            route_key = k.get("route")
            break
            
    dest_path = _resolve_destination_root(config, route_key)
    dest_path.mkdir(parents=True, exist_ok=True)
    
    # 4. Deterministic Naming: stem__hash.ext
    # Ensure stem + hash + ext
    stem = sanitize_stem(file_path.stem)
    # If file has multiple extensions (e.g. .tar.gz), pathlib .stem gives .tar
    # User requested: scan.final.v2.pdf -> "scan.final.v2"
    # Logic: name minus suffix is the stem? 
    # Actually pathlib stem is just name without last extension. 
    # "scan.final.v2.pdf" -> stem "scan.final.v2", suffix ".pdf". This works for standard usage.
    
    new_name = f"{stem}__{file_hash}{ext_lower}" # Normalize to lowercase ext per user option
    
    final_path = dest_path / new_name
    lane_id = resolve_lane_for_route(route_key, kind)
    transition_context = {
        "run_id": run_id,
        "module": "app.hq.curation.curate",
        "operation": "register_artifact",
        "source_path": str(file_path),
        "sha256": file_hash,
        "artifact_type": kind,
        "route_key": route_key,
        "final_path": str(final_path),
        "legacy_current_state": "compiled",
    }
    validation = validate_transition(
        current_state=None,
        next_state="staged",
        lane_id=lane_id,
        context=transition_context,
    )
    emit_transition_event(
        validation,
        run_id=run_id,
        envelope_id=file_hash,
        artifact_id=file_hash,
        context=transition_context,
    )
    if not validation.get("allowed"):
        logger.error(f"Transition gate rejected curate for {file_path}: {validation.get('reason')}")
        return {
            "action": "rejected",
            "reason": validation.get("reason"),
            "lane_id": lane_id,
            "run_id": run_id,
            "policy_result": validation.get("policy_result"),
        }
    
    action_type = config.get("defaults", {}).get("action", "move")
    
    try:
        final_path = _publish_staged_artifact(file_path, final_path, file_hash)
            
        # 6. Register
        record = {
            "timestamp": datetime.now().isoformat(),
            "run_id": run_id,
            "name": new_name,
            "original_name": file_path.name,
            "kind": kind,
            "sha256": file_hash,
            "size": final_path.stat().st_size,
            "path": str(final_path),
            "route": route_key,
            "lane_id": lane_id,
            "lifecycle": make_lifecycle_metadata(validation, final_state="staged"),
        }
        register_artifact(record)
        
        # 7. Cleanup Input if 'move'
        # Only delete input after successful registry
        _cleanup_input_file(file_path, action_type)
        
        logger.info(f"CREATED: {final_path}")
        return {
            "action": "created",
            "run_id": run_id,
            "sha256": file_hash,
            "output_path": str(final_path),
            "route": route_key,
            "lane_id": lane_id,
            "state": "staged",
        }

    except CurationContractError as e:
        logger.error(f"Failed to curate {file_path}: {e.reason}")
        return {"action": "error", "reason": e.reason}
    except Exception as e:
        logger.error(f"Failed to curate {file_path}: {e}")
        return {"action": "error", "reason": str(e)}

def curate_backfill(enforce_governor: bool = True):
    if enforce_governor:
        blocked = _enforce_curate_governor()
        if blocked is not None:
            return [{
                "action": "blocked",
                "reason": blocked.get("reason"),
                "governor": blocked,
            }]

    config = load_config()
    roots = config.get("intake_roots", [])
    results = []
    
    for root in roots:
        p = Path(root)
        if not p.exists(): continue
        
        # Walk
        for item in p.rglob("*"):
            if item.is_file():
                # Avoid processing our own output/staging if nested?
                # User config defines intake_roots.
                res = curate_file(item, enforce_governor=False)
                results.append(res)
                
    return results

if __name__ == "__main__":
    import argparse
    import sys
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", help="Path to file or directory to curate")
    parser.add_argument("--backfill", action="store_true", help="Process all intake roots")
    parser.add_argument("--no-governor", action="store_true", help="Disable Activation Governor enforcement")
    args = parser.parse_args()
    
    if args.backfill:
        res = curate_backfill(enforce_governor=not args.no_governor)
        print(json.dumps(res, indent=2))
    elif args.path:
        p = Path(args.path)
        if p.is_file():
            res = curate_file(p, enforce_governor=not args.no_governor)
            print(json.dumps(res, indent=2))
        elif p.is_dir():
             # Recurse dir
             final_res = []
             for item in p.rglob("*"):
                if item.is_file():
                    final_res.append(curate_file(item, enforce_governor=not args.no_governor))
             print(json.dumps(final_res, indent=2))
    else:
        print("Usage: curate.py --path <path> OR --backfill")
