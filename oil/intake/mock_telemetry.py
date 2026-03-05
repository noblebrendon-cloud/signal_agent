"""
OIL Intake -- Mock Telemetry (v0.2)

Simulates a deployment spike scenario:
- checkout service:  high-delta revenue metric (reference/symptom)
- auth service:      error_rate spike + cpu utilization noise
- payment service:   latency increase + DEPLOY change event (root cause candidate)
- inventory service: minor noise event (delta=None tests normalizer coercion)
"""
from __future__ import annotations

MOCK_EVENTS: list[dict] = [
    {
        "event_id": "evt-001",
        "timestamp": "2026-02-27T17:00:00Z",
        "service": "checkout",
        "metric_name": "revenue_per_minute",
        "metric_value": 1200.0,
        "delta": -420.0,
        "event_type": "metric",
        "source": "prometheus",
        "related_deployment": "deploy-checkout-v2.4",
        "business_tag": "revenue",
    },
    {
        "event_id": "evt-002",
        "timestamp": "2026-02-27T16:58:30Z",
        "service": "auth",
        "metric_name": "error_rate",
        "metric_value": 0.12,
        "delta": 0.09,
        "event_type": "error_rate",
        "source": "prometheus",
        "related_deployment": "deploy-auth-v1.9",
        "business_tag": "access",
    },
    {
        "event_id": "evt-003",
        "timestamp": "2026-02-27T16:57:00Z",
        "service": "payment",
        "metric_name": "p99_latency_ms",
        "metric_value": 980.0,
        "delta": 310.0,
        "event_type": "latency",
        "source": "datadog",
        "related_deployment": "",
        "business_tag": "transactions",
    },
    {
        "event_id": "evt-004",
        "timestamp": "2026-02-27T16:55:00Z",
        "service": "inventory",
        "metric_name": "cache_miss_rate",
        "metric_value": 0.03,
        "delta": None,
        "event_type": "metric",
        "source": "internal",
        "related_deployment": "",
        "business_tag": "fulfillment",
    },
    {
        "event_id": "evt-005",
        "timestamp": "2026-02-27T16:50:00Z",
        "service": "auth",
        "metric_name": "cpu_utilization",
        "metric_value": 0.88,
        "delta": 0.35,
        "event_type": "metric",
        "source": "prometheus",
        "related_deployment": "deploy-auth-v1.9",
        "business_tag": "access",
    },
    {
        "event_id": "evt-006",
        "timestamp": "2026-02-27T16:55:30Z",
        "service": "payment",
        "event_type": "change",
        "change_kind": "deploy",
        "change_id": "sha-payment-v3.1.2",
        "source": "spinnaker",
        "related_deployment": "deploy-payment-v3.1.2",
        "business_tag": "transactions",
    },
]
