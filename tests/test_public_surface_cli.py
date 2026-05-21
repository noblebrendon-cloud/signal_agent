from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path


def _module():
    return importlib.import_module("app.public_surfaces.cli")


def _write_domain_profiles(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "version: 1",
                "approval_classes:",
                "  - human_public_review",
                "domain_profiles:",
                "  - domain_id: signal",
                "    lifecycle_state: active",
                "    approval_class: human_public_review",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_primitive_registry(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "primitive_id": "sp_signal",
                "invariant_refs": ["coherence_under_pressure"],
                "compatible_domains": ["signal"],
                "approval_class": "human_public_review",
            }
        )
        + "\n",
        encoding="utf-8",
    )


def test_cli_import_stays_out_of_capture_and_platform_code() -> None:
    sys.modules.pop("app.public_surfaces.cli", None)
    sys.modules.pop("app.hq.capture.router", None)
    sys.modules.pop("signal_agent.content.wtpu_channel", None)

    cli = _module()

    assert "app.hq.capture.router" not in sys.modules
    assert "signal_agent.content.wtpu_channel" not in sys.modules
    assert callable(cli.main)


def test_cli_default_example_config_renders_json(capsys) -> None:
    cli = _module()

    result = cli.main([])
    output = json.loads(capsys.readouterr().out)

    assert result == 0
    assert output["routable_domains"] == []
    assert output["quarantined_domains"] == ["mars_hill"]
    assert output["recommended_holds"]


def test_cli_explicit_paths_render_json(tmp_path: Path, capsys) -> None:
    cli = _module()
    domain_profiles = tmp_path / "domain_profiles.yaml"
    primitive_registry = tmp_path / "primitive_registry.jsonl"
    _write_domain_profiles(domain_profiles)
    _write_primitive_registry(primitive_registry)

    result = cli.main(
        [
            "--domain-profiles",
            str(domain_profiles),
            "--primitive-registry",
            str(primitive_registry),
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert result == 0
    assert output["routable_domains"] == ["signal"]
    assert output["quarantined_domains"] == []
    assert output["primitives_by_domain"] == {"signal": ["sp_signal"]}


def test_cli_malformed_primitive_registry_exits_nonzero(tmp_path: Path, capsys) -> None:
    cli = _module()
    domain_profiles = tmp_path / "domain_profiles.yaml"
    primitive_registry = tmp_path / "primitive_registry.jsonl"
    _write_domain_profiles(domain_profiles)
    primitive_registry.write_text('{"primitive_id": "broken"\n', encoding="utf-8")

    result = cli.main(
        [
            "--domain-profiles",
            str(domain_profiles),
            "--primitive-registry",
            str(primitive_registry),
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert result == 1
    assert output["clean"] is False
    assert output["error_type"] == "PublicSurfaceValidationError"
    assert "invalid_jsonl_row:1" in output["error"]
