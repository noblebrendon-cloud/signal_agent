from __future__ import annotations

import pytest

from shared.artifact_identity import artifact_display_name, normalize_artifact_ref


def test_normalize_artifact_ref_is_deterministic_for_filename_and_abstract_refs() -> None:
    filename_ref = normalize_artifact_ref("bundle_001.md")
    assert filename_ref == {
        "artifact_id": "bundle_001.md",
        "looks_like_filename": True,
        "extension": ".md",
    }
    assert normalize_artifact_ref("bundle_001.md") == filename_ref

    abstract_ref = normalize_artifact_ref("artifact_bundle_001")
    assert abstract_ref == {
        "artifact_id": "artifact_bundle_001",
        "looks_like_filename": False,
        "extension": None,
    }


def test_artifact_identity_rejects_missing_or_non_string_refs() -> None:
    with pytest.raises(ValueError, match="artifact_ref_required"):
        normalize_artifact_ref("")

    with pytest.raises(TypeError, match="artifact_ref_must_be_str"):
        normalize_artifact_ref(None)  # type: ignore[arg-type]


def test_artifact_display_name_uses_optional_path_label() -> None:
    assert artifact_display_name("artifact_bundle_001") == "artifact_bundle_001"
    assert (
        artifact_display_name("artifact_bundle_001", "artifacts/promoted/bundle_001.md")
        == "artifact_bundle_001 (bundle_001.md)"
    )
