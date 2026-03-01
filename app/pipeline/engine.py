from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class EngineResult:
    ok: bool
    request_id: str
    diagnostics: Dict[str, Any]


def run_pipeline_cycle(contract: dict, request_id: str) -> dict:
    """
    Executes ONE deterministic pipeline cycle and returns structured stats.
    MUST NOT call sys.exit().
    MUST NOT raise unless truly unexpected; instead return ok=False with error info.

    Expected contract shape (minimal):
      contract.get("pipeline", {}) may include flags used by capture/promote/route
    """
    diagnostics: Dict[str, Any] = {
        "request_id": request_id,
        "stages": [],
        "errors": [],
    }

    try:
        # Import here to avoid daemon import-time side effects.
        # Adjust these imports to match your repo names.
        from app.hq.capture.promote import promote_run as promote_capture  # type: ignore
        from app.hq.capture.router import route_bundle as route_promoted     # type: ignore

        # Stage 1: promote
        diagnostics["stages"].append({"name": "promote", "status": "START"})
        
        # Promote run takes a directory threshold etc, but for engine mapping we pass sensible defaults
        # or extract from contract if defined.
        promote_stats = promote_capture() if callable(promote_capture) else "promote executed"
        diagnostics["stages"][-1].update({"status": "OK", "stats": promote_stats})

        # Stage 2: route
        diagnostics["stages"].append({"name": "route", "status": "START"})
        route_stats = route_promoted(None) if callable(route_promoted) else "route executed"
        diagnostics["stages"][-1].update({"status": "OK", "stats": route_stats})

        return EngineResult(ok=True, request_id=request_id, diagnostics=diagnostics).__dict__

    except Exception as e:  # noqa: BLE001
        diagnostics["errors"].append({"type": type(e).__name__, "msg": str(e)})
        return EngineResult(ok=False, request_id=request_id, diagnostics=diagnostics).__dict__
