from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest


def _contract_module():
    return importlib.import_module("shared.contract")


def test_contract_import_owns_exception_without_loading_router() -> None:
    sys.modules.pop("shared.contract", None)
    sys.modules.pop("app.hq.capture.router", None)

    contract = _contract_module()

    assert "app.hq.capture.router" not in sys.modules
    assert issubclass(contract.ContractResolutionError, RuntimeError)
    assert contract.ContractResolutionError.__module__ == "shared.contract"


def test_contract_resolves_registry_and_frontmatter_evidence(tmp_path: Path) -> None:
    contract = _contract_module()
    bundle = tmp_path / "bundle_registry.md"
    registry = tmp_path / "registry.jsonl"
    bundle.write_text("## Bundle\n", encoding="utf-8")
    registry.write_text(
        json.dumps(
            {
                "artifact_id": bundle.name,
                "state": "promoted",
                "path": str(bundle),
                "updated_at": "2026-05-21T00:00:00+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    registry_result = contract.resolve_bundle_contract(bundle, bundle.read_text(), registry)
    assert registry_result == {
        "lifecycle_state": "promoted",
        "contract_source": "registry",
        "routable": True,
        "confidence": "high",
    }

    frontmatter_result = contract.resolve_bundle_contract(
        tmp_path / "bundle_frontmatter.md",
        "---\nlifecycle_state: routed\n---\n\nbody\n",
        registry_path=tmp_path / "missing_registry.jsonl",
    )
    assert frontmatter_result == {
        "lifecycle_state": "routed",
        "contract_source": "frontmatter",
        "routable": True,
        "confidence": "medium",
    }


def test_contract_member_inference_is_not_routing_authority(tmp_path: Path) -> None:
    contract = _contract_module()

    result = contract.resolve_bundle_contract(
        tmp_path / "bundle_inferred.md",
        "## Sources\n- raw_2026-05-21T10-11-12_001Z.md\n",
        registry_path=tmp_path / "missing_registry.jsonl",
    )

    assert result == {
        "lifecycle_state": "promoted",
        "contract_source": "member_inference",
        "routable": False,
        "confidence": "low",
    }


def test_contract_raises_owned_error_when_evidence_is_missing(tmp_path: Path) -> None:
    contract = _contract_module()

    with pytest.raises(contract.ContractResolutionError, match="no resolvable lifecycle contract"):
        contract.resolve_bundle_contract(
            tmp_path / "bundle_missing.md",
            "## Bundle\n\nNo contract evidence.\n",
            registry_path=tmp_path / "missing_registry.jsonl",
        )
