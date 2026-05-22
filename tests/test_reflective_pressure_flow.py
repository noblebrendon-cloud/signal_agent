from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.reflective_pressure.classify import classify_input
from app.reflective_pressure.generate import generate_draft
from app.reflective_pressure.models import build_classification_record, build_input_record
from app.reflective_pressure.observe import record_observation
from app.reflective_pressure.reconcile import reconcile_reflective_pressure_state
from app.reflective_pressure.store import CLASSIFICATIONS_FILE, append_classification, append_draft, append_input
from app.reflective_pressure.summary import summarize_by_pressure_type, summarize_by_spine
from app.retention.jsonl_store import append_record


@pytest.fixture
def rp_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    monkeypatch.setenv("SIGNAL_AGENT_ROOT", str(root))
    return root


def test_full_local_flow_and_summaries(rp_root: Path) -> None:
    input_record = append_input(
        build_input_record(
            source_platform="facebook_group",
            source_type="comment",
            raw_text="People keep turning every deeper discussion back into slogans instead of dealing with the pressure.",
            intended_spine="reflective",
            created_at="2026-05-14T12:00:00Z",
        )
    )
    classification = append_classification(
        classify_input(input_record, created_at="2026-05-14T12:01:00Z")
    )
    draft = append_draft(
        generate_draft(
            input_record,
            classification,
            output_type="reply",
            target_platform="facebook_group",
            created_at="2026-05-14T12:02:00Z",
        )
    )
    observation = record_observation(
        input_id=input_record["input_id"],
        draft_id=draft["draft_id"],
        views=1000,
        reactions=25,
        comments=18,
        shares=4,
        saves=0,
        profile_clicks=3,
        recognition_events=6,
        constructive_reply_ratio=0.7,
        self_insertion_density=0.5,
        delayed_recirculation=0,
        contradiction_heat=3,
        created_at="2026-05-14T13:00:00Z",
    )

    assert classification["pressure_type"] == "shallow_certainty"
    assert draft["preserves_tension"] is True
    assert observation["external_action_allowed"] is False

    pressure_summary = summarize_by_pressure_type()
    spine_summary = summarize_by_spine()
    assert pressure_summary["counts"] == {"shallow_certainty": 1}
    assert pressure_summary["recognition_events"] == {"shallow_certainty": 6}
    assert spine_summary["input_counts"] == {"reflective": 1}
    assert spine_summary["draft_counts"] == {"reflective": 1}

    report = reconcile_reflective_pressure_state()
    assert report["clean"] is True
    assert report["summary"]["input_count"] == 1
    assert report["summary"]["classification_count"] == 1
    assert report["summary"]["draft_count"] == 1
    assert report["summary"]["observation_count"] == 1


def test_reconciliation_fails_on_broken_reference(rp_root: Path) -> None:
    bad_classification = build_classification_record(
        input_id="rpi_missing",
        surface_claim="broken ref",
        hidden_pressure="missing input reference",
        pressure_type="unknown",
        moral_temperature=1,
        ambiguity_level=5,
        audience_self_insertion_potential=1,
        risk_of_tribal_escalation=1,
        recognition_potential=1,
        recommended_output_type="pressure_log_entry",
        rationale="test fixture",
        confidence=0.2,
        created_at="2026-05-14T12:01:00Z",
    )
    append_record(CLASSIFICATIONS_FILE, bad_classification)

    report = reconcile_reflective_pressure_state()

    assert report["clean"] is False
    assert any(issue["issue_type"] == "classification_unknown_input" for issue in report["failures"])


def test_reconciliation_fails_on_malformed_ledger(rp_root: Path) -> None:
    state_root = rp_root / "data" / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    (state_root / CLASSIFICATIONS_FILE).write_text('{"broken":\n', encoding="utf-8")

    report = reconcile_reflective_pressure_state()

    assert report["clean"] is False
    assert report["failures"][0]["issue_type"] == "invalid_jsonl_record"


def test_no_network_or_posting_behavior_exists() -> None:
    module_root = Path(__file__).resolve().parents[1] / "app" / "reflective_pressure"
    source = "\n".join(path.read_text(encoding="utf-8") for path in sorted(module_root.glob("*.py")))

    forbidden_tokens = (
        "requests",
        "urllib",
        "http.client",
        "socket",
        "send_message",
        "scrape",
    )
    for token in forbidden_tokens:
        assert token not in source
