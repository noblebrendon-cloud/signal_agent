"""
shared/coherence.py — Temporal coherence guard for artifact state.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, Optional

from shared.state_registry import get_state


class CoherenceError(RuntimeError):
    pass


def _build_result(
    artifact_id: Optional[str],
    expected_state: Optional[str],
    registry_found: bool,
    registry_state: Optional[str],
    registry_path: Optional[str],
    filesystem_exists: bool,
    coherent: bool,
    reason: str,
) -> Dict[str, Any]:
    from shared.result_schemas import make_coherence_result
    return make_coherence_result(
        artifact_id=artifact_id,
        expected_state=expected_state,
        registry_found=registry_found,
        registry_state=registry_state,
        registry_path=registry_path,
        filesystem_exists=filesystem_exists,
        coherent=coherent,
        reason=reason,
    )


def check_artifact_coherence(
    artifact_id: str,
    expected_state: Optional[str] = None,
    expected_hash: Optional[str] = None,
    registry_path: Optional[Path] = None,
) -> Dict[str, Any]:
    entry = get_state(artifact_id, registry_path=registry_path)
    if not entry:
        return _build_result(
            artifact_id=artifact_id,
            expected_state=expected_state,
            registry_found=False,
            registry_state=None,
            registry_path=None,
            filesystem_exists=False,
            coherent=False,
            reason="missing_registry_entry",
        )

    reg_state = entry.get("state")
    reg_path = entry.get("path")
    
    if expected_state and reg_state != expected_state:
        fs_exists = bool(reg_path and Path(reg_path).exists())
        return _build_result(
            artifact_id=artifact_id,
            expected_state=expected_state,
            registry_found=True,
            registry_state=reg_state,
            registry_path=reg_path,
            filesystem_exists=fs_exists,
            coherent=False,
            reason="state_mismatch",
        )

    if not reg_path:
        return _build_result(
            artifact_id=artifact_id,
            expected_state=expected_state,
            registry_found=True,
            registry_state=reg_state,
            registry_path=None,
            filesystem_exists=False,
            coherent=False,
            reason="missing_filesystem_artifact",
        )

    p_obj = Path(reg_path)
    if not p_obj.exists():
        return _build_result(
            artifact_id=artifact_id,
            expected_state=expected_state,
            registry_found=True,
            registry_state=reg_state,
            registry_path=reg_path,
            filesystem_exists=False,
            coherent=False,
            reason="missing_filesystem_artifact",
        )

    if expected_hash:
        try:
            content_hash = hashlib.sha256(p_obj.read_bytes()).hexdigest()
            if content_hash != expected_hash:
                return _build_result(
                    artifact_id=artifact_id,
                    expected_state=expected_state,
                    registry_found=True,
                    registry_state=reg_state,
                    registry_path=reg_path,
                    filesystem_exists=True,
                    coherent=False,
                    reason="content_mismatch",
                )
        except OSError:
            return _build_result(
                artifact_id=artifact_id,
                expected_state=expected_state,
                registry_found=True,
                registry_state=reg_state,
                registry_path=reg_path,
                filesystem_exists=False,
                coherent=False,
                reason="missing_filesystem_artifact",
            )

    return _build_result(
        artifact_id=artifact_id,
        expected_state=expected_state,
        registry_found=True,
        registry_state=reg_state,
        registry_path=reg_path,
        filesystem_exists=True,
        coherent=True,
        reason="coherent",
    )


def check_path_coherence(
    artifact_path: str | Path,
    expected_state: Optional[str] = None,
    expected_hash: Optional[str] = None,
    registry_path: Optional[Path] = None,
) -> Dict[str, Any]:
    p = Path(artifact_path)
    artifact_id = p.name
    return check_artifact_coherence(
        artifact_id=artifact_id,
        expected_state=expected_state,
        expected_hash=expected_hash,
        registry_path=registry_path,
    )
