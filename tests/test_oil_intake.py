"""Tests: oil/intake/normalizer.py"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone

from oil.intake.normalizer import normalize_event, normalize_events


_BASE = {
    "event_id": "evt-test-001",
    "timestamp": "2026-02-27T17:00:00Z",
    "service": "checkout",
}


class TestNormalizeEvent:
    def test_full_event_round_trips(self):
        raw = {
            **_BASE,
            "metric_name": "revenue",
            "metric_value": 1200.0,
            "delta": -420.0,
            "event_type": "metric",
            "source": "prometheus",
            "related_deployment": "deploy-v2",
            "business_tag": "revenue",
        }
        e = normalize_event(raw)
        assert e.event_id == "evt-test-001"
        assert e.service == "checkout"
        assert e.metric_name == "revenue"
        assert e.metric_value == 1200.0
        assert e.delta == -420.0
        assert e.event_type == "metric"
        assert e.source == "prometheus"
        assert e.related_deployment == "deploy-v2"
        assert e.business_tag == "revenue"

    def test_timestamp_parsed_to_utc_datetime(self):
        e = normalize_event(_BASE)
        assert isinstance(e.timestamp, datetime)
        assert e.timestamp.tzinfo is not None
        assert e.timestamp == datetime(2026, 2, 27, 17, 0, 0, tzinfo=timezone.utc)

    def test_naive_timestamp_treated_as_utc(self):
        raw = {**_BASE, "timestamp": "2026-02-27T17:00:00"}
        e = normalize_event(raw)
        assert e.timestamp.tzinfo is not None
        assert e.timestamp == datetime(2026, 2, 27, 17, 0, 0, tzinfo=timezone.utc)

    def test_offset_timestamp_converted_to_utc(self):
        raw = {**_BASE, "timestamp": "2026-02-27T12:00:00-05:00"}
        e = normalize_event(raw)
        assert e.timestamp == datetime(2026, 2, 27, 17, 0, 0, tzinfo=timezone.utc)

    def test_delta_none_coerced_to_zero(self):
        raw = {**_BASE, "delta": None}
        e = normalize_event(raw)
        assert e.delta == 0.0

    def test_delta_missing_coerced_to_zero(self):
        e = normalize_event(_BASE)
        assert e.delta == 0.0

    def test_optional_fields_default_to_empty(self):
        e = normalize_event(_BASE)
        assert e.metric_name == ""
        assert e.event_type == ""
        assert e.source == ""
        assert e.related_deployment == ""
        assert e.business_tag == ""

    def test_missing_event_id_raises(self):
        raw = {"timestamp": "2026-02-27T17:00:00Z", "service": "checkout"}
        with pytest.raises(ValueError, match="event_id"):
            normalize_event(raw)

    def test_missing_timestamp_raises(self):
        raw = {"event_id": "x", "service": "checkout"}
        with pytest.raises(ValueError, match="timestamp"):
            normalize_event(raw)

    def test_missing_service_raises(self):
        raw = {"event_id": "x", "timestamp": "2026-02-27T17:00:00Z"}
        with pytest.raises(ValueError, match="service"):
            normalize_event(raw)

    def test_normalize_events_list(self):
        raws = [_BASE, {**_BASE, "event_id": "evt-002"}]
        events = normalize_events(raws)
        assert len(events) == 2
        assert events[0].event_id == "evt-test-001"
        assert events[1].event_id == "evt-002"


class TestMetricKindInference:
    def _ev(self, metric_name):
        return normalize_event({**_BASE, "metric_name": metric_name})

    def test_latency_inferred_from_p99(self):
        assert self._ev("p99_latency_ms").metric_kind == "latency"

    def test_latency_inferred_from_latency_keyword(self):
        assert self._ev("response_latency").metric_kind == "latency"

    def test_error_rate_inferred_from_error(self):
        assert self._ev("error_rate").metric_kind == "error_rate"

    def test_saturation_inferred_from_cpu(self):
        assert self._ev("cpu_utilization").metric_kind == "saturation"

    def test_business_kpi_inferred_from_revenue(self):
        assert self._ev("revenue_per_minute").metric_kind == "business_kpi"

    def test_no_match_returns_empty(self):
        assert self._ev("cache_miss_rate").metric_kind == ""

    def test_explicit_metric_kind_overrides_inference(self):
        e = normalize_event({**_BASE, "metric_name": "cpu_usage", "metric_kind": "business_kpi"})
        assert e.metric_kind == "business_kpi"

    def test_metric_kind_empty_string_triggers_inference(self):
        e = normalize_event({**_BASE, "metric_name": "p99_response", "metric_kind": ""})
        assert e.metric_kind == "latency"

