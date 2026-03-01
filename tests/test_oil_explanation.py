"""Tests: oil/explanation/generator.py + reporter.py"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from oil.correlation.ranker import rank_hypotheses
from oil.explanation.generator import format_human_block, generate_explanation
from oil.explanation.reporter import write_artifact
from oil.graph.loader import load_graph
from oil.impact.mapper import load_impact_map
from oil.intake.normalizer import normalize_event

_SAMPLE_GRAPH = Path(__file__).resolve().parents[1] / "oil" / "graph" / "sample_graph.json"
_REF_TS = datetime(2026, 2, 27, 17, 0, 0, tzinfo=timezone.utc)
_REF_SERVICE = "checkout"

_REQUIRED_REPORT_KEYS = {
    "incident_summary",
    "primary_technical_impact",
    "business_effect_estimate",
    "top_ranked_cause",
    "confidence_score",
    "recommended_human_action",
}


def _make_events():
    def _ev(service, delta, dt_min):
        ts = _REF_TS - timedelta(minutes=dt_min)
        return normalize_event({
            "event_id": f"evt-{service}",
            "timestamp": ts.isoformat(),
            "service": service,
            "delta": delta,
            "event_type": "metric",
        })
    return [
        _ev("checkout", -420.0, 0),
        _ev("payment", 310.0, 3),
        _ev("auth", 0.09, 2),
    ]


class TestGenerateExplanation:
    def test_report_has_all_required_keys(self):
        graph = load_graph(_SAMPLE_GRAPH)
        events = _make_events()
        hypotheses = rank_hypotheses(events, graph, _REF_TS, _REF_SERVICE)
        impact_map = load_impact_map()
        report = generate_explanation(hypotheses, events, impact_map, _REF_SERVICE)
        assert _REQUIRED_REPORT_KEYS.issubset(report.keys())

    def test_confidence_score_is_float(self):
        graph = load_graph(_SAMPLE_GRAPH)
        events = _make_events()
        hypotheses = rank_hypotheses(events, graph, _REF_TS, _REF_SERVICE)
        impact_map = load_impact_map()
        report = generate_explanation(hypotheses, events, impact_map, _REF_SERVICE)
        assert isinstance(report["confidence_score"], float)
        assert 0.0 <= report["confidence_score"] <= 1.0

    def test_evidence_list_present(self):
        graph = load_graph(_SAMPLE_GRAPH)
        events = _make_events()
        hypotheses = rank_hypotheses(events, graph, _REF_TS, _REF_SERVICE)
        impact_map = load_impact_map()
        report = generate_explanation(hypotheses, events, impact_map, _REF_SERVICE)
        assert "evidence" in report
        assert isinstance(report["evidence"], list)
        assert len(report["evidence"]) <= 3

    def test_empty_hypotheses_does_not_crash(self):
        events = _make_events()
        impact_map = load_impact_map()
        report = generate_explanation([], events, impact_map, _REF_SERVICE)
        assert _REQUIRED_REPORT_KEYS.issubset(report.keys())
        assert report["confidence_score"] == 0.0

    def test_primary_impact_prefers_reference_service(self):
        """checkout event should appear in primary_technical_impact when it has qualifying type."""
        graph = load_graph(_SAMPLE_GRAPH)
        events = _make_events()
        hypotheses = rank_hypotheses(events, graph, _REF_TS, _REF_SERVICE)
        impact_map = load_impact_map()
        report = generate_explanation(hypotheses, events, impact_map, _REF_SERVICE)
        # checkout is the reference_service and has the highest abs(delta)=420
        assert "checkout" in report["primary_technical_impact"]

    def test_format_human_block_returns_string(self):
        graph = load_graph(_SAMPLE_GRAPH)
        events = _make_events()
        hypotheses = rank_hypotheses(events, graph, _REF_TS, _REF_SERVICE)
        impact_map = load_impact_map()
        report = generate_explanation(hypotheses, events, impact_map, _REF_SERVICE)
        block = format_human_block(report)
        assert isinstance(block, str)
        assert "OIL" in block
        assert "CONFIDENCE" in block


class TestWriteArtifact:
    def test_artifact_written_to_disk(self, tmp_path):
        report = {k: "test" for k in _REQUIRED_REPORT_KEYS}
        report["confidence_score"] = 0.75
        artifact_path, _ = write_artifact(report, tmp_path)
        assert artifact_path.exists()

    def test_artifact_is_valid_json(self, tmp_path):
        report = {k: "test" for k in _REQUIRED_REPORT_KEYS}
        report["confidence_score"] = 0.75
        artifact_path, _ = write_artifact(report, tmp_path)
        data = json.loads(artifact_path.read_text(encoding="utf-8"))
        # v0.2: report is nested under 'report' key in envelope
        assert "incident_summary" in data["report"]

    def test_artifact_filename_matches_pattern(self, tmp_path):
        report = {"confidence_score": 0.5}
        artifact_path, _ = write_artifact(report, tmp_path)
        # v0.4.1: filename includes run_id suffix: incident_<ts>_<run_id>.json
        assert re.match(r"incident_\d{8}T\d{6}Z_[0-9a-f]{16}\.json", artifact_path.name)

    def test_artifact_creates_dir_if_missing(self, tmp_path):
        nested = tmp_path / "deep" / "nested" / "artifacts"
        report = {"confidence_score": 0.5}
        artifact_path, _ = write_artifact(report, nested)
        assert artifact_path.exists()


class TestV01DomainClarity:
    """v0.1 business_effect_estimate separates impact_domain from origin_domain."""

    def _make_report(self):
        graph = load_graph(_SAMPLE_GRAPH)
        events = _make_events()
        hypotheses = rank_hypotheses(events, graph, _REF_TS, _REF_SERVICE)
        impact_map = load_impact_map()
        return generate_explanation(hypotheses, events, impact_map, _REF_SERVICE)

    def test_business_effect_contains_impact_domain_label(self):
        report = self._make_report()
        assert "Impact domain" in report["business_effect_estimate"]

    def test_business_effect_contains_origin_domain_label(self):
        report = self._make_report()
        assert "Suspected origin domain" in report["business_effect_estimate"]

    def test_business_effect_contains_correct_impact_domain(self):
        """checkout → revenue (impact domain)."""
        report = self._make_report()
        assert "revenue" in report["business_effect_estimate"]

    def test_business_effect_contains_correct_origin_domain(self):
        """Suspected origin domain should match the top hypothesis's service domain.

        v0.2: checkout (0-hop, confidence=1.0) is top hypothesis with these test events.
        We verify the label structure rather than hardcoding a specific domain string.
        """
        report = self._make_report()
        text = report["business_effect_estimate"]
        # Extract what the top hypothesis actually is
        graph = load_graph(_SAMPLE_GRAPH)
        events = _make_events()
        hyps = rank_hypotheses(events, graph, _REF_TS, _REF_SERVICE)
        from oil.impact.mapper import map_impact
        expected_origin_domain = map_impact(hyps[0].suspected_origin, load_impact_map())
        assert expected_origin_domain in text

    def test_domains_are_labelled_differently(self):
        """The two domains must appear in separately labelled phrases, not merged."""
        report = self._make_report()
        text = report["business_effect_estimate"]
        assert "Impact domain" in text and "Suspected origin domain" in text


class TestV02ArtifactEnvelope:
    """v0.2 artifact versioning: all incidents wrapped in envelope."""

    def test_artifact_has_envelope_keys(self, tmp_path):
        from oil.explanation.reporter import write_artifact, ARTIFACT_VERSION, OIL_VERSION
        report = {"incident_summary": "test", "confidence_score": 0.9}
        path, run_id = write_artifact(report, tmp_path, inputs_digest="sha256:abc123")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["artifact_version"] == ARTIFACT_VERSION
        assert data["oil_version"] == OIL_VERSION
        assert "created_utc" in data
        assert data["inputs_digest"] == "sha256:abc123"
        assert "run_id" in data              # v0.4.1
        assert len(data["run_id"]) == 16     # 16-char hex
        assert "report" in data

    def test_artifact_report_nested_under_report_key(self, tmp_path):
        from oil.explanation.reporter import write_artifact
        report = {"incident_summary": "nested test", "confidence_score": 0.5}
        path, _ = write_artifact(report, tmp_path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["report"]["incident_summary"] == "nested test"

    def test_inputs_digest_is_stable(self):
        """Same events/graph/impact_map → same digest across calls."""
        from oil.explanation.reporter import compute_inputs_digest
        events = [{"event_id": "e1", "service": "checkout"}]
        graph = {"checkout": {"upstream": [], "downstream": []}}
        impact_map = {"checkout": "revenue"}
        d1 = compute_inputs_digest(events, graph, impact_map)
        d2 = compute_inputs_digest(events, graph, impact_map)
        assert d1 == d2

    def test_inputs_digest_starts_with_sha256(self):
        from oil.explanation.reporter import compute_inputs_digest
        events = [{"event_id": "e1", "service": "checkout"}]
        d = compute_inputs_digest(events, {}, {})
        assert d.startswith("sha256:")

    def test_inputs_digest_changes_with_different_events(self):
        from oil.explanation.reporter import compute_inputs_digest
        events_a = [{"event_id": "e1", "service": "checkout"}]
        events_b = [{"event_id": "e2", "service": "payment"}]
        d1 = compute_inputs_digest(events_a, {}, {})
        d2 = compute_inputs_digest(events_b, {}, {})
        assert d1 != d2


class TestV03ChangeOriginRendering:
    """v0.3: explanation renders change-origin as 'service change_kind change_id'."""

    def _make_payment_change_events(self):
        """Return [payment metric event, payment deploy change event]."""
        def _ev(service, delta, dt_min, event_type="metric", change_kind="", change_id=""):
            ts = _REF_TS - timedelta(minutes=dt_min)
            return normalize_event({
                "event_id": f"ev-{service}-{dt_min}",
                "timestamp": ts.isoformat(),
                "service": service,
                "delta": delta,
                "event_type": event_type,
                "change_kind": change_kind,
                "change_id": change_id,
            })
        return [
            _ev("payment", delta=310.0, dt_min=3),
            _ev("payment", delta=0.0, dt_min=5, event_type="change",
                change_kind="deploy", change_id="sha-payment-v3.1"),
        ]

    def test_change_origin_appears_in_top_ranked_cause(self):
        """top_ranked_cause should include 'deploy' and the change_id."""
        graph = load_graph(_SAMPLE_GRAPH)
        events = self._make_payment_change_events()
        hyps = rank_hypotheses(events, graph, _REF_TS, _REF_SERVICE)
        impact_map = load_impact_map()
        report = generate_explanation(hyps, events, impact_map, _REF_SERVICE)
        cause_text = report["top_ranked_cause"]
        # v0.3: rendered as "payment deploy sha-payment-v3.1"
        assert "payment" in cause_text
        assert "deploy" in cause_text
        assert "sha-payment-v3.1" in cause_text

    def test_plain_service_origin_not_change_formatted(self):
        """Without a change event, top_ranked_cause shows plain service name."""
        def _plain_ev(service, delta, dt_min):
            ts = _REF_TS - timedelta(minutes=dt_min)
            return normalize_event({
                "event_id": f"ev-{service}",
                "timestamp": ts.isoformat(),
                "service": service,
                "delta": delta,
                "event_type": "latency",
            })
        graph = load_graph(_SAMPLE_GRAPH)
        events = [_plain_ev("payment", delta=310.0, dt_min=3)]
        hyps = rank_hypotheses(events, graph, _REF_TS, _REF_SERVICE)
        report = generate_explanation(hyps, events, load_impact_map(), _REF_SERVICE)
        cause_text = report["top_ranked_cause"]
        assert "payment" in cause_text
        assert "deploy" not in cause_text

    def test_business_effect_uses_origin_service_for_domain(self):
        """origin_service drives domain lookup, not compound suspected_origin."""
        graph = load_graph(_SAMPLE_GRAPH)
        events = self._make_payment_change_events()
        hyps = rank_hypotheses(events, graph, _REF_TS, _REF_SERVICE)
        report = generate_explanation(hyps, events, load_impact_map(), _REF_SERVICE)
        # payment maps to "transactions" in the standard impact_map
        assert "transactions" in report["business_effect_estimate"]



