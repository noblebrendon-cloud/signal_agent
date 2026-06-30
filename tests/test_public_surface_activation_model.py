from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.letters_of_light.brand_registry import (
    get_brand,
    release_blockers,
    release_requirements_payload,
    safe_brand_metadata,
)
from app.letters_of_light.release import create_release_candidate, release_target_blockers


REPO_ROOT = Path(__file__).resolve().parents[1]
BEL_CAMPAIGN_ROOT = REPO_ROOT / "data" / "state" / "governed_publishing" / "BEL-V010-PUBLIC-LAUNCH"


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _surface(brand_id: str, surface_ref: str) -> dict:
    return get_brand(brand_id)["destination_surfaces"][surface_ref]


def test_brc_facebook_linkedin_and_threads_are_visible_but_not_publishable() -> None:
    brand = get_brand("brendon_r_coleman")
    surfaces = brand["destination_surfaces"]

    for surface_ref, constraints in {
        "facebook": ("longer text post", "link post"),
        "linkedin": ("professional post", "document-style note"),
        "threads": ("short-form conversational post", "short conversational thread"),
    }.items():
        surface = surfaces[surface_ref]
        assert surface["status"] == "configured_manual_publish"
        assert surface["manual_publication_possible"] is True
        assert surface["direct_system_publication_allowed"] is False
        assert surface["adapter_exists"] is False
        assert surface["credentials_exist"] is False
        assert surface["credential_state"] == "none"
        assert surface["public_url"] == ""
        assert surface["platform_account_id"] == ""
        assert set(constraints).issubset(set(surface["content_constraints"]))
        assert brand["available_release_targets"][surface_ref] is False
        assert release_blockers(brand, target=surface_ref, output_type="social")


def test_brc_existing_site_and_x_behavior_is_unchanged() -> None:
    brand = get_brand("brendon_r_coleman")
    targets = brand["available_release_targets"]

    assert targets["site"] is True
    assert targets["youtube"] is True
    assert targets["x"] is True
    assert targets["facebook"] is False
    assert targets["linkedin"] is False
    assert targets["threads"] is False

    site = _surface("brendon_r_coleman", "site")
    assert site["status"] == "publish_enabled"
    assert site["public_url"] == "https://brendonrcoleman.com"
    assert site["adapter_ref"] == "release_site"
    assert site["adapter_exists"] is True

    x_surface = _surface("brendon_r_coleman", "x")
    assert x_surface["status"] == "configured_manual_publish"
    assert x_surface["direct_system_publication_allowed"] is False
    assert x_surface["adapter_exists"] is False


def test_csg_candidate_surfaces_are_provisioning_only_without_invented_public_facts() -> None:
    brand = get_brand("clarity_systems_group")

    assert brand["status"] == "internal_only"
    assert brand["approval_rules"]["allow_public_publish"] is False
    assert all(value is False for value in brand["available_release_targets"].values())
    assert brand["brand_identity"] == {
        "identity_type": "business_legal_operating_identity",
        "display_name": "Clarity Systems Group",
        "public_service_offering_claims_configured": False,
        "public_domain_configured": False,
        "public_contact_configured": False,
    }

    expected = {"csg_site", "csg_linkedin", "csg_facebook", "csg_x", "csg_threads"}
    assert set(brand["destination_surfaces"]) == expected
    for surface in brand["destination_surfaces"].values():
        assert surface["status"] in {"draft_only", "provisioning_required"}
        assert surface["public_url"] == ""
        assert surface["platform_account_id"] == ""
        assert surface["adapter_ref"] == ""
        assert surface["adapter_exists"] is False
        assert surface["credential_state"] == "none"
        assert surface["credentials_exist"] is False
        assert surface["manual_publication_possible"] is False
        assert surface["direct_system_publication_allowed"] is False


def test_destination_surfaces_are_exposed_without_credentials_or_secret_fields() -> None:
    metadata = safe_brand_metadata("brendon_r_coleman")
    requirements = release_requirements_payload("brendon_r_coleman", output_type="social")

    assert {"facebook", "linkedin", "threads"}.issubset(metadata["destination_surfaces"])
    assert {"facebook", "linkedin", "threads"}.issubset(requirements["destination_surfaces"])

    serialized = json.dumps({"metadata": metadata, "requirements": requirements}).lower()
    for forbidden in (
        "credential_profile_key",
        "access_token",
        "refresh_token",
        "client_secret",
        "api_key",
        "password",
    ):
        assert forbidden not in serialized


def test_configured_destination_does_not_bypass_release_target_gates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SIGNAL_AGENT_ROOT", str(tmp_path))
    letter_id = "brc_manual_surface_gate"
    letter_dir = tmp_path / "data" / "state" / "letters_of_light" / letter_id
    video = letter_dir / "final.mp4"
    visual = letter_dir / "visual.png"
    video.parent.mkdir(parents=True, exist_ok=True)
    video.write_bytes(b"fake mp4")
    visual.write_bytes(b"fake png")

    _write_json(
        letter_dir / "letter.json",
        {
            "letter_id": letter_id,
            "theme": "surface-gate",
            "title": "Surface Gate",
            "text": "Draft body.",
            "video_path": str(video),
            "visual_path": str(visual),
            "audio_path": "",
            "music_path": "",
            "lifecycle_state": "registered",
            "evaluation": {"decision": "accept", "total": 27, "audio_alignment": 4},
            "metadata": {
                "brand_id": "brendon_r_coleman",
                "brand_version": "1",
                "output_type": "social",
                "release_targets": {
                    "facebook": True,
                    "linkedin": True,
                    "threads": True,
                    "x": True,
                },
            },
        },
    )
    _write_json(letter_dir / "routing.json", {"facebook": {"message": "Draft body."}, "x": {"tweets": ["Draft body."]}})
    _write_json(letter_dir / "interaction.json", {"questions": []})

    release = create_release_candidate(letter_id)

    assert release["targets"]["facebook"]["enabled"] is False
    assert release["targets"]["x"]["enabled"] is True
    for target in ("facebook", "linkedin", "threads"):
        blockers = release_target_blockers(letter_id, target)
        assert blockers
        assert any(f"does not allow {target} releases" in blocker for blocker in blockers)


def test_existing_build_evidence_library_campaign_derivatives_remain_draft_unapproved_and_ineligible() -> None:
    campaign_path = BEL_CAMPAIGN_ROOT / "campaign.json"
    if not campaign_path.exists():
        pytest.skip("local Build Evidence Library campaign state is not present")

    campaign = json.loads(campaign_path.read_text(encoding="utf-8"))

    assert campaign["release_eligible"] is False
    assert campaign["approval_status"] == "unapproved"
    derivatives = campaign["derivatives"]
    assert derivatives

    for derivative in derivatives:
        assert derivative["release_eligible"] is False
        assert derivative["review_status"] == "unreviewed"
        letter = json.loads((REPO_ROOT / derivative["draft_location"]).read_text(encoding="utf-8"))
        metadata = letter["metadata"]
        assert letter["lifecycle_state"] == "draft"
        assert metadata["release_eligible"] is False
        assert metadata["approval_status"] == "unapproved"
        assert metadata["publication_state"] == "not_started"
