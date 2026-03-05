from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None  # type: ignore

from app.pipeline.engine import run_pipeline_cycle


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return round(float(val), 6)
    except (TypeError, ValueError):
        return None


def _atomic_write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _append_jsonl(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _load_contract(contract_path: Path) -> dict:
    if not contract_path.exists():
        raise FileNotFoundError(str(contract_path))
    raw = contract_path.read_text(encoding="utf-8")
    if contract_path.suffix.lower() in {".yaml", ".yml"}:
        if yaml is None:
            raise RuntimeError("pyyaml not installed but contract is yaml")
        return yaml.safe_load(raw) or {}
    return json.loads(raw)


@dataclass(frozen=True)
class EvalResult:
    ok: bool
    request_id: str
    contract_path: str
    preflight_path: str
    postflight_path: str
    contract_eval_path: str
    detail: Dict[str, Any]


def evaluate_cycle(contract_path: Path, kernel_snap: Any) -> dict:
    """
    Deterministically emits:
      data/state/preflight.json
      data/state/postflight.json
      data/state/contract_eval.json
    AND appends:
      data/state/contract_eval.jsonl  (for daemon tick-only contract evidence)

    Returns EvalResult dict.
    """
    contract = _load_contract(contract_path)
    request_id = contract.get("request_id") or f"req_{_utc_now_iso()}"

    state_dir = Path("data/state")
    preflight_p = state_dir / "preflight.json"
    postflight_p = state_dir / "postflight.json"
    contract_eval_p = state_dir / "contract_eval.json"
    contract_eval_jsonl_p = state_dir / "contract_eval.jsonl"

    from app.providers.registry import load_registry  # type: ignore
    registry = load_registry()
    provider_name = registry.get_default_provider_name()
    provider_hash = registry.get_provider_profile_hash(provider_name)

    provider_block = {
        "name": provider_name,
        "profile_hash": provider_hash,
    }

    preflight = {
        "ts_utc": _utc_now_iso(),
        "request_id": request_id,
        "contract_path": str(contract_path),
        "kernel": {
            "regime": getattr(kernel_snap, "regime", None),
        },
        "provider": provider_block,
    }
    _atomic_write_json(preflight_p, preflight)

    # Phase A: Kernel Telemetry Persistence
    kernel_history_p = state_dir / "kernel_history.jsonl"
    kernel_history_line = {
        "ts_utc": _utc_now_iso(),
        "request_id": request_id,
        "provider": provider_block,
        "kernel": {
            "regime": getattr(kernel_snap, "regime", None),
            "V_raw": _safe_float(getattr(kernel_snap, "V_raw", None)),
            "phi1": _safe_float(getattr(kernel_snap, "phi1", None)),
            "phi2": _safe_float(getattr(kernel_snap, "phi2", None)),
            "phi3": _safe_float(getattr(kernel_snap, "phi3", None)),
            "phi4": _safe_float(getattr(kernel_snap, "phi4", None)),
            "phi5": _safe_float(getattr(kernel_snap, "phi5", None)),
        },
        "engine_version": getattr(kernel_snap, "version", None) if hasattr(kernel_snap, "version") else None,
    }
    _append_jsonl(kernel_history_p, kernel_history_line)

    cycle_stats = run_pipeline_cycle(contract=contract, request_id=request_id)

    postflight = {
        "ts_utc": _utc_now_iso(),
        "request_id": request_id,
        "cycle_ok": bool(cycle_stats.get("ok")),
        "cycle_stats": cycle_stats,
    }
    _atomic_write_json(postflight_p, postflight)

    # Contract verification (minimal hook).
    # Tighten verify_contract signature later if needed; keep deterministic.
    try:
        from app.audit.runtime_audit import verify_contract  # type: ignore
        verify_ok, verify_detail = verify_contract(contract=contract, preflight=preflight, postflight=postflight)
    except Exception as e:  # noqa: BLE001
        verify_ok, verify_detail = False, {"error": {"type": type(e).__name__, "msg": str(e)}}

    eval_obj = {
        "ts_utc": _utc_now_iso(),
        "request_id": request_id,
        "contract_path": str(contract_path),
        "ok": bool(verify_ok),
        "detail": verify_detail,
        "provider": provider_block,
    }

    _atomic_write_json(contract_eval_p, eval_obj)
    _append_jsonl(contract_eval_jsonl_p, eval_obj)

    return EvalResult(
        ok=bool(verify_ok),
        request_id=request_id,
        contract_path=str(contract_path),
        preflight_path=str(preflight_p),
        postflight_path=str(postflight_p),
        contract_eval_path=str(contract_eval_p),
        detail=eval_obj,
    ).__dict__
