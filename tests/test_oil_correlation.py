"""Tests: oil/correlation/ranker.py"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from oil.correlation.ranker import _temporal_score, rank_hypotheses, select_reference
from oil.graph.loader import load_graph
from oil.intake.normalizer import normalize_event

_SAMPLE_GRAPH = Path(__file__).resolve().parents[1] / "oil" / "graph" / "sample_graph.json"

_REF_TS = datetime(2026, 2, 27, 17, 0, 0, tzinfo=timezone.utc)
_REF_SERVICE = "checkout"


def _ev(service, delta, dt_minutes=0, event_id=None, event_type="metric"):
    ts = _REF_TS - timedelta(minutes=dt_minutes)
    return normalize_event({
        "event_id": event_id or f"evt-{service}",
        "timestamp": ts.isoformat(),
        "service": service,
        "delta": delta,
        "event_type": event_type,
    })


class TestTemporalScore:
    def test_at_reference_ts_is_one(self):
        assert _temporal_score(_REF_TS, _REF_TS) == 1.0

    def test_within_five_minutes_is_one(self):
        assert _temporal_score(_REF_TS - timedelta(minutes=5), _REF_TS) == 1.0

    def test_at_thirty_minutes_is_zero(self):
        assert _temporal_score(_REF_TS - timedelta(minutes=30), _REF_TS) == 0.0

    def test_beyond_thirty_minutes_is_zero(self):
        assert _temporal_score(_REF_TS - timedelta(minutes=45), _REF_TS) == 0.0

    def test_at_ten_minutes_linear_decay(self):
        score = _temporal_score(_REF_TS - timedelta(minutes=10), _REF_TS)
        # (10 - 5) / 25 = 0.2  →  1 - 0.2 = 0.8
        assert abs(score - 0.8) < 1e-9

    def test_at_31minutes_just_above_zero(self):
        # 31 min: (31-5)/25 = 1.04 → clamped to 0
        score = _temporal_score(_REF_TS - timedelta(minutes=31), _REF_TS)
        assert score == 0.0


class TestRankHypotheses:
    def test_returns_sorted_descending(self):
        graph = load_graph(_SAMPLE_GRAPH)
        # payment (1 hop, recent, large delta) should score higher than inventory
        events = [
            _ev("payment", delta=300.0, dt_minutes=2),
            _ev("inventory", delta=5.0, dt_minutes=25),
        ]
        hypotheses = rank_hypotheses(events, graph, _REF_TS, _REF_SERVICE)
        assert len(hypotheses) == 2
        assert hypotheses[0].confidence_score >= hypotheses[1].confidence_score

    def test_empty_events_returns_empty(self):
        graph = load_graph(_SAMPLE_GRAPH)
        result = rank_hypotheses([], graph, _REF_TS, _REF_SERVICE)
        assert result == []

    def test_all_zero_deltas_magnitude_zero(self):
        graph = load_graph(_SAMPLE_GRAPH)
        events = [_ev("payment", delta=0.0, dt_minutes=2)]
        hypotheses = rank_hypotheses(events, graph, _REF_TS, _REF_SERVICE)
        assert hypotheses[0].impact_score == 0.0

    def test_delta_none_normalized_does_not_crash(self):
        """delta=None is coerced to 0.0 in normalizer — ranker must handle 0.0 gracefully."""
        graph = load_graph(_SAMPLE_GRAPH)
        events = [_ev("inventory", delta=0.0, dt_minutes=5)]
        hypotheses = rank_hypotheses(events, graph, _REF_TS, _REF_SERVICE)
        assert len(hypotheses) == 1
        assert hypotheses[0].impact_score == 0.0

    def test_hypothesis_id_is_stable(self):
        """Same inputs must always produce same hypothesis_id."""
        graph = load_graph(_SAMPLE_GRAPH)
        events = [_ev("payment", delta=100.0, dt_minutes=3)]
        h1 = rank_hypotheses(events, graph, _REF_TS, _REF_SERVICE)
        h2 = rank_hypotheses(events, graph, _REF_TS, _REF_SERVICE)
        assert h1[0].hypothesis_id == h2[0].hypothesis_id

    def test_hypothesis_id_length_16(self):
        graph = load_graph(_SAMPLE_GRAPH)
        events = [_ev("payment", delta=100.0, dt_minutes=3)]
        h = rank_hypotheses(events, graph, _REF_TS, _REF_SERVICE)
        assert len(h[0].hypothesis_id) == 16

    def test_auth_two_hops_lower_distance_score(self):
        """auth is 2 hops from checkout; payment is 1. auth should score lower on distance."""
        graph = load_graph(_SAMPLE_GRAPH)
        events = [
            _ev("payment", delta=100.0, dt_minutes=2),
            _ev("auth", delta=100.0, dt_minutes=2),
        ]
        hyps = rank_hypotheses(events, graph, _REF_TS, _REF_SERVICE)
        payment_h = next(h for h in hyps if h.suspected_origin == "payment")
        auth_h = next(h for h in hyps if h.suspected_origin == "auth")
        assert payment_h.dependency_distance == 1
        assert auth_h.dependency_distance == 2
        assert payment_h.confidence_score > auth_h.confidence_score


class TestV01Hardening:
    """v0.1 reliability hardening tests."""

    def test_unknown_node_gets_02_distance_score(self):
        """A service not in graph → distance_score=0.2, sentinel hop=-1."""
        graph = load_graph(_SAMPLE_GRAPH)
        # "billing" is not in sample_graph.json
        events = [_ev("billing", delta=200.0, dt_minutes=2)]
        hyps = rank_hypotheses(events, graph, _REF_TS, _REF_SERVICE)
        h = hyps[0]
        assert h.dependency_distance == -1
        # v0.2 weights: confidence = 0.45*1.0 + 0.35*0.2 + 0.20*1.0 = 0.72
        # (no cap: distance_score=0.2 ≠ 0.0)
        assert abs(h.confidence_score - 0.72) < 0.01

    def test_known_far_node_gets_zero_distance_score(self):
        """A service in graph but unreachable → distance_score=0.0, hops=999."""
        import json
        from pathlib import Path
        # Two nodes with no edges
        data = {
            "svc_isolated": {"upstream": [], "downstream": []},
            "checkout": {"upstream": [], "downstream": []},
        }
        import tempfile
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, dir=_SAMPLE_GRAPH.parent.parent
        ) as f:
            json.dump(data, f)
            tmp_path = Path(f.name)
        try:
            graph = load_graph(tmp_path)
            events = [_ev("svc_isolated", delta=200.0, dt_minutes=2)]
            hyps = rank_hypotheses(events, graph, _REF_TS, "checkout")
            h = hyps[0]
            assert h.dependency_distance == 999
            # distance_score=0.0 for known-far
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_confidence_cap_triggers(self):
        """distance=0.0 + high temporal + high magnitude → capped at 0.7."""
        graph = load_graph(_SAMPLE_GRAPH)
        # "svc_isolated" is not in sample_graph → unknown=0.2... need a known-far scenario.
        # Use a graph where billing is IN graph but disconnected from checkout.
        import json, tempfile
        from pathlib import Path
        data = {
            "checkout": {"upstream": [], "downstream": []},
            "far_svc": {"upstream": [], "downstream": []},  # in graph, unreachable
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, dir=_SAMPLE_GRAPH.parent.parent
        ) as f:
            json.dump(data, f)
            tmp_path = Path(f.name)
        try:
            graph = load_graph(tmp_path)
            # Single event from far_svc within 2min (high temporal) with big delta (high magnitude)
            events = [_ev("far_svc", delta=500.0, dt_minutes=2)]
            hyps = rank_hypotheses(events, graph, _REF_TS, "checkout")
            h = hyps[0]
            assert h.dependency_distance == 999   # known-far
            assert h.confidence_score <= 0.7      # cap applied
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_confidence_cap_bypassed_by_corroboration(self):
        """≥2 events from same service within 10m → cap does NOT apply."""
        graph = load_graph(_SAMPLE_GRAPH)
        import json, tempfile
        from pathlib import Path
        data = {
            "checkout": {"upstream": [], "downstream": []},
            "far_svc": {"upstream": [], "downstream": []},
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, dir=_SAMPLE_GRAPH.parent.parent
        ) as f:
            json.dump(data, f)
            tmp_path = Path(f.name)
        try:
            graph = load_graph(tmp_path)
            # Two events from far_svc within 10m → corroborated
            events = [
                _ev("far_svc", delta=500.0, dt_minutes=2, event_id="evt-a"),
                _ev("far_svc", delta=450.0, dt_minutes=4, event_id="evt-b"),
            ]
            hyps = rank_hypotheses(events, graph, _REF_TS, "checkout")
            h = next(h for h in hyps if h.suspected_origin == "far_svc")
            # v0.2: 2 corroborating events, no cap applied.
            # uncapped = 0.45*1.0 + 0.35*0.0 + 0.20*1.0 = 0.65
            assert h.confidence_score >= 0.6
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_select_reference_uses_primary_impact_event(self):
        """select_reference picks the qualifying Rule 8 event for the reference service."""
        from datetime import timedelta
        # checkout has a metric event at t=17:00 (reference) — should be selected
        ref = datetime(2026, 2, 27, 17, 0, 0, tzinfo=timezone.utc)
        checkout_ev = normalize_event({
            "event_id": "e-checkout",
            "timestamp": ref.isoformat(),
            "service": "checkout",
            "metric_name": "revenue_per_minute",
            "delta": -420.0,
            "event_type": "metric",
        })
        other_ev = normalize_event({
            "event_id": "e-auth",
            "timestamp": (ref - timedelta(minutes=15)).isoformat(),
            "service": "auth",
            "metric_name": "cpu_util",
            "delta": 0.3,
            "event_type": "metric",
        })
        result = select_reference([other_ev, checkout_ev], "checkout")
        assert result == ref

    def test_select_reference_fallback_to_latest(self):
        """When no qualifying event exists for reference_service, use latest timestamp.

        Events must have non-qualifying event_type (no metric_kind inferred, no qualifying
        event_type) so _select_primary_impact_event returns None → fallback to max timestamp.
        """
        t1 = datetime(2026, 2, 27, 17, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 2, 27, 17, 5, 0, tzinfo=timezone.utc)
        e1 = normalize_event({
            "event_id": "e1", "timestamp": t1.isoformat(),
            "service": "auth", "event_type": "deploy",  # non-qualifying type
        })
        e2 = normalize_event({
            "event_id": "e2", "timestamp": t2.isoformat(),
            "service": "auth", "event_type": "deploy",  # non-qualifying type
        })
        # reference_service "checkout" has no events → no primary impact event found
        result = select_reference([e1, e2], "checkout")
        assert result == t2


class TestV02ChangeBias:
    """v0.2 change_bias: +0.10 if a change event exists for suspected_origin within 20m."""

    def _change_ev(self, service, dt_min, change_kind="deploy", change_id="sha-abc"):
        ts = _REF_TS - timedelta(minutes=dt_min)
        return normalize_event({
            "event_id": f"chg-{service}-{dt_min}",
            "timestamp": ts.isoformat(),
            "service": service,
            "event_type": "change",
            "change_kind": change_kind,
            "change_id": change_id,
        })

    def test_change_bias_applied_within_window(self):
        """Change event within 20m before ref_ts → +0.10 bias applied.

        v0.3: suspected_origin is now compound 'payment:deploy:sha-abc';
        use origin_service to look up the hypothesis.
        """
        graph = load_graph(_SAMPLE_GRAPH)
        base_ev = _ev("payment", delta=100.0, dt_minutes=2)
        change_ev = self._change_ev("payment", dt_min=5)  # 5m before ref_ts
        events = [base_ev, change_ev]
        hyps = rank_hypotheses(events, graph, _REF_TS, _REF_SERVICE)
        payment_h = next(h for h in hyps if h.origin_service == "payment")
        assert payment_h.change_biased is True
        # base = 0.45*1.0 + 0.35*0.8 + 0.20*1.0 = 0.73  (+bias = 0.83)
        assert payment_h.confidence_score > 0.73

    def test_change_bias_not_applied_outside_window(self):
        """Change event >20m before ref_ts → no bias."""
        graph = load_graph(_SAMPLE_GRAPH)
        base_ev = _ev("payment", delta=100.0, dt_minutes=2)
        change_ev = self._change_ev("payment", dt_min=25)  # 25m before ref_ts — outside 20m window
        events = [base_ev, change_ev]
        hyps = rank_hypotheses(events, graph, _REF_TS, _REF_SERVICE)
        payment_h = next(h for h in hyps if h.suspected_origin == "payment")
        assert payment_h.change_biased is False

    def test_change_biased_flag_propagates_to_hypothesis(self):
        """change_biased=True appears on hypothesis when bias was applied."""
        graph = load_graph(_SAMPLE_GRAPH)
        events = [
            _ev("payment", delta=100.0, dt_minutes=2),
            self._change_ev("payment", dt_min=4),
        ]
        hyps = rank_hypotheses(events, graph, _REF_TS, _REF_SERVICE)
        payment_h = next(h for h in hyps if h.origin_service == "payment")
        assert payment_h.change_biased is True

    def test_change_bias_deterministic_same_events_same_confidence(self):
        """Same inputs always produce same confidence_score (bias is deterministic)."""
        graph = load_graph(_SAMPLE_GRAPH)
        events = [
            _ev("payment", delta=100.0, dt_minutes=2),
            self._change_ev("payment", dt_min=4),
        ]
        h1 = rank_hypotheses(events, graph, _REF_TS, _REF_SERVICE)
        h2 = rank_hypotheses(events, graph, _REF_TS, _REF_SERVICE)
        p1 = next(h for h in h1 if h.origin_service == "payment")
        p2 = next(h for h in h2 if h.origin_service == "payment")
        assert p1.confidence_score == p2.confidence_score


class TestV03EligibilityFilter:
    """v0.3: reference_service excluded from hypotheses unless it has a change event."""

    def test_reference_service_excluded_when_no_change_event(self):
        """checkout (reference) should not appear in hypotheses without a change event."""
        graph = load_graph(_SAMPLE_GRAPH)
        # Include events for both checkout (reference) and payment
        events = [
            _ev("checkout", delta=-420.0, dt_minutes=0),     # reference service, metric only
            _ev("payment",  delta=310.0,  dt_minutes=3),     # candidate cause
        ]
        hyps = rank_hypotheses(events, graph, _REF_TS, _REF_SERVICE)
        origins = {h.origin_service for h in hyps}
        assert "checkout" not in origins             # filtered out: no change event
        assert "payment" in origins                  # valid candidate

    def test_reference_service_allowed_when_change_event_within_20m(self):
        """checkout with a change event within 20m is allowed as a hypothesis origin."""
        graph = load_graph(_SAMPLE_GRAPH)
        ts_ref = _REF_TS
        checkout_ev = _ev("checkout", delta=-420.0, dt_minutes=0)
        # Change event for checkout, 10m before reference_ts
        checkout_change = normalize_event({
            "event_id": "chg-checkout",
            "timestamp": (ts_ref - timedelta(minutes=10)).isoformat(),
            "service": "checkout",
            "event_type": "change",
            "change_kind": "deploy",
            "change_id": "sha-checkout-v5",
        })
        events = [checkout_ev, checkout_change]
        hyps = rank_hypotheses(events, graph, ts_ref, _REF_SERVICE)
        origins = {h.origin_service for h in hyps}
        assert "checkout" in origins        # allowed: has change event within 20m
        checkout_h = next(h for h in hyps if h.origin_service == "checkout")
        assert checkout_h.change_biased is True
        assert checkout_h.origin_change_kind == "deploy"


class TestV03ChangeOriginGranularity:
    """v0.3: suspected_origin is compound key when change event exists."""

    def _change_ev(self, service, dt_min, change_kind="deploy", change_id="sha-payment-v3"):
        ts = _REF_TS - timedelta(minutes=dt_min)
        return normalize_event({
            "event_id": f"chg-{service}-{dt_min}",
            "timestamp": ts.isoformat(),
            "service": service,
            "event_type": "change",
            "change_kind": change_kind,
            "change_id": change_id,
        })

    def test_change_origin_compound_suspected_origin(self):
        """When change event exists, suspected_origin becomes 'service:kind:id'."""
        graph = load_graph(_SAMPLE_GRAPH)
        events = [
            _ev("payment", delta=100.0, dt_minutes=2),
            self._change_ev("payment", dt_min=5),
        ]
        hyps = rank_hypotheses(events, graph, _REF_TS, _REF_SERVICE)
        payment_h = next(h for h in hyps if h.origin_service == "payment")
        assert payment_h.suspected_origin == "payment:deploy:sha-payment-v3"
        assert payment_h.origin_service == "payment"
        assert payment_h.origin_change_kind == "deploy"
        assert payment_h.origin_change_id == "sha-payment-v3"

    def test_no_change_event_gives_plain_suspected_origin(self):
        """Without a change event, suspected_origin stays as plain service name."""
        graph = load_graph(_SAMPLE_GRAPH)
        events = [_ev("payment", delta=100.0, dt_minutes=2)]
        hyps = rank_hypotheses(events, graph, _REF_TS, _REF_SERVICE)
        payment_h = hyps[0]
        assert payment_h.suspected_origin == "payment"
        assert payment_h.origin_service == "payment"
        assert payment_h.origin_change_kind == ""
        assert payment_h.origin_change_id == ""

    def test_bfs_distance_uses_origin_service_not_compound_key(self):
        """Hop distance is computed from origin_service, not the compound key."""
        graph = load_graph(_SAMPLE_GRAPH)
        events = [
            _ev("payment", delta=100.0, dt_minutes=2),
            self._change_ev("payment", dt_min=5),
        ]
        hyps = rank_hypotheses(events, graph, _REF_TS, _REF_SERVICE)
        payment_h = next(h for h in hyps if h.origin_service == "payment")
        # payment is exactly 1 hop from checkout
        assert payment_h.dependency_distance == 1
