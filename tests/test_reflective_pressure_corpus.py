from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.reflective_pressure import cli
from app.reflective_pressure.classify import classify_input
from app.reflective_pressure.export import export_prompt_pack
from app.reflective_pressure.generate import generate_draft
from app.reflective_pressure.importer import import_inputs_from_jsonl
from app.reflective_pressure.models import (
    build_correction_record,
    build_golden_example_record,
    build_input_record,
)
from app.reflective_pressure.reconcile import reconcile_reflective_pressure_state
from app.reflective_pressure.review import build_review_packet
from app.reflective_pressure.store import (
    CORRECTIONS_FILE,
    GOLDEN_EXAMPLES_FILE,
    append_classification,
    append_correction,
    append_draft,
    append_golden_example,
    append_input,
    list_corrections,
    list_golden_examples,
)
from app.reflective_pressure.summary import (
    summarize_classification_vs_correction_drift,
    summarize_ready_for_prompt_export,
)
from app.retention.jsonl_store import append_record


def _read_stdout_json(capsys: pytest.CaptureFixture[str]) -> dict:
    return json.loads(capsys.readouterr().out)


def _write_jsonl(path: Path, rows: list[object]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


@pytest.fixture
def rp_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    monkeypatch.setenv("SIGNAL_AGENT_ROOT", str(root))
    return root


def test_correction_model_validation_and_unsafe_flags(rp_root: Path) -> None:
    input_record, classification, _draft = _seed_flow()
    correction = build_correction_record(
        target_record_type="classification",
        target_record_id=classification["classification_id"],
        input_id=input_record["input_id"],
        corrected_pressure_type="peace_vs_escalation",
        corrected_surface_claim="The thread is reacting to accusation.",
        corrected_hidden_pressure="The deeper pressure is whether conflict becomes recognition or escalation.",
        corrected_moral_temperature=3,
        corrected_ambiguity_level=4,
        corrected_audience_self_insertion_potential=4,
        corrected_risk_of_tribal_escalation=3,
        corrected_recognition_potential=4,
        corrected_recommended_output_type="reply",
        correction_reason="Human read sees accusation pressure more clearly.",
        created_at="2026-05-14T14:00:00Z",
    )

    assert correction["correction_id"].startswith("rpx_")
    assert correction["corrected_by"] == "human_operator"
    assert correction["external_action_allowed"] is False

    with pytest.raises(ValueError, match="external_action_allowed_not_allowed"):
        build_correction_record(
            target_record_type="classification",
            target_record_id=classification["classification_id"],
            input_id=input_record["input_id"],
            corrected_pressure_type="peace_vs_escalation",
            corrected_surface_claim="surface",
            corrected_hidden_pressure="hidden",
            corrected_moral_temperature=3,
            corrected_ambiguity_level=4,
            corrected_audience_self_insertion_potential=4,
            corrected_risk_of_tribal_escalation=3,
            corrected_recognition_potential=4,
            corrected_recommended_output_type="reply",
            correction_reason="unsafe flag test",
            external_action_allowed=True,
        )


def test_golden_example_model_validation_and_unsafe_flags(rp_root: Path) -> None:
    input_record, classification, draft = _seed_flow()
    correction = append_correction(_build_correction(input_record, classification))
    golden = build_golden_example_record(
        input_id=input_record["input_id"],
        classification_id=classification["classification_id"],
        correction_id=correction["correction_id"],
        draft_id=draft["draft_id"],
        pressure_type="peace_vs_escalation",
        title="Accusation pressure without escalation",
        why_it_matters="It preserves tension without rewarding conflict.",
        reusable_pattern="Name the pressure, then refuse the slogan.",
        approved_for_prompt_export=True,
        created_at="2026-05-14T14:05:00Z",
    )

    assert golden["golden_id"].startswith("rpg_")
    assert golden["approved_for_prompt_export"] is True
    assert golden["external_action_allowed"] is False

    with pytest.raises(ValueError, match="irreversible_action_allowed_not_allowed"):
        build_golden_example_record(
            input_id=input_record["input_id"],
            classification_id=classification["classification_id"],
            pressure_type="peace_vs_escalation",
            title="Unsafe",
            why_it_matters="Unsafe flag test",
            reusable_pattern="Do not allow unsafe flags.",
            irreversible_action_allowed=True,
        )


def test_append_and_list_corrections_and_golden_examples(rp_root: Path) -> None:
    input_record, classification, draft = _seed_flow()
    correction = append_correction(_build_correction(input_record, classification))
    golden = append_golden_example(
        _build_golden(input_record, classification, correction_id=correction["correction_id"], draft_id=draft["draft_id"])
    )

    assert list_corrections(input_id=input_record["input_id"]) == [correction]
    assert list_corrections(target_record_id=classification["classification_id"]) == [correction]
    assert list_golden_examples(pressure_type="peace_vs_escalation") == [golden]
    assert list_golden_examples(approved_only=True) == [golden]


def test_import_valid_and_mixed_jsonl(rp_root: Path, tmp_path: Path) -> None:
    valid_path = tmp_path / "valid.jsonl"
    _write_jsonl(
        valid_path,
        [
            {
                "source_platform": "facebook_group",
                "source_type": "comment",
                "raw_text": "Nobody understands the pressure of being unseen.",
                "tags": ["recognition"],
            },
            {
                "source_platform": "personal_note",
                "source_type": "personal_reflection",
                "raw_text": "This system conversation keeps circling authority and power.",
            },
        ],
    )
    report = import_inputs_from_jsonl(valid_path)
    assert report["imported_count"] == 2
    assert report["failed_count"] == 0
    assert len(report["created_input_ids"]) == 2

    mixed_path = tmp_path / "mixed.jsonl"
    _write_jsonl(
        mixed_path,
        [
            {"source_platform": "facebook_group", "source_type": "comment", "raw_text": "lol this meme hides pain"},
            {"source_platform": "bad_platform", "source_type": "comment", "raw_text": "bad"},
            {"source_platform": "facebook_group", "source_type": "comment", "raw_text": "bad tags", "tags": "not-list"},
        ],
    )
    mixed = import_inputs_from_jsonl(mixed_path)
    assert mixed["imported_count"] == 1
    assert mixed["failed_count"] == 2
    assert [failure["line_number"] for failure in mixed["failures"]] == [2, 3]


def test_import_with_classify_and_draft_generation(rp_root: Path, tmp_path: Path) -> None:
    path = tmp_path / "seed.jsonl"
    _write_jsonl(
        path,
        [
            {
                "source_platform": "facebook_group",
                "source_type": "comment",
                "raw_text": "People keep using slogans instead of naming pressure.",
            }
        ],
    )

    report = import_inputs_from_jsonl(path, classify=True, generate_draft=True, output_type="reply")

    assert report["imported_count"] == 1
    assert len(report["created_classification_ids"]) == 1
    assert len(report["created_draft_ids"]) == 1


def test_review_packet_suggests_next_actions(rp_root: Path) -> None:
    input_record = append_input(
        build_input_record(
            source_platform="facebook_group",
            source_type="comment",
            raw_text="This accusation is missing my intent.",
            created_at="2026-05-14T12:00:00Z",
        )
    )
    assert build_review_packet(input_record["input_id"])["suggested_next_action"] == "classify"
    classification = append_classification(classify_input(input_record, created_at="2026-05-14T12:01:00Z"))
    assert build_review_packet(input_record["input_id"])["suggested_next_action"] == "generate_draft"
    append_draft(
        generate_draft(
            input_record,
            classification,
            output_type="reply",
            target_platform="facebook_group",
            created_at="2026-05-14T12:02:00Z",
        )
    )
    assert build_review_packet(input_record["input_id"])["suggested_next_action"] == "record_observation_after_manual_posting"


def test_correction_and_golden_cli(rp_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    input_record, classification, draft = _seed_flow()
    result = cli.main(
        [
            "rp-correct-classification",
            "--classification-id",
            classification["classification_id"],
            "--input-id",
            input_record["input_id"],
            "--pressure-type",
            "peace_vs_escalation",
            "--hidden-pressure",
            "The real pressure is whether this becomes recognition or escalation.",
            "--correction-reason",
            "Human correction.",
        ]
    )
    assert result == 0
    correction = _read_stdout_json(capsys)
    assert correction["target_record_id"] == classification["classification_id"]
    assert correction["corrected_pressure_type"] == "peace_vs_escalation"

    result = cli.main(
        [
            "rp-mark-golden",
            "--input-id",
            input_record["input_id"],
            "--classification-id",
            classification["classification_id"],
            "--correction-id",
            correction["correction_id"],
            "--draft-id",
            draft["draft_id"],
            "--pressure-type",
            "peace_vs_escalation",
            "--title",
            "Golden correction",
            "--why-it-matters",
            "It teaches de-escalating pressure recognition.",
            "--reusable-pattern",
            "Name the pressure without collapsing into blame.",
            "--approved-for-prompt-export",
            "true",
        ]
    )
    assert result == 0
    golden = _read_stdout_json(capsys)
    assert golden["approved_for_prompt_export"] is True


def test_prompt_pack_export_and_ready_summary(rp_root: Path) -> None:
    input_record, classification, draft = _seed_flow()
    correction = append_correction(_build_correction(input_record, classification))
    golden = append_golden_example(
        _build_golden(input_record, classification, correction_id=correction["correction_id"], draft_id=draft["draft_id"])
    )

    out_path = rp_root / "data" / "outputs" / "reflective_pressure" / "prompt_pack.md"
    report = export_prompt_pack(out_path)
    text = out_path.read_text(encoding="utf-8")
    ready = summarize_ready_for_prompt_export()

    assert report["example_count"] == 1
    assert "Reflective Pressure Prompt Pack" in text
    assert golden["golden_id"] in text
    assert ready["ready_count"] == 1
    assert ready["golden_ids"] == [golden["golden_id"]]

    with pytest.raises(ValueError, match="prompt_pack_path_outside_allowed_root"):
        export_prompt_pack(rp_root / "data" / "outputs" / "bad.md")


def test_summary_drift_and_reconciliation_with_corpus_records(rp_root: Path) -> None:
    input_record, classification, draft = _seed_flow()
    correction = append_correction(_build_correction(input_record, classification))
    append_golden_example(
        _build_golden(input_record, classification, correction_id=correction["correction_id"], draft_id=draft["draft_id"])
    )

    drift = summarize_classification_vs_correction_drift()
    report = reconcile_reflective_pressure_state()

    assert drift["pairs"] == {"shallow_certainty->peace_vs_escalation": 1}
    assert drift["drifted_pressure_type_count"] == 1
    assert report["clean"] is True
    assert report["summary"]["correction_count"] == 1
    assert report["summary"]["golden_example_count"] == 1


def test_reconciliation_failure_on_broken_correction_reference(rp_root: Path) -> None:
    correction = build_correction_record(
        target_record_type="classification",
        target_record_id="rpc_missing",
        input_id="rpi_missing",
        corrected_pressure_type="peace_vs_escalation",
        corrected_surface_claim="surface",
        corrected_hidden_pressure="hidden",
        corrected_moral_temperature=3,
        corrected_ambiguity_level=4,
        corrected_audience_self_insertion_potential=4,
        corrected_risk_of_tribal_escalation=3,
        corrected_recognition_potential=4,
        corrected_recommended_output_type="reply",
        correction_reason="broken reference fixture",
        created_at="2026-05-14T14:00:00Z",
    )
    append_record(CORRECTIONS_FILE, correction)

    report = reconcile_reflective_pressure_state()

    assert report["clean"] is False
    assert any(issue["issue_type"] == "correction_unknown_input" for issue in report["failures"])


def test_reconciliation_failure_on_broken_golden_reference(rp_root: Path) -> None:
    golden = build_golden_example_record(
        input_id="rpi_missing",
        classification_id="rpc_missing",
        pressure_type="peace_vs_escalation",
        title="Broken golden",
        why_it_matters="Fixture",
        reusable_pattern="Fixture",
        approved_for_prompt_export=True,
        created_at="2026-05-14T14:00:00Z",
    )
    append_record(GOLDEN_EXAMPLES_FILE, golden)

    report = reconcile_reflective_pressure_state()

    assert report["clean"] is False
    assert any(issue["issue_type"] == "golden_unknown_input" for issue in report["failures"])
    assert any(issue["issue_type"] == "golden_unknown_classification" for issue in report["failures"])


def _seed_flow() -> tuple[dict, dict, dict]:
    input_record = append_input(
        build_input_record(
            source_platform="facebook_group",
            source_type="comment",
            raw_text="People keep turning every deeper discussion back into slogans instead of dealing with pressure.",
            intended_spine="reflective",
            created_at="2026-05-14T12:00:00Z",
        )
    )
    classification = append_classification(classify_input(input_record, created_at="2026-05-14T12:01:00Z"))
    draft = append_draft(
        generate_draft(
            input_record,
            classification,
            output_type="reply",
            target_platform="facebook_group",
            created_at="2026-05-14T12:02:00Z",
        )
    )
    return input_record, classification, draft


def _build_correction(input_record: dict, classification: dict) -> dict:
    return build_correction_record(
        target_record_type="classification",
        target_record_id=classification["classification_id"],
        input_id=input_record["input_id"],
        corrected_pressure_type="peace_vs_escalation",
        corrected_surface_claim="The thread is reacting to accusation pressure.",
        corrected_hidden_pressure="The deeper pressure is whether this becomes recognition or escalation.",
        corrected_moral_temperature=3,
        corrected_ambiguity_level=4,
        corrected_audience_self_insertion_potential=4,
        corrected_risk_of_tribal_escalation=3,
        corrected_recognition_potential=4,
        corrected_recommended_output_type="reply",
        correction_reason="Human correction fixture.",
        created_at="2026-05-14T14:00:00Z",
    )


def _build_golden(
    input_record: dict,
    classification: dict,
    *,
    correction_id: str,
    draft_id: str,
) -> dict:
    return build_golden_example_record(
        input_id=input_record["input_id"],
        classification_id=classification["classification_id"],
        correction_id=correction_id,
        draft_id=draft_id,
        pressure_type="peace_vs_escalation",
        title="Accusation pressure without escalation",
        why_it_matters="It is reusable because it preserves conflict pressure without amplifying it.",
        reusable_pattern="Name the pressure, name the surface, leave room for recognition.",
        voice_notes="Measured and plainspoken.",
        risk_notes="Avoid blame language.",
        approved_for_prompt_export=True,
        created_at="2026-05-14T14:05:00Z",
    )
