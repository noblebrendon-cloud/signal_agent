"""
OIL Explanation -- Artifact Reporter (v0.4.1)

v0.4.1 adds:
  run_id: sha256(created_utc + inputs_digest)[:16]
    - Written to artifact envelope.
    - Used as stable identity for DIM deduplication.
  Artifact filename: incident_<UTC_compact>_<run_id>.json
    - Guarantees uniqueness even within the same second.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

OIL_VERSION = "0.9"
ARTIFACT_VERSION = "1"


def _utc_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _compute_run_id(created_utc: str, inputs_digest: str) -> str:
    """Derive a stable 16-char run identifier from (created_utc, inputs_digest).

    Deterministic: identical (created_utc, inputs_digest) always yields the
    same run_id. Provides uniqueness across artifacts even within the same second.
    """
    payload = created_utc + "|" + inputs_digest
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def compute_inputs_digest(
    events_dicts: list[dict],
    graph_dicts: dict[str, Any],
    impact_map: dict[str, str],
) -> str:
    """Compute a stable sha256 digest of the pipeline inputs.

    Returns 'sha256:<hex>'.
    """
    payload = {
        "events": sorted(events_dicts, key=lambda e: e.get("event_id", "")),
        "graph": {k: graph_dicts[k] for k in sorted(graph_dicts)},
        "impact_map": {k: impact_map[k] for k in sorted(impact_map)},
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def write_artifact(
    report: dict,
    artifacts_dir: Path,
    inputs_digest: str = "",
) -> tuple[Path, str]:
    """Atomically write a versioned artifact envelope.

    v0.4.1: Returns (artifact_path, run_id) so the caller can pass run_id
    to the memory store without recomputing. Filename now includes run_id:
      incident_<UTC_compact>_<run_id>.json

    Creates artifacts_dir if it does not exist.
    Uses tmp-then-rename for atomic write.
    """
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    created_utc = _utc_iso()
    compact_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = _compute_run_id(created_utc, inputs_digest)

    filename = f"incident_{compact_ts}_{run_id}.json"
    target = artifacts_dir / filename
    tmp = target.with_suffix(".json.tmp")

    envelope = {
        "artifact_version": ARTIFACT_VERSION,
        "oil_version": OIL_VERSION,
        "created_utc": created_utc,
        "run_id": run_id,
        "inputs_digest": inputs_digest,
        "report": report,
    }

    tmp.write_text(
        json.dumps(envelope, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    tmp.replace(target)
    return target, run_id
