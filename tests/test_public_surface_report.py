from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DOMAIN_EXAMPLE = REPO_ROOT / "config" / "public_surfaces" / "domain_profiles.example.yaml"
PRIMITIVE_EXAMPLE = REPO_ROOT / "config" / "public_surfaces" / "primitive_registry.example.jsonl"


def _module():
    return importlib.import_module("app.public_surfaces.report")


def _write_domain_profiles(path: Path, rows: str) -> None:
    path.write_text(
        "\n".join(
            [
                "version: 1",
                "approval_classes:",
                "  - human_public_review",
                "  - quarantined",
                "domain_profiles:",
                rows.rstrip(),
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_primitive_registry(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def _primitive(primitive_id: str, domains: list[str]) -> dict[str, object]:
    return {
        "primitive_id": primitive_id,
        "invariant_refs": ["coherence_under_pressure"],
        "compatible_domains": domains,
        "approval_class": "human_public_review",
    }


def test_report_import_stays_out_of_capture_and_platform_code() -> None:
    sys.modules.pop("app.public_surfaces.report", None)
    sys.modules.pop("app.hq.capture.router", None)
    sys.modules.pop("signal_agent.content.wtpu_channel", None)

    report = _module()

    assert "app.hq.capture.router" not in sys.modules
    assert "signal_agent.content.wtpu_channel" not in sys.modules
    assert callable(report.build_governance_report)


def test_example_report_summarizes_public_surface_readiness() -> None:
    report = _module()

    result = report.build_governance_report(
        domain_profiles_path=DOMAIN_EXAMPLE,
        primitive_registry_path=PRIMITIVE_EXAMPLE,
    )

    assert result == {
        "schema_version": "1.0",
        "summary": "public_surface_governance",
        "total_domains": 4,
        "routable_domains": [],
        "quarantined_domains": ["mars_hill"],
        "invalid_domains": [],
        "total_primitives": 2,
        "primitives_by_domain": {
            "letters_of_light": ["sp_example_peace_not_denial"],
            "mars_hill": [],
            "signal": [
                "sp_example_coherence_under_pressure",
                "sp_example_peace_not_denial",
            ],
            "wtpu": ["sp_example_coherence_under_pressure"],
        },
        "primitives_with_missing_domain_refs": [],
        "domains_without_primitives": ["mars_hill"],
        "approval_class_counts": {
            "human_high_trust_review": 1,
            "human_public_review": 2,
            "quarantined": 1,
        },
        "recommended_holds": [
            {
                "subject_type": "domain",
                "subject_id": "letters_of_light",
                "reason_code": "domain_not_routable",
                "detail": "lifecycle_state:candidate",
            },
            {
                "subject_type": "domain",
                "subject_id": "mars_hill",
                "reason_code": "domain_quarantined",
            },
            {
                "subject_type": "domain",
                "subject_id": "signal",
                "reason_code": "domain_not_routable",
                "detail": "lifecycle_state:candidate",
            },
            {
                "subject_type": "domain",
                "subject_id": "wtpu",
                "reason_code": "domain_not_routable",
                "detail": "lifecycle_state:candidate",
            },
        ],
    }


def test_unknown_primitive_domain_refs_are_reported_not_loader_failures(tmp_path: Path) -> None:
    report = _module()
    registry = tmp_path / "primitive_registry.jsonl"
    _write_primitive_registry(
        registry,
        [
            _primitive("sp_known_and_unknown", ["signal", "ghost_domain"]),
            _primitive("sp_known", ["wtpu"]),
        ],
    )

    result = report.build_governance_report(
        domain_profiles_path=DOMAIN_EXAMPLE,
        primitive_registry_path=registry,
    )

    assert result["primitives_with_missing_domain_refs"] == [
        {
            "primitive_id": "sp_known_and_unknown",
            "domain_ids": ["ghost_domain"],
        }
    ]
    assert {
        "subject_type": "primitive",
        "subject_id": "sp_known_and_unknown",
        "reason_code": "unknown_domain_refs",
        "domain_ids": ["ghost_domain"],
    } in result["recommended_holds"]


def test_invalid_domain_rows_remain_visible_while_valid_domains_report(tmp_path: Path) -> None:
    report = _module()
    domain_profiles = tmp_path / "domain_profiles.yaml"
    registry = tmp_path / "primitive_registry.jsonl"
    _write_domain_profiles(
        domain_profiles,
        """
  - domain_id: signal
    lifecycle_state: active
    approval_class: human_public_review
  - lifecycle_state: active
    approval_class: human_public_review
""",
    )
    _write_primitive_registry(registry, [_primitive("sp_signal", ["signal"])])

    result = report.build_governance_report(
        domain_profiles_path=domain_profiles,
        primitive_registry_path=registry,
    )

    assert result["total_domains"] == 2
    assert result["routable_domains"] == ["signal"]
    assert result["invalid_domains"] == [
        {
            "domain_id": "row_2",
            "row_index": 2,
            "error": "missing_required_field:domain_id",
        }
    ]
    assert result["approval_class_counts"] == {"human_public_review": 1}
    assert {
        "subject_type": "domain",
        "subject_id": "row_2",
        "reason_code": "invalid_domain_profile",
        "detail": "missing_required_field:domain_id",
    } in result["recommended_holds"]
