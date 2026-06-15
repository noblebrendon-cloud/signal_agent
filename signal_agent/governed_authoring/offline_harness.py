from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .prototype_bridge import (
    PROTOTYPE_BRIDGE_SCHEMA_VERSION,
    PROTOTYPE_RESULT_SCHEMA_VERSION,
    backend_result_to_prototype_result,
    bridge_prototype_packet,
)
from .runtime import GovernedAuthoringRuntime


OFFLINE_VERIFICATION_SCHEMA_VERSION = "governed_authoring.offline_verification.v1"
SOURCE_PACKET_SCHEMA_VERSION = "governed_authoring.source_packet.v1"


def load_static_export_packet(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _as_mapping(value: Any) -> dict[str, Any]:
    return value if type(value) is dict else {}


def static_export_to_bridge_packet(packet: dict[str, Any]) -> dict[str, Any]:
    payload = _as_mapping(packet)
    schema_version = payload.get("schema_version")
    if schema_version == PROTOTYPE_BRIDGE_SCHEMA_VERSION and type(payload.get("source_packet")) is dict:
        return {
            "schema_version": PROTOTYPE_BRIDGE_SCHEMA_VERSION,
            "source_packet": dict(payload["source_packet"]),
            "bridge_issues": list(payload.get("bridge_issues") or []),
        }
    if schema_version == SOURCE_PACKET_SCHEMA_VERSION:
        return {
            "schema_version": PROTOTYPE_BRIDGE_SCHEMA_VERSION,
            "source_packet": dict(payload),
            "bridge_issues": [],
        }
    return bridge_prototype_packet(payload)


def run_offline_verification(
    static_export_packet: dict[str, Any],
    *,
    canonical_ledger_path: Path | None = None,
) -> dict[str, Any]:
    bridge_packet = static_export_to_bridge_packet(static_export_packet)
    runtime = GovernedAuthoringRuntime(canonical_ledger_path=canonical_ledger_path)
    backend_result = runtime.run(bridge_packet["source_packet"])
    static_import_packet = backend_result_to_prototype_result(backend_result)
    return {
        "schema_version": OFFLINE_VERIFICATION_SCHEMA_VERSION,
        "static_export_schema_version": _as_mapping(static_export_packet).get("schema_version", ""),
        "bridge_packet": bridge_packet,
        "source_packet": bridge_packet["source_packet"],
        "bridge_issues": list(bridge_packet["bridge_issues"]),
        "backend_result": backend_result.to_dict(),
        "output_manifest": backend_result.output_manifest.to_dict(),
        "static_import_packet": static_import_packet,
    }


def run_offline_verification_file(
    static_export_path: Path,
    *,
    canonical_ledger_path: Path | None = None,
) -> dict[str, Any]:
    return run_offline_verification(
        load_static_export_packet(static_export_path),
        canonical_ledger_path=canonical_ledger_path,
    )


def write_static_import_packet(path: Path, result: dict[str, Any]) -> None:
    static_import_packet = _as_mapping(result).get("static_import_packet")
    if _as_mapping(static_import_packet).get("schema_version") != PROTOTYPE_RESULT_SCHEMA_VERSION:
        raise ValueError("offline verification result does not contain a static import packet")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(static_import_packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
