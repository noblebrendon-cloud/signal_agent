from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
DOMAIN_EXAMPLE = REPO_ROOT / "config" / "public_surfaces" / "domain_profiles.example.yaml"
PRIMITIVE_EXAMPLE = REPO_ROOT / "config" / "public_surfaces" / "primitive_registry.example.jsonl"


def _module():
    return importlib.import_module("shared.public_surfaces")


def _domain_profile(**overrides: object) -> dict[str, object]:
    profile: dict[str, object] = {
        "domain_id": "domain_alpha",
        "lifecycle_state": "active",
        "approval_class": "human_public_review",
    }
    profile.update(overrides)
    return profile


def _primitive(**overrides: object) -> dict[str, object]:
    primitive: dict[str, object] = {
        "primitive_id": "sp_alpha",
        "invariant_refs": ["coherence_under_pressure"],
        "compatible_domains": ["signal"],
        "approval_class": "human_public_review",
    }
    primitive.update(overrides)
    return primitive


def test_public_surface_import_stays_out_of_capture_and_platform_code() -> None:
    sys.modules.pop("shared.public_surfaces", None)
    sys.modules.pop("app.hq.capture.router", None)
    sys.modules.pop("signal_agent.content.wtpu_channel", None)

    public_surfaces = _module()

    assert "app.hq.capture.router" not in sys.modules
    assert "signal_agent.content.wtpu_channel" not in sys.modules
    assert issubclass(public_surfaces.PublicSurfaceValidationError, ValueError)


def test_example_domain_profiles_load_and_quarantine_is_not_routable() -> None:
    public_surfaces = _module()

    profiles = public_surfaces.load_domain_profiles(DOMAIN_EXAMPLE)

    assert set(profiles) == {"letters_of_light", "mars_hill", "signal", "wtpu"}
    assert profiles["letters_of_light"]["lifecycle_state"] == "candidate"
    assert profiles["letters_of_light"]["approval_class"] == "human_high_trust_review"
    assert public_surfaces.is_domain_routable(profiles["letters_of_light"]) is False
    assert profiles["mars_hill"]["lifecycle_state"] == "quarantined"
    assert public_surfaces.is_domain_routable(profiles["mars_hill"]) is False


def test_active_domain_profile_is_routable() -> None:
    public_surfaces = _module()

    profile = _domain_profile()
    public_surfaces.validate_domain_profile(profile)

    assert public_surfaces.is_domain_routable(profile) is True


@pytest.mark.parametrize("field", ["domain_id", "lifecycle_state"])
def test_domain_profile_missing_required_fields_fail_closed(field: str) -> None:
    public_surfaces = _module()
    profile = _domain_profile()
    profile.pop(field)
    if field == "lifecycle_state":
        profile.pop("status", None)

    with pytest.raises(
        public_surfaces.PublicSurfaceValidationError,
        match=rf"missing_required_field:{field}",
    ):
        public_surfaces.validate_domain_profile(profile)


def test_domain_profile_rejects_unknown_approval_class() -> None:
    public_surfaces = _module()

    with pytest.raises(
        public_surfaces.PublicSurfaceValidationError,
        match="unknown_approval_class:auto_emit",
    ):
        public_surfaces.validate_domain_profile(_domain_profile(approval_class="auto_emit"))


def test_example_primitive_registry_loads_and_normalizes_compatible_domains() -> None:
    public_surfaces = _module()

    primitives = public_surfaces.load_primitive_registry(PRIMITIVE_EXAMPLE)

    assert [row["primitive_id"] for row in primitives] == [
        "sp_example_coherence_under_pressure",
        "sp_example_peace_not_denial",
    ]
    assert primitives[0]["compatible_domains"] == ["signal", "wtpu"]


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("primitive_id", "missing_required_field:primitive_id"),
        ("invariant_refs", "missing_required_field:invariant_refs"),
        ("compatible_domains", "missing_required_field:compatible_domains"),
    ],
)
def test_primitive_missing_required_fields_fail_closed(field: str, message: str) -> None:
    public_surfaces = _module()
    primitive = _primitive()
    primitive.pop(field)
    if field == "compatible_domains":
        primitive.pop("compatible_domain_ids", None)

    with pytest.raises(public_surfaces.PublicSurfaceValidationError, match=message):
        public_surfaces.validate_primitive(primitive)


def test_primitive_rejects_unknown_approval_class() -> None:
    public_surfaces = _module()

    with pytest.raises(
        public_surfaces.PublicSurfaceValidationError,
        match="unknown_approval_class:auto_emit",
    ):
        public_surfaces.validate_primitive(_primitive(approval_class="auto_emit"))


def test_primitive_registry_rejects_invalid_jsonl_row(tmp_path: Path) -> None:
    public_surfaces = _module()
    registry = tmp_path / "primitive_registry.jsonl"
    registry.write_text(
        json.dumps(_primitive()) + "\n" + '{"primitive_id": "broken"\n',
        encoding="utf-8",
    )

    with pytest.raises(
        public_surfaces.PublicSurfaceValidationError,
        match="invalid_jsonl_row:2",
    ):
        public_surfaces.load_primitive_registry(registry)
