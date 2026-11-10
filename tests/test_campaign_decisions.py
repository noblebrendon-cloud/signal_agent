"""Behavioral contracts for campaign proposals, evidence, and source integrity."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
import pytest
from referencing import Registry, Resource

from signal_agent.campaigns.core import (
    CampaignValidationError,
    evaluate_campaign,
    load_principles,
    validate_campaign,
)


ROOT = Path(__file__).resolve().parents[1]
EVALUATED_AT = "2026-11-10T00:00:00Z"
SOURCE_TEXT = (
    "  A familiar question can help a reader enter an explanation.\n"
    "That is a working hypothesis, not evidence that the explanation changed behavior.\n"
    "Keep this qualification in every derivative. — Source note\n"
)
QUALIFIED_CLAIM = (
    "A familiar question may help a reader enter an explanation; "
    "the campaign has not established a causal effect on behavior."
)


def campaign_context() -> dict:
    """A fresh first-campaign input with real source text and explicit editorial review."""
    return {
        "schema_version": "campaign_context.v1",
        "campaign_id": "campaign.test.source-fidelity",
        "title": "A bounded explanation experiment",
        "purpose": "Help a reader understand the source without overstating its claim.",
        "phase": "planned",
        "principle_ids": ["messaging", "gap"],
        "constraints": ["Preserve the source qualification in every derivative."],
        "sources": [
            {
                "source_id": "source.test.essay.v1",
                "text": SOURCE_TEXT,
                "uri": "https://example.invalid/source/essay-v1",
                "content_hash": "sha256:" + hashlib.sha256(SOURCE_TEXT.encode("utf-8")).hexdigest(),
                "evidence_refs": ["evidence:source.essay.v1"],
            }
        ],
        "claims": [
            {
                "claim_id": "claim.test.qualified",
                "statement": QUALIFIED_CLAIM,
                "status": "qualified",
                "evidence_refs": ["evidence:source.essay.v1"],
            }
        ],
        "review": {
            "mission": "aligned",
            "source_fidelity": "preserved",
            "by": "editorial-review:test-fixture",
            "reason": "The proposed explanation retains the source qualification.",
            "evidence_refs": ["evidence:source.essay.v1"],
        },
        "observations": [],
        "evaluation_plan": None,
        "requested_outputs": [
            {
                "output_id": "output.test.explanation",
                "kind": "short_post",
                "description": "Prepare one short explanation retaining the source qualification.",
            }
        ],
    }


def observation(number: int, **changes: object) -> dict:
    item = {
        "observation_id": f"observation.test.{number}",
        "variant_id": f"variant.test.{number}",
        "kind": "repeat_value",
        "summary": "A reader independently described the qualified source meaning as useful.",
        "source_ref": f"evidence:audience-response.{number}",
        "observed_at": "2026-11-08T12:00:00Z",
        "platform": "test-platform",
        "format": "short-explanation",
        "verification": "verified",
        "verified_by": "reviewer:test-fixture",
        "exposures": 200,
        "metric": {"name": "useful_responses", "numerator": 10, "denominator": 200},
    }
    item.update(changes)
    return item


def repeated_evidence_campaign() -> dict:
    campaign = campaign_context()
    campaign["phase"] = "reviewing"
    campaign["principle_ids"] = ["repeated_offender", "consistency"]
    campaign["evaluation_plan"] = {
        "window_start": "2026-11-07T00:00:00Z",
        "window_end": "2026-11-09T00:00:00Z",
        "platform": "test-platform",
        "format": "short-explanation",
        "minimum_observations": 2,
        "minimum_exposures": 300,
        "minimum_independent_variants": 2,
    }
    campaign["observations"] = [observation(1), observation(2)]
    return campaign


def campaign_lineage() -> dict:
    return {
        "parent_campaign_digest": "sha256:" + "a" * 64,
        "parent_decision_id": "campaign_decision." + "b" * 64,
        "parent_variant_ids": ["variant.previous.explanation"],
        "corrected_claim_ids": ["claim.previous.overstated"],
        "change_note": "Preserve the corrected qualification and identify the preceding variant.",
    }


def assert_schema(instance: dict, schema_version: str) -> None:
    candidates = []
    resources = []
    schema_paths = (
        path
        for directory in ("campaigns", "governed_authoring")
        for path in (ROOT / "schemas" / directory).rglob("*.schema.json")
    )
    for path in schema_paths:
        schema = json.loads(path.read_text(encoding="utf-8"))
        uri = path.resolve().as_uri()
        schema = {**schema, "$id": uri}
        resources.append((uri, Resource.from_contents(schema)))
        if schema.get("properties", {}).get("schema_version", {}).get("const") == schema_version:
            candidates.append(schema)
    assert len(candidates) == 1, f"Expected one published schema for {schema_version!r}."
    Draft202012Validator.check_schema(candidates[0])
    registry = Registry().with_resources(resources)
    Draft202012Validator(candidates[0], registry=registry, format_checker=FormatChecker()).validate(instance)


def test_first_campaign_can_propose_a_test_without_manufacturing_results_or_authority() -> None:
    decision = evaluate_campaign(campaign_context(), evaluated_at=EVALUATED_AT)

    assert decision["proposed_action"] == "run_small_test"
    assert decision["production_eligible"] is True
    assert decision["evidence_quality"]["criteria_met"] is False
    assert decision["evidence_quality"]["total_observations"] == 0
    assert decision["evidence_quality"]["causal_effect_established"] is False
    assert decision["authority_status"] == "not_granted_by_evaluation"


@pytest.mark.parametrize("phase", ["testing", "reviewing"])
def test_absent_results_do_not_establish_success_in_an_existing_campaign(phase: str) -> None:
    campaign = campaign_context()
    campaign["phase"] = phase

    decision = evaluate_campaign(campaign, evaluated_at=EVALUATED_AT)

    assert decision["proposed_action"] == "observe_more"
    assert decision["production_eligible"] is False
    assert decision["evidence_quality"]["criteria_met"] is False


def test_evaluation_and_validation_leave_the_callers_input_unchanged() -> None:
    campaign = repeated_evidence_campaign()
    before = deepcopy(campaign)

    normalized = validate_campaign(campaign)
    first = evaluate_campaign(campaign, evaluated_at=EVALUATED_AT)
    second = evaluate_campaign(campaign, evaluated_at=EVALUATED_AT)

    assert campaign == before
    assert first == second
    normalized["sources"][0]["text"] = "changed by caller after validation"
    first["evidence_quality"]["total_observations"] = -1
    assert campaign == before
    assert evaluate_campaign(campaign, evaluated_at=EVALUATED_AT) == second


def test_normalized_context_and_decision_satisfy_the_published_schemas() -> None:
    normalized = validate_campaign(campaign_context())
    decision = evaluate_campaign(normalized, evaluated_at=EVALUATED_AT)

    assert_schema(normalized, "campaign_context.v1")
    assert_schema(decision, decision["schema_version"])


def test_declared_predecessor_and_correction_lineage_passes_through_without_becoming_authority() -> None:
    campaign = campaign_context()
    assert validate_campaign(campaign)["lineage"] is None
    campaign["lineage"] = campaign_lineage()
    before = deepcopy(campaign)

    normalized = validate_campaign(campaign)
    decision = evaluate_campaign(campaign, evaluated_at=EVALUATED_AT)

    assert normalized["lineage"] == campaign["lineage"]
    assert decision["lineage"] == campaign["lineage"]
    assert decision["authority_status"] == "not_granted_by_evaluation"
    assert campaign == before
    assert_schema(normalized, normalized["schema_version"])
    assert_schema(decision, decision["schema_version"])


@pytest.mark.parametrize("missing", ["change_note", "parent_reference"])
def test_correction_lineage_requires_both_an_explanation_and_a_predecessor(missing: str) -> None:
    campaign = campaign_context()
    campaign["lineage"] = campaign_lineage()
    if missing == "change_note":
        campaign["lineage"]["change_note"] = ""
    else:
        campaign["lineage"]["parent_campaign_digest"] = None
        campaign["lineage"]["parent_decision_id"] = None
        campaign["lineage"]["parent_variant_ids"] = []

    with pytest.raises(CampaignValidationError):
        validate_campaign(campaign)


def test_changing_the_declared_parent_changes_campaign_and_decision_identity() -> None:
    campaign = campaign_context()
    campaign["lineage"] = campaign_lineage()
    original = evaluate_campaign(campaign, evaluated_at=EVALUATED_AT)
    campaign["lineage"]["parent_campaign_digest"] = "sha256:" + "c" * 64

    changed = evaluate_campaign(campaign, evaluated_at=EVALUATED_AT)

    assert changed["campaign_digest"] != original["campaign_digest"]
    assert changed["decision_id"] != original["decision_id"]
    assert changed["source_references"] == original["source_references"]


def test_lineage_cannot_include_an_unsupported_history_verification_claim() -> None:
    campaign = campaign_context()
    campaign["lineage"] = campaign_lineage()
    campaign["lineage"]["verified_against_history"] = True

    with pytest.raises(CampaignValidationError):
        validate_campaign(campaign)


def test_source_text_and_qualifications_are_not_normalized_away() -> None:
    normalized = validate_campaign(campaign_context())

    assert normalized["sources"][0]["text"] == SOURCE_TEXT
    assert normalized["claims"][0]["statement"] == QUALIFIED_CLAIM
    assert normalized["claims"][0]["status"] == "qualified"


def test_a_known_source_hash_mismatch_is_invalid() -> None:
    campaign = campaign_context()
    campaign["sources"][0]["content_hash"] = "sha256:" + "0" * 64

    with pytest.raises(CampaignValidationError):
        validate_campaign(campaign)
    with pytest.raises(CampaignValidationError):
        evaluate_campaign(campaign, evaluated_at=EVALUATED_AT)


@pytest.mark.parametrize("text", ["", " \n\t "])
def test_a_source_uri_or_hash_does_not_substitute_for_usable_source_text(text: str) -> None:
    campaign = campaign_context()
    campaign["sources"][0]["text"] = text
    campaign["sources"][0]["content_hash"] = (
        "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest() if text else ""
    )

    decision = evaluate_campaign(campaign, evaluated_at=EVALUATED_AT)

    assert decision["production_eligible"] is False
    assert decision["proposed_action"] == "observe_more"


@pytest.mark.parametrize(
    ("field", "value"),
    [("mission", "misaligned"), ("source_fidelity", "violated")],
)
def test_high_engagement_cannot_override_mission_or_source_violations(field: str, value: str) -> None:
    campaign = repeated_evidence_campaign()
    campaign["review"][field] = value
    for item in campaign["observations"]:
        item["exposures"] = 1_000_000
        item["metric"] = {"name": "views", "numerator": 1_000_000, "denominator": 1_000_000}

    decision = evaluate_campaign(campaign, evaluated_at=EVALUATED_AT)

    assert decision["proposed_action"] == "pause"
    assert decision["production_eligible"] is False
    assert decision["authority_status"] == "not_granted_by_evaluation"


@pytest.mark.parametrize("field", ["mission", "source_fidelity"])
def test_unknown_editorial_assessment_is_not_assumed_to_be_a_pass(field: str) -> None:
    campaign = campaign_context()
    campaign["review"][field] = "unknown"

    decision = evaluate_campaign(campaign, evaluated_at=EVALUATED_AT)

    assert decision["production_eligible"] is False


@pytest.mark.parametrize(("phase", "expected_action"), [("paused", "pause"), ("archived", "archive")])
def test_evidence_does_not_automatically_restart_a_paused_or_archived_campaign(
    phase: str, expected_action: str
) -> None:
    campaign = repeated_evidence_campaign()
    campaign["phase"] = phase

    decision = evaluate_campaign(campaign, evaluated_at=EVALUATED_AT)

    assert decision["proposed_action"] == expected_action
    assert decision["production_eligible"] is False


def test_irrelevant_creative_principles_do_not_block_a_valid_first_test() -> None:
    campaign = campaign_context()
    campaign["principle_ids"] = []

    decision = evaluate_campaign(campaign, evaluated_at=EVALUATED_AT)

    assert decision["proposed_action"] == "run_small_test"
    assert decision["production_eligible"] is True


def test_two_independent_comparable_observations_can_support_a_bounded_repeat() -> None:
    decision = evaluate_campaign(repeated_evidence_campaign(), evaluated_at=EVALUATED_AT)

    assert decision["proposed_action"] == "repeat_theme"
    assert decision["production_eligible"] is True
    assert decision["evidence_quality"]["criteria_met"] is True
    assert decision["evidence_quality"]["independent_variants"] == 2
    assert decision["evidence_quality"]["counted_exposures"] == 400
    assert decision["evidence_quality"]["causal_effect_established"] is False
    assert decision["authority_status"] == "not_granted_by_evaluation"


@pytest.mark.parametrize("problem", ["early", "small", "unverified", "platform", "format", "no_plan"])
def test_inadequate_or_incomparable_observations_cannot_establish_repeatable_success(problem: str) -> None:
    campaign = repeated_evidence_campaign()
    if problem == "early":
        campaign["evaluation_plan"]["window_end"] = "2026-11-11T00:00:00Z"
    elif problem == "small":
        campaign["evaluation_plan"]["minimum_exposures"] = 10_000
    elif problem == "unverified":
        campaign["observations"][1]["verification"] = "unverified"
        campaign["observations"][1]["verified_by"] = ""
    elif problem in {"platform", "format"}:
        campaign["observations"][1][problem] = "another-context"
    else:
        campaign["evaluation_plan"] = None

    decision = evaluate_campaign(campaign, evaluated_at=EVALUATED_AT)

    assert decision["proposed_action"] != "repeat_theme"
    assert decision["evidence_quality"]["criteria_met"] is False
    assert decision["evidence_quality"]["causal_effect_established"] is False


def test_a_repeated_measurement_is_not_a_third_independent_observation() -> None:
    campaign = repeated_evidence_campaign()
    campaign["evaluation_plan"]["minimum_observations"] = 3
    duplicate = deepcopy(campaign["observations"][0])
    duplicate["observation_id"] = "observation.test.same-measurement-again"
    campaign["observations"].append(duplicate)

    decision = evaluate_campaign(campaign, evaluated_at=EVALUATED_AT)

    assert decision["evidence_quality"]["criteria_met"] is False
    assert decision["evidence_quality"]["eligible_observations"] == 2
    assert decision["proposed_action"] != "repeat_theme"


def test_repeated_snapshots_of_one_variant_do_not_inflate_its_exposure_count() -> None:
    campaign = repeated_evidence_campaign()
    campaign["evaluation_plan"]["minimum_exposures"] = 1_000
    campaign["observations"][0]["exposures"] = 600
    campaign["observations"][1]["exposures"] = 100
    campaign["observations"][1]["metric"] = None
    campaign["observations"].append(observation(3, variant_id="variant.test.1", exposures=600))

    decision = evaluate_campaign(campaign, evaluated_at=EVALUATED_AT)

    assert decision["evidence_quality"]["counted_exposures"] == 700
    assert decision["evidence_quality"]["criteria_met"] is False
    assert decision["proposed_action"] != "repeat_theme"


def test_an_excluded_duplicate_cannot_supply_the_missing_exposure_evidence() -> None:
    campaign = repeated_evidence_campaign()
    campaign["evaluation_plan"]["minimum_exposures"] = 1_000
    duplicate = deepcopy(campaign["observations"][0])
    duplicate["observation_id"] = "observation.test.duplicate-with-inflated-count"
    duplicate["exposures"] = 1_000_000
    campaign["observations"].append(duplicate)

    decision = evaluate_campaign(campaign, evaluated_at=EVALUATED_AT)

    assert decision["evidence_quality"]["criteria_met"] is False
    assert decision["evidence_quality"]["counted_exposures"] == 400
    assert decision["proposed_action"] != "repeat_theme"


def test_one_variant_cannot_become_multiple_independent_variants() -> None:
    campaign = repeated_evidence_campaign()
    campaign["observations"][1]["variant_id"] = campaign["observations"][0]["variant_id"]

    decision = evaluate_campaign(campaign, evaluated_at=EVALUATED_AT)

    assert decision["evidence_quality"]["independent_variants"] == 1
    assert decision["evidence_quality"]["criteria_met"] is False
    assert decision["proposed_action"] != "repeat_theme"


def test_one_cited_measurement_cannot_be_aliased_into_two_independent_variants() -> None:
    campaign = repeated_evidence_campaign()
    campaign["observations"][1]["source_ref"] = campaign["observations"][0]["source_ref"]

    decision = evaluate_campaign(campaign, evaluated_at=EVALUATED_AT)

    assert decision["evidence_quality"]["eligible_observations"] == 1
    assert decision["evidence_quality"]["independent_variants"] == 1
    assert decision["evidence_quality"]["criteria_met"] is False
    assert decision["evidence_quality"]["repeat_supported"] is False
    assert decision["proposed_action"] != "repeat_theme"


def test_a_recorded_correction_invalidates_the_original_measurement_even_after_its_window() -> None:
    campaign = repeated_evidence_campaign()
    correction = observation(
        3,
        variant_id="variant.test.1",
        source_ref="evidence:audience-response.1",
        observed_at="2026-11-09T06:00:00Z",
        verification="contradicted",
        summary="The earlier response was misattributed and cannot support this campaign result.",
    )
    campaign["observations"].append(correction)

    decision = evaluate_campaign(campaign, evaluated_at=EVALUATED_AT)

    assert decision["evidence_quality"]["contradicted_reference_count"] == 1
    assert decision["evidence_quality"]["repeat_supported"] is False
    assert decision["evidence_quality"]["criteria_met"] is False
    assert decision["proposed_action"] != "repeat_theme"
    assert {ref["observation_id"] for ref in decision["evidence_references"]} == {
        row["observation_id"] for row in campaign["observations"]
    }


def test_a_future_dated_correction_does_not_rewrite_an_earlier_fixed_time_evaluation() -> None:
    campaign = repeated_evidence_campaign()
    campaign["observations"].append(observation(
        3,
        variant_id="variant.test.1",
        source_ref="evidence:audience-response.1",
        observed_at="2026-11-11T00:00:00Z",
        verification="contradicted",
        summary="A correction not yet observable at the fixed evaluation time.",
    ))

    decision = evaluate_campaign(campaign, evaluated_at=EVALUATED_AT)

    assert decision["evidence_quality"]["contradicted_reference_count"] == 0
    assert decision["proposed_action"] == "repeat_theme"


@pytest.mark.parametrize(("kind", "expected_action"), [
    ("misunderstanding", "clarify_message"),
    ("conflict", "observe_more"),
])
def test_positive_first_row_cannot_hide_a_duplicate_references_qualitative_problem(
    kind: str, expected_action: str,
) -> None:
    campaign = repeated_evidence_campaign()
    problem = observation(
        3,
        variant_id="variant.test.1",
        source_ref="evidence:audience-response.1",
        kind=kind,
        summary="The same cited discussion also contains this unresolved interpretation problem.",
    )
    campaign["observations"].append(problem)
    reversed_rows = deepcopy(campaign)
    reversed_rows["observations"].reverse()

    for context in (campaign, reversed_rows):
        decision = evaluate_campaign(context, evaluated_at=EVALUATED_AT)
        assert decision["proposed_action"] == expected_action
        assert decision["evidence_quality"]["repeat_supported"] is False
        assert len(decision["evidence_references"]) == 3


def test_a_meaning_based_lane_review_can_be_proposed_without_manufactured_audience_success() -> None:
    campaign = campaign_context()
    campaign["operator_request"] = {
        "action": "propose_lane_routing",
        "reason": "Review whether this purpose fits an existing durable lane.",
        "by": "human:campaign-owner",
        "evidence_refs": [],
    }

    decision = evaluate_campaign(campaign, evaluated_at=EVALUATED_AT)

    assert decision["proposed_action"] == "propose_lane_routing"
    assert decision["production_eligible"] is False
    assert decision["evidence_quality"]["criteria_met"] is False
    assert decision["authority_status"] == "not_granted_by_evaluation"


def test_repeated_evidence_does_not_automatically_authorize_a_broader_campaign() -> None:
    campaign = repeated_evidence_campaign()
    campaign["operator_request"] = {
        "action": "expand_campaign",
        "reason": "Consider a broader series using the observed responses.",
        "by": "human:campaign-owner",
        "evidence_refs": ["evidence:audience-response.1", "evidence:audience-response.2"],
    }

    decision = evaluate_campaign(campaign, evaluated_at=EVALUATED_AT)

    assert decision["proposed_action"] == "expand_campaign"
    assert decision["production_eligible"] is False
    assert decision["authority_status"] == "not_granted_by_evaluation"


def test_explicit_bounded_variation_can_be_proposed_while_a_campaign_has_no_results() -> None:
    campaign = campaign_context()
    campaign["phase"] = "testing"
    campaign["operator_request"] = {
        "action": "vary_format",
        "reason": "Prepare a clearly labeled exploratory variant.",
        "by": "human:campaign-owner",
        "evidence_refs": [],
    }

    decision = evaluate_campaign(campaign, evaluated_at=EVALUATED_AT)

    assert decision["proposed_action"] == "vary_format"
    assert decision["production_eligible"] is True
    assert decision["evidence_quality"]["criteria_met"] is False
    assert decision["authority_status"] == "not_granted_by_evaluation"


def test_raw_performance_counts_do_not_alone_establish_repeatable_usefulness() -> None:
    campaign = repeated_evidence_campaign()
    for row in campaign["observations"]:
        row["kind"] = "performance"
        row["exposures"] = 1_000_000

    decision = evaluate_campaign(campaign, evaluated_at=EVALUATED_AT)

    assert decision["evidence_quality"]["criteria_met"] is True
    assert decision["evidence_quality"]["repeat_supported"] is False
    assert decision["proposed_action"] == "observe_more"


@pytest.mark.parametrize("field", ["source_ref", "verified_by"])
def test_an_observation_cannot_self_label_verified_without_attribution(field: str) -> None:
    campaign = repeated_evidence_campaign()
    campaign["observations"][0][field] = ""

    with pytest.raises(CampaignValidationError):
        validate_campaign(campaign)


def test_duplicate_observation_ids_are_rejected_instead_of_hiding_an_overwrite() -> None:
    campaign = repeated_evidence_campaign()
    campaign["observations"][1]["observation_id"] = campaign["observations"][0]["observation_id"]

    with pytest.raises(CampaignValidationError):
        validate_campaign(campaign)


@pytest.mark.parametrize("bad_number", [True, float("nan"), float("inf"), -1])
def test_exposure_counts_must_be_actual_finite_nonnegative_numbers(bad_number: object) -> None:
    campaign = repeated_evidence_campaign()
    campaign["observations"][0]["exposures"] = bad_number

    with pytest.raises(CampaignValidationError):
        validate_campaign(campaign)


@pytest.mark.parametrize("metric", [
    {"name": "shares", "numerator": 1, "denominator": 0},
    {"name": "shares", "numerator": 2, "denominator": 1},
    {"name": "shares", "numerator": True, "denominator": 10},
])
def test_metric_counts_cannot_claim_a_rate_without_a_valid_denominator(metric: dict) -> None:
    campaign = repeated_evidence_campaign()
    campaign["observations"][0]["metric"] = metric

    with pytest.raises(CampaignValidationError):
        validate_campaign(campaign)


@pytest.mark.parametrize("injected_key", ["publication_authorized", "production_eligible", "review_decision"])
def test_input_cannot_inject_a_downstream_authorization_or_completion_flag(injected_key: str) -> None:
    campaign = campaign_context()
    campaign[injected_key] = True

    with pytest.raises(CampaignValidationError):
        evaluate_campaign(campaign, evaluated_at=EVALUATED_AT)


def test_catalog_is_isolated_from_mutation_by_a_previous_caller() -> None:
    original = load_principles()
    changed = load_principles()
    changed.clear()

    assert load_principles() == original
    assert original
