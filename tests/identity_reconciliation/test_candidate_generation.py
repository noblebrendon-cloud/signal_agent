from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from signal_agent.identity_reconciliation import generate_identity_candidates
from signal_agent.identity_reconciliation.artifacts import verify_sealed
from signal_agent.identity_reconciliation.policy import normalize_comparison_value

from .conftest import FIXED_CLOCK, read_json, tree


def _records(path: Path) -> dict[str, dict]:
    return {
        item["relationship_record_id"]: item
        for item in (
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
        )
    }


def test_exact_attribute_policy_generates_five_expected_candidates(candidate_run) -> None:
    result, source_runs = candidate_run
    assert result.success is True
    assert (result.candidate_count, result.proposed_count, result.conflicting_count) == (
        5,
        4,
        1,
    )
    linkedin = _records(source_runs["linkedin"] / "01_normalized/relationship_records.jsonl")
    candidates = [read_json(path) for path in result.candidate_paths]
    by_name = {}
    for candidate in candidates:
        record_id = candidate["left_identity_reference"]["relationship_record_ids"][0]
        by_name.setdefault(linkedin[record_id]["person"]["display_name"], []).append(candidate)
    assert by_name["Avery Stone"][0]["status"] == "conflicting"
    assert by_name["Jordan Lee"][0]["status"] == "proposed"
    assert by_name["Casey R. Morgan"][0]["status"] == "proposed"
    assert len(by_name["Rowan Pine"]) == 2
    assert all(item["status"] == "proposed" for item in by_name["Rowan Pine"])
    assert "Taylor Reed" not in by_name
    casey_path = next(
        path
        for path in result.evidence_bundle_paths
        if read_json(path)["left_identity_reference"]["relationship_record_ids"][0]
        == by_name["Casey R. Morgan"][0]["left_identity_reference"][
            "relationship_record_ids"
        ][0]
    )
    casey_bundle = read_json(casey_path)
    assert {
        item["match_representation"]
        for item in casey_bundle["comparison_signals"]
        if item["signal_type"] == "name_exact"
    } == {"first_last_to_display_name_exact"}


def test_candidate_tree_is_deterministic_and_source_runs_are_unchanged(
    tmp_path: Path, completed_source_runs: dict[str, Path]
) -> None:
    source_before = {
        name: tree(completed_source_runs[name])
        for name in ("linkedin", "interaction")
    }
    policy = completed_source_runs["repository"] / (
        "config/identity_reconciliation/linkedin_interaction_attribute_v1.json"
    )
    first = generate_identity_candidates(
        completed_source_runs["linkedin"],
        completed_source_runs["interaction"],
        tmp_path / "first-candidates",
        policy,
        lambda: FIXED_CLOCK,
    )
    second = generate_identity_candidates(
        completed_source_runs["linkedin"],
        completed_source_runs["interaction"],
        tmp_path / "second-candidates",
        policy,
        lambda: FIXED_CLOCK,
    )
    assert tree(first.run_root) == tree(second.run_root)
    assert source_before == {
        name: tree(completed_source_runs[name])
        for name in ("linkedin", "interaction")
    }
    assert not (first.run_root / ".staging").exists()
    assert verify_sealed(read_json(first.manifest_path), "manifest_hash")


def test_candidate_identity_excludes_clock_and_normalization_is_exact_only(
    tmp_path: Path, completed_source_runs: dict[str, Path]
) -> None:
    policy = completed_source_runs["repository"] / (
        "config/identity_reconciliation/linkedin_interaction_attribute_v1.json"
    )
    first = generate_identity_candidates(
        completed_source_runs["linkedin"],
        completed_source_runs["interaction"],
        tmp_path / "clock-one",
        policy,
        lambda: FIXED_CLOCK,
    )
    second = generate_identity_candidates(
        completed_source_runs["linkedin"],
        completed_source_runs["interaction"],
        tmp_path / "clock-two",
        policy,
        lambda: "2026-08-04T12:00:00Z",
    )
    assert [path.stem for path in first.candidate_paths] == [
        path.stem for path in second.candidate_paths
    ]
    assert [path.stem for path in first.evidence_bundle_paths] == [
        path.stem for path in second.evidence_bundle_paths
    ]
    assert tree(first.run_root) != tree(second.run_root)
    assert normalize_comparison_value("  CASEY\u3000Morgan  ") == "casey morgan"
    assert normalize_comparison_value("Casey-Morgan") == "casey-morgan"
    assert normalize_comparison_value("Morgan, Casey") == "morgan, casey"
    assert normalize_comparison_value("C. Morgan") == "c. morgan"


def test_artifacts_validate_and_omit_prohibited_values(candidate_run) -> None:
    result, source_runs = candidate_run
    repository = source_runs["repository"]
    schemas = {
        "01_evidence": read_json(
            repository
            / "schemas/identity_reconciliation/identity_evidence_bundle.v1.schema.json"
        ),
        "02_candidates": read_json(
            repository / "schemas/identity_reconciliation/identity_candidate.v1.schema.json"
        ),
        "05_receipts": read_json(
            repository
            / "schemas/identity_reconciliation/identity_reconciliation_manifest.v1.schema.json"
        ),
    }
    source_text = (
        (source_runs["linkedin"] / "00_original/Connections.csv").read_text("utf-8")
        + (source_runs["interaction"] / "00_original/interaction_events.jsonl").read_text(
            "utf-8"
        )
    )
    prohibited = [
        "shared@example.test",
        "linkedin.com/in/",
        '"actor_id"',
        '"event_id"',
        '"thread_id"',
        '"text"',
        "hmac-sha256:",
        "Avery Stone",
        "Jordan Lee",
        "Casey Morgan",
        "Atlas Systems",
    ]
    assert source_text
    for relative, payload in tree(result.run_root).items():
        text = payload.decode("utf-8")
        assert all(value not in text for value in prohibited), relative
        if relative.startswith("01_evidence/"):
            Draft202012Validator(schemas["01_evidence"]).validate(json.loads(text))
        elif relative.startswith("02_candidates/"):
            Draft202012Validator(schemas["02_candidates"]).validate(json.loads(text))
        elif relative.startswith("05_receipts/"):
            Draft202012Validator(schemas["05_receipts"]).validate(json.loads(text))
    for path in result.evidence_bundle_paths:
        bundle = read_json(path)
        compatibility = bundle["protection_compatibility"]
        assert compatibility["comparable"] is False
        assert compatibility["verified_key_material_domain"] is False
        assert compatibility["left_domain"]["key_id"] != compatibility[
            "right_domain"
        ]["key_id"]
        assert compatibility["token_values_compared"] is False
        assert bundle["privacy"] == {
            "clear_identifiers_read": False,
            "clear_identifiers_serialized": False,
            "protected_token_values_serialized": False,
            "compared_attribute_values_serialized": False,
            "reversible_value_digests_serialized": False,
            "raw_interaction_text_read": False,
        }
