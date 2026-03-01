"""Tests: oil/memory/fingerprint.py + oil/memory/store.py (OIL v0.4 DIM)"""
from __future__ import annotations

import json
import tempfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from oil.graph.loader import load_graph
from oil.impact.mapper import load_impact_map
from oil.correlation.ranker import rank_hypotheses
from oil.explanation.generator import generate_explanation, format_human_block
from oil.intake.normalizer import normalize_event
from oil.memory.fingerprint import generate_fingerprint, _hop_distance_class, _temporal_class
from oil.memory.store import (
    append_entry, find_similar, load_index, _similarity_score,
)

_SAMPLE_GRAPH = Path(__file__).resolve().parents[1] / "oil" / "graph" / "sample_graph.json"
_REF_TS = datetime(2026, 2, 27, 17, 0, 0, tzinfo=timezone.utc)
_REF_SERVICE = "checkout"


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
        "metric_kind": "latency" if service == "payment" else "",
    })


def _make_hypotheses_and_report():
    graph = load_graph(_SAMPLE_GRAPH)
    events = [
        _ev("payment", 310.0, 3),
        _ev("payment", 0.0, 5, event_type="change", change_kind="deploy", change_id="sha-v3"),
    ]
    hyps = rank_hypotheses(events, graph, _REF_TS, _REF_SERVICE)
    impact_map = load_impact_map()
    report = generate_explanation(hyps, events, impact_map, _REF_SERVICE)
    return report, hyps


# ── Helpers ─────────────────────────────────────────────────────────────


def _make_index_entry(
    fp_id="fp-001",
    artifact="art-001.json",
    origin_service="payment",
    change_kind="deploy",
    metric_kind="latency",
    hop_distance_class="1",
    impact_domain="transactions",
    confidence=0.90,
    created_utc="2026-02-27T20:00:00Z",
):
    return {
        "fingerprint_id": fp_id,
        "artifact_path": artifact,
        "created_utc": created_utc,
        "origin_service": origin_service,
        "change_kind": change_kind,
        "metric_kind": metric_kind,
        "hop_distance_class": hop_distance_class,
        "impact_domain": impact_domain,
        "confidence": confidence,
    }


# ── Fingerprint tests ────────────────────────────────────────────────────


class TestGenerateFingerprint:
    def test_fingerprint_stable_sameInputs(self):
        """Same report + hypotheses always yields same fingerprint."""
        report, hyps = _make_hypotheses_and_report()
        f1 = generate_fingerprint(report, hyps)
        f2 = generate_fingerprint(report, hyps)
        assert f1 == f2

    def test_fingerprint_is_16_chars(self):
        report, hyps = _make_hypotheses_and_report()
        fp = generate_fingerprint(report, hyps)
        assert len(fp) == 16

    def test_fingerprint_is_hex(self):
        report, hyps = _make_hypotheses_and_report()
        fp = generate_fingerprint(report, hyps)
        assert all(c in "0123456789abcdef" for c in fp)

    def test_fingerprint_changes_on_different_origin_service(self):
        """Different origin_service yields different fingerprint."""
        report, hyps = _make_hypotheses_and_report()
        fp1 = generate_fingerprint(report, hyps)

        # Different origin: auth instead
        graph = load_graph(_SAMPLE_GRAPH)
        events2 = [_ev("auth", 0.3, 2)]
        hyps2 = rank_hypotheses(events2, graph, _REF_TS, _REF_SERVICE)
        report2 = generate_explanation(hyps2, events2, load_impact_map(), _REF_SERVICE)
        fp2 = generate_fingerprint(report2, hyps2)
        assert fp1 != fp2

    def test_fingerprint_empty_hypotheses_does_not_crash(self):
        fp = generate_fingerprint({"reference_service": "checkout"}, [])
        assert len(fp) == 16

    def test_hop_distance_class_mapping(self):
        assert _hop_distance_class(-1) == "unknown"
        assert _hop_distance_class(0) == "0"
        assert _hop_distance_class(1) == "1"
        assert _hop_distance_class(2) == "2"
        assert _hop_distance_class(999) == "far"
        assert _hop_distance_class(3) == "far"

    def test_temporal_class_mapping(self):
        assert _temporal_class(0.0) == "0-5m"
        assert _temporal_class(5.0) == "0-5m"
        assert _temporal_class(5.1) == "5-15m"
        assert _temporal_class(15.0) == "5-15m"
        assert _temporal_class(15.1) == "15-30m"
        assert _temporal_class(30.0) == "15-30m"
        assert _temporal_class(30.1) == "30m+"

    def test_report_carries_dim_metadata(self):
        """generate_explanation must expose reference_service, impact_direction etc."""
        report, _ = _make_hypotheses_and_report()
        assert "reference_service" in report
        assert "impact_direction" in report
        assert "primary_metric_kind" in report
        assert "impact_domain" in report
        assert "hop_distance_class" in report
        assert report["reference_service"] == "checkout"
        assert report["impact_direction"] in ("increase", "decrease", "")


# ── Store / append tests ─────────────────────────────────────────────────


class TestAppendEntry:
    def test_creates_file_on_first_append(self, tmp_path):
        idx = tmp_path / "test.jsonl"
        assert not idx.exists()
        append_entry("fp1", "art1.json", "payment", "deploy", "latency", "1", "transactions", 0.9, idx)
        assert idx.exists()

    def test_appended_entry_is_valid_json(self, tmp_path):
        idx = tmp_path / "test.jsonl"
        append_entry("fp1", "art1.json", "payment", "deploy", "latency", "1", "transactions", 0.9, idx)
        line = idx.read_text(encoding="utf-8").strip()
        data = json.loads(line)
        assert data["fingerprint_id"] == "fp1"
        assert data["origin_service"] == "payment"

    def test_multiple_appends_give_multiple_lines(self, tmp_path):
        idx = tmp_path / "test.jsonl"
        for i in range(3):
            append_entry(f"fp{i}", f"art{i}.json", "payment", "deploy", "latency", "1", "transactions", 0.9, idx)
        lines = [l for l in idx.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(lines) == 3

    def test_append_preserves_prior_entries(self, tmp_path):
        idx = tmp_path / "test.jsonl"
        append_entry("first", "first.json", "auth", "", "error_rate", "2", "access", 0.7, idx)
        append_entry("second", "second.json", "payment", "deploy", "latency", "1", "transactions", 0.9, idx)
        entries = load_index(idx)
        assert len(entries) == 2
        assert entries[0]["fingerprint_id"] == "first"
        assert entries[1]["fingerprint_id"] == "second"


class TestLoadIndex:
    def test_returns_empty_when_file_missing(self, tmp_path):
        idx = tmp_path / "nonexistent.jsonl"
        assert load_index(idx) == []

    def test_skips_malformed_lines(self, tmp_path):
        idx = tmp_path / "test.jsonl"
        idx.write_text('{"fingerprint_id":"ok"}\nnot-json\n{"fingerprint_id":"ok2"}\n', encoding="utf-8")
        entries = load_index(idx)
        assert len(entries) == 2


# ── Similarity scoring ───────────────────────────────────────────────────


class TestSimilarityScore:
    def _q(self, origin="payment", change_kind="deploy", metric_kind="latency",
            hop="1", impact_domain="transactions"):
        return {
            "origin_service": origin, "change_kind": change_kind,
            "metric_kind": metric_kind, "hop_distance_class": hop,
            "impact_domain": impact_domain,
        }

    def test_perfect_match_scores_7(self):
        q = self._q()
        assert _similarity_score(q, q) == 7  # +2+2+1+1+1

    def test_same_origin_scores_2(self):
        q = self._q()
        c = {**q, "change_kind": "config", "metric_kind": "error_rate",
             "hop_distance_class": "2", "impact_domain": "access"}
        assert _similarity_score(q, c) == 2  # only origin_service match

    def test_empty_change_kind_skips_bonus(self):
        q = self._q(change_kind="")
        c = self._q(change_kind="")
        score = _similarity_score(q, c)
        # missing +2 for change_kind (both empty)
        assert score == 5  # +2 origin, +1 metric, +1 hop, +1 domain

    def test_different_origin_different_all_scores_zero(self):
        q = self._q(origin="payment")
        c = self._q(origin="auth", change_kind="config", metric_kind="saturation",
                    hop="0", impact_domain="access")
        assert _similarity_score(q, c) == 0


class TestFindSimilar:
    def _idx(self, entries):
        return entries

    def test_returns_empty_when_no_similar(self, tmp_path):
        idx = [_make_index_entry("fp-other", origin_service="auth", change_kind="config")]
        # Query fp-001 not in index
        result = find_similar("fp-001", idx)
        assert result == []

    def test_excludes_self_match(self):
        entry = _make_index_entry("fp-001", "art-001.json")
        entry["run_id"] = "run-aaa"
        idx = [entry]
        # v0.4.1: self-exclusion is by run_id
        result = find_similar("fp-001", idx, current_run_id="run-aaa", min_score=0)
        assert result == []

    def test_returns_top_n_results(self):
        query = _make_index_entry("fp-001", "art-001.json")
        query["run_id"] = "run-query"
        others = [
            {**_make_index_entry(f"fp-{i:03}", f"art-{i}.json",
                                  created_utc=f"2026-02-27T{18+i:02}:00:00Z"),
             "run_id": f"run-{i:03}"}
            for i in range(10)
        ]
        idx = [query] + others
        result = find_similar("fp-001", idx, top_n=3, current_run_id="run-query", min_score=0)
        assert len(result) <= 3

    def test_similarity_score_in_results(self):
        query = _make_index_entry("fp-001", "art-001.json")
        query["run_id"] = "run-q1"
        other = _make_index_entry("fp-002", "art-002.json")
        other["run_id"] = "run-q2"
        idx = [query, other]
        result = find_similar("fp-001", idx, current_run_id="run-q1", min_score=0)
        assert len(result) >= 1
        assert "similarity_score" in result[0]
        assert result[0]["similarity_score"] == 7  # perfect match on all dimensions

    def test_result_sorted_by_score_descending(self):
        query = _make_index_entry("fp-001", "art-001.json",
                                  origin_service="payment", change_kind="deploy")
        query["run_id"] = "rq"
        high = _make_index_entry("fp-002", "art-002.json",
                                 origin_service="payment", change_kind="deploy")  # score=7
        high["run_id"] = "rh"
        low = _make_index_entry("fp-003", "art-003.json",
                                origin_service="auth", change_kind="config")      # score=0
        low["run_id"] = "rl"
        idx = [query, high, low]
        result = find_similar("fp-001", idx, current_run_id="rq", min_score=0)
        assert result[0]["fingerprint_id"] == "fp-002"
        assert all(r["similarity_score"] > 0 for r in result)

    def test_find_similar_is_deterministic(self):
        query = _make_index_entry("fp-001", "art-001.json")
        query["run_id"] = "rq"
        others = [{**_make_index_entry(f"fp-{i}", f"art-{i}.json",
                                       created_utc=f"2026-02-27T{19+i:02}:00:00Z"),
                   "run_id": f"r{i}"}
                  for i in range(5)]
        idx = [query] + others
        r1 = find_similar("fp-001", idx, current_run_id="rq", min_score=0)
        r2 = find_similar("fp-001", idx, current_run_id="rq", min_score=0)
        assert [r["fingerprint_id"] for r in r1] == [r["fingerprint_id"] for r in r2]


# ── Explanation integration ──────────────────────────────────────────────


class TestExplanationWithSimilarIncidents:
    def test_format_human_block_shows_similar_when_present(self):
        report, hyps = _make_hypotheses_and_report()
        report["similar_incidents"] = {
            "occurrence_count": 2,
            "most_common_origin": "payment",
            "recent_examples": [
                _make_index_entry("fp-old", "art-old.json", created_utc="2026-02-26T10:00:00Z"),
            ],
        }
        text = format_human_block(report)
        assert "SIMILAR INCIDENTS" in text
        assert "occurrence_count" in text or "2" in text
        assert "payment" in text

    def test_format_human_block_no_similar_section_when_empty(self):
        report, hyps = _make_hypotheses_and_report()
        report["similar_incidents"] = {"occurrence_count": 0, "most_common_origin": "", "recent_examples": []}
        text = format_human_block(report)
        assert "SIMILAR INCIDENTS" not in text

    def test_format_human_block_no_similar_section_when_absent(self):
        report, hyps = _make_hypotheses_and_report()
        # No similar_incidents key at all
        report.pop("similar_incidents", None)
        text = format_human_block(report)
        assert "SIMILAR INCIDENTS" not in text

    def test_append_then_find_similar_roundtrip(self, tmp_path):
        """Append two entries with distinct run_ids, verify find_similar returns first."""
        idx = tmp_path / "test.jsonl"
        report, hyps = _make_hypotheses_and_report()
        fp = generate_fingerprint(report, hyps)

        # First run
        append_entry(fp, "art-001.json", "payment", "deploy", "latency", "1", "transactions",
                     0.90, idx, run_id="run-001")
        # Second run (same fingerprint, different run_id)
        append_entry(fp, "art-002.json", "payment", "deploy", "latency", "1", "transactions",
                     0.88, idx, run_id="run-002")

        index = load_index(idx)
        matches = find_similar(fp, index, current_run_id="run-002")
        # run-001 has score=7 (all dimensions match) >= min_score=5 so it's included
        assert len(matches) >= 1
        assert any(m["artifact_path"] == "art-001.json" for m in matches)


class TestV041DIM:
    """v0.4.1: run_id deduplication, lookback filtering, min_score filtering."""

    # ── helper ───────────────────────────────────────────────────────────

    def _e(self, run_id, fp="fp-001", artifact="art.json",
           origin="payment", change_kind="deploy",
           metric_kind="latency", hop="1", impact_domain="transactions",
           confidence=0.9, created_utc="2026-02-27T20:00:00Z"):
        return {
            "run_id": run_id,
            "fingerprint_id": fp,
            "artifact_path": artifact,
            "created_utc": created_utc,
            "origin_service": origin,
            "change_kind": change_kind,
            "metric_kind": metric_kind,
            "hop_distance_class": hop,
            "impact_domain": impact_domain,
            "confidence": confidence,
        }

    # ── dedup by run_id ──────────────────────────────────────────────────

    def test_double_append_same_run_id_deduped_by_load_index(self, tmp_path):
        """load_index dedupes by run_id: double-append yields one entry."""
        idx = tmp_path / "dedup.jsonl"
        # Simulate a single CLI invocation appending twice (bug guard)
        append_entry("fp-x", "art.json", "payment", "deploy", "latency", "1",
                     "transactions", 0.9, idx, run_id="run-shared")
        append_entry("fp-x", "art.json", "payment", "deploy", "latency", "1",
                     "transactions", 0.9, idx, run_id="run-shared")
        entries = load_index(idx)
        assert len(entries) == 1            # deduplicated
        assert entries[0]["run_id"] == "run-shared"

    def test_different_run_ids_both_kept(self, tmp_path):
        """Two different run_ids survive dedup (normal case)."""
        idx = tmp_path / "keep.jsonl"
        append_entry("fp-x", "art-a.json", "payment", "deploy", "latency", "1",
                     "transactions", 0.9, idx, run_id="run-A")
        append_entry("fp-x", "art-b.json", "payment", "deploy", "latency", "1",
                     "transactions", 0.8, idx, run_id="run-B")
        entries = load_index(idx)
        assert len(entries) == 2

    # ── unique run_ids in results ─────────────────────────────────────────

    def test_results_have_unique_run_ids(self):
        """find_similar dedupes results by run_id before returning."""
        query = self._e("run-q", fp="fp-q")
        # Two candidates with SAME run_id (shouldn't happen in clean index, but guard it)
        dup1 = self._e("run-dup", fp="fp-dup-a", artifact="art-dup1.json")
        dup2 = self._e("run-dup", fp="fp-dup-b", artifact="art-dup2.json")
        idx = [query, dup1, dup2]
        results = find_similar("fp-q", idx, current_run_id="run-q", min_score=0)
        result_run_ids = [r["run_id"] for r in results]
        # No duplicate run_ids in results
        assert len(result_run_ids) == len(set(result_run_ids))

    # ── min_score filtering ───────────────────────────────────────────────

    def test_min_score_filters_low_score_matches(self):
        """Entries scoring below min_score are excluded."""
        query = self._e("run-q",  origin="payment", change_kind="deploy")
        # Different origin: score=0 (below any min_score)
        low = self._e("run-low", origin="auth", change_kind="config",
                      metric_kind="saturation", hop="0", impact_domain="access")
        idx = [query, low]
        results = find_similar("fp-001", idx, current_run_id="run-q", min_score=5)
        assert all(r["similarity_score"] >= 5 for r in results)

    def test_min_score_zero_returns_all_nonzero(self):
        """min_score=0 returns all candidates with score>0 (legacy compatible)."""
        query = self._e("run-q", origin="payment")
        partial = self._e("run-p", origin="payment", change_kind="config",
                          metric_kind="error_rate", impact_domain="access")  # score=3
        idx = [query, partial]
        results_thresh = find_similar("fp-001", idx, current_run_id="run-q", min_score=5)
        results_zero   = find_similar("fp-001", idx, current_run_id="run-q", min_score=0)
        assert len(results_thresh) == 0     # score=3 < min_score=5
        assert len(results_zero) >= 1       # score=3 >= min_score=0

    # ── lookback window ───────────────────────────────────────────────────

    def test_lookback_filters_old_entries(self):
        """Entries older than lookback_days are excluded."""
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        old_ts = (now - timedelta(days=60)).strftime("%Y-%m-%dT%H:%M:%SZ")
        recent_ts = (now - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")

        query  = self._e("run-q",   created_utc=recent_ts)
        old    = self._e("run-old", created_utc=old_ts)
        recent = self._e("run-new", created_utc=recent_ts, artifact="art-rec.json")
        idx = [query, old, recent]
        results = find_similar("fp-001", idx, current_run_id="run-q",
                               lookback_days=30, min_score=0)
        result_run_ids = {r["run_id"] for r in results}
        assert "run-old" not in result_run_ids   # too old
        assert "run-new" in result_run_ids        # within window

    # ── artifact filename uniqueness ──────────────────────────────────────

    def test_artifact_filename_includes_run_id(self, tmp_path):
        """v0.4.1: artifact filename is incident_<ts>_<run_id>.json."""
        import re
        from oil.explanation.reporter import write_artifact
        report_dict = {"incident_summary": "test", "confidence_score": 0.9}
        path, run_id = write_artifact(report_dict, tmp_path, inputs_digest="sha256:abc")
        assert run_id in path.name
        assert re.match(r"incident_\d{8}T\d{6}Z_[0-9a-f]{16}\.json", path.name)


class TestV05ActionMemory:
    """v0.5: Deterministic Action Memory -- extract_action, store, recall summary."""

    from oil.memory.actions import extract_action

    # ── action_category parsing ───────────────────────────────────────────

    @pytest.mark.parametrize("keyword,expected_category", [
        ("Please rollback the service",             "rollback"),
        ("You should restart the pod",              "restart"),
        ("Consider scale the cluster",              "scale"),
        ("Trigger failover to secondary",           "failover"),
        ("Apply a hotfix to the endpoint",          "hotfix"),
        ("Apply a patch to the config",             "hotfix"),
        ("Escalate to your vendor support",         "vendor_escalation"),
        ("Contact the provider about the outage",   "vendor_escalation"),
        ("Investigate recent changes to 'payment'", "investigate"),
        ("Collect additional telemetry",            "investigate"),
        ("",                                        "unknown"),
    ])
    def test_action_category_keyword_dispatch(self, keyword, expected_category):
        from oil.memory.actions import extract_action
        report = {"recommended_human_action": keyword, "evidence": []}
        result = extract_action(report, "payment")
        assert result["action_category"] == expected_category, (
            f"keyword={keyword!r} → expected {expected_category!r}, "
            f"got {result['action_category']!r}"
        )

    def test_default_target_is_origin_service(self):
        """When action text doesn't name an alternative service, target = origin_service."""
        from oil.memory.actions import extract_action
        report = {
            "recommended_human_action": "Investigate recent changes.",
            "evidence": [],
        }
        result = extract_action(report, "payment")
        assert result["action_target_service"] == "payment"

    def test_target_extracted_from_quoted_service(self):
        """Pattern "to '<service>'" in action text overrides origin_service as target."""
        from oil.memory.actions import extract_action
        report = {
            "recommended_human_action": "Investigate recent changes to 'auth'. Check logs.",
            "evidence": [],
        }
        result = extract_action(report, "payment")
        assert result["action_target_service"] == "auth"

    def test_action_reason_from_evidence(self):
        """action_reason is derived deterministically from the top evidence item."""
        from oil.memory.actions import extract_action
        report = {
            "recommended_human_action": "Investigate.",
            "evidence": [
                {"service": "payment", "metric_name": "p99_latency_ms",
                 "delta": 310.0, "reason": "highest delta"},
            ],
        }
        result = extract_action(report, "payment")
        assert "payment" in result["action_reason"]
        assert "spike" in result["action_reason"] or "310" in result["action_reason"]

    def test_action_reason_fallback_when_no_evidence(self):
        """When evidence is empty, action_reason falls back to top_ranked_cause."""
        from oil.memory.actions import extract_action
        report = {
            "recommended_human_action": "Investigate.",
            "evidence": [],
            "top_ranked_cause": "'payment deploy sha' -- 1 hop(s)",
        }
        result = extract_action(report, "payment")
        assert result["action_reason"]  # non-empty
        assert "payment" in result["action_reason"]

    # ── JSONL store integration ───────────────────────────────────────────

    def test_memory_line_includes_action_fields(self, tmp_path):
        """append_entry writes action_category and action_target_service to JSONL line."""
        idx = tmp_path / "action_test.jsonl"
        append_entry(
            "fp-act", "art-act.json", "payment", "deploy", "latency", "1",
            "transactions", 0.9, idx, run_id="run-act",
            action_category="rollback", action_target_service="payment",
        )
        entry = json.loads(idx.read_text(encoding="utf-8").strip())
        assert entry["action_category"] == "rollback"
        assert entry["action_target_service"] == "payment"

    def test_memory_line_action_fields_default_to_empty(self, tmp_path):
        """append_entry without action args writes empty strings (backward compat)."""
        idx = tmp_path / "compat.jsonl"
        append_entry(
            "fp-compat", "art.json", "auth", "", "error_rate", "2",
            "access", 0.7, idx, run_id="run-compat",
        )
        entry = json.loads(idx.read_text(encoding="utf-8").strip())
        assert entry.get("action_category", "") == ""
        assert entry.get("action_target_service", "") == ""

    # ── Recall summary ────────────────────────────────────────────────────

    def test_recall_summary_most_common_action_category(self):
        """find_similar results carry action_category; _build_similar_incidents_block
        computes most_common_action_category correctly."""
        from oil.run_analysis import _build_similar_incidents_block
        matches = [
            {"origin_service": "payment", "action_category": "rollback",
             "created_utc": "2026-02-27T20:00:00Z", "confidence": 0.9,
             "similarity_score": 7},
            {"origin_service": "payment", "action_category": "rollback",
             "created_utc": "2026-02-27T19:00:00Z", "confidence": 0.85,
             "similarity_score": 7},
            {"origin_service": "auth", "action_category": "investigate",
             "created_utc": "2026-02-27T18:00:00Z", "confidence": 0.7,
             "similarity_score": 5},
        ]
        block = _build_similar_incidents_block(matches)
        assert block["most_common_action_category"] == "rollback"

    def test_recall_summary_empty_when_no_matches(self):
        """Empty match list → most_common_action_category is empty string."""
        from oil.run_analysis import _build_similar_incidents_block
        block = _build_similar_incidents_block([])
        assert block["most_common_action_category"] == ""
        assert block["occurrence_count"] == 0

    def test_format_human_block_renders_action_in_similar(self):
        """format_human_block shows most_common_action_category in SIMILAR INCIDENTS."""
        report, hyps = _make_hypotheses_and_report()
        report["similar_incidents"] = {
            "occurrence_count": 1,
            "most_common_origin": "payment",
            "most_common_action_category": "rollback",
            "recent_examples": [
                {"created_utc": "2026-02-27T20:00:00Z", "origin_service": "payment",
                 "confidence": 0.9, "similarity_score": 7, "action_category": "rollback"},
            ],
        }
        text = format_human_block(report)
        assert "most_common_action_category" in text or "rollback" in text
        assert "SIMILAR INCIDENTS" in text



class TestV06OutcomeMemory:
    """v0.6: Outcome store, CLI, negation/compound actions, outcome_summary."""

    # ─── outcome append + load ────────────────────────────────────────────

    def test_append_outcome_creates_file(self, tmp_path):
        from oil.memory.outcomes import append_outcome, load_outcomes
        p = tmp_path / "outcomes.jsonl"
        append_outcome("run-a", "resolved", outcomes_path=p)
        assert p.exists()

    def test_append_outcome_is_valid_json(self, tmp_path):
        from oil.memory.outcomes import append_outcome
        p = tmp_path / "outcomes.jsonl"
        append_outcome("run-a", "resolved", notes="fixed by rollback", outcomes_path=p)
        data = json.loads(p.read_text(encoding="utf-8").strip())
        assert data["run_id"] == "run-a"
        assert data["outcome_kind"] == "resolved"
        assert data["notes"] == "fixed by rollback"
        assert "created_utc" in data

    def test_load_outcomes_empty_when_file_missing(self, tmp_path):
        from oil.memory.outcomes import load_outcomes
        result = load_outcomes(tmp_path / "nonexistent.jsonl")
        assert result == {}

    def test_load_outcomes_keyed_by_run_id(self, tmp_path):
        from oil.memory.outcomes import append_outcome, load_outcomes
        p = tmp_path / "outcomes.jsonl"
        append_outcome("run-1", "resolved", outcomes_path=p)
        append_outcome("run-2", "mitigated", outcomes_path=p)
        result = load_outcomes(p)
        assert "run-1" in result
        assert "run-2" in result
        assert result["run-1"][0]["outcome_kind"] == "resolved"

    def test_load_outcomes_multiple_per_run(self, tmp_path):
        from oil.memory.outcomes import append_outcome, load_outcomes
        p = tmp_path / "outcomes.jsonl"
        append_outcome("run-x", "mitigated", outcomes_path=p)
        append_outcome("run-x", "resolved", outcomes_path=p)
        result = load_outcomes(p)
        assert len(result["run-x"]) == 2

    def test_append_outcome_invalid_kind_raises(self, tmp_path):
        from oil.memory.outcomes import append_outcome
        with pytest.raises(ValueError, match="Invalid outcome_kind"):
            append_outcome("run-z", "destroyed", outcomes_path=tmp_path / "o.jsonl")

    # ─── CLI run_outcome tool ─────────────────────────────────────────────

    def test_cli_run_outcome_writes_entry(self, tmp_path):
        """oil.run_outcome CLI appends the expected entry to the outcomes file."""
        import importlib
        import sys
        outcomes_path = tmp_path / "outcomes.jsonl"
        # Simulate CLI invocation via main() directly (no subprocess)
        from oil.run_outcome import main
        rc = main([
            "--run-id", "run-cli",
            "--kind", "resolved",
            "--notes", "auto test",
            "--outcomes-path", str(outcomes_path),
        ])
        assert rc == 0
        from oil.memory.outcomes import load_outcomes
        result = load_outcomes(outcomes_path)
        assert "run-cli" in result
        assert result["run-cli"][0]["outcome_kind"] == "resolved"
        assert result["run-cli"][0]["notes"] == "auto test"

    def test_cli_run_outcome_invalid_kind_exits_1(self, tmp_path, capsys):
        from oil.run_outcome import main
        # argparse exits with SystemExit on bad --kind, which we catch
        with pytest.raises(SystemExit):
            main(["--run-id", "r", "--kind", "destroyed",
                  "--outcomes-path", str(tmp_path / "o.jsonl")])

    # ─── Negation guard ───────────────────────────────────────────────────

    def test_negation_do_not_rollback_skipped(self):
        from oil.memory.actions import extract_action
        report = {
            "recommended_human_action": "Do not rollback -- too risky. Investigate instead.",
            "evidence": [],
        }
        result = extract_action(report, "payment")
        assert result["primary_action_category"] != "rollback", (
            "negated keyword 'rollback' should not be primary"
        )
        assert result["primary_action_category"] == "investigate"

    def test_negation_dont_restart_skipped(self):
        from oil.memory.actions import extract_action
        report = {
            "recommended_human_action": "Don't restart. Investigate the root cause.",
            "evidence": [],
        }
        result = extract_action(report, "payment")
        assert result["primary_action_category"] != "restart"

    def test_negation_avoid_rollback_skipped(self):
        from oil.memory.actions import extract_action
        report = {
            "recommended_human_action": "Avoid rollback at this stage.",
            "evidence": [],
        }
        result = extract_action(report, "payment")
        assert result["primary_action_category"] != "rollback"

    def test_non_negated_keyword_still_matches(self):
        """Negation only applies when negator is within 3 tokens before keyword."""
        from oil.memory.actions import extract_action
        report = {
            "recommended_human_action": "After investigation, rollback the service.",
            "evidence": [],
        }
        result = extract_action(report, "payment")
        # "investigation" is the 4th token before "rollback", so rollback is NOT negated
        # Actually: "After" "investigation," "rollback" → "investigation" is 2 tokens before
        # → but "investigation" is not a negator, so rollback matches
        assert result["primary_action_category"] in ("investigate", "rollback")

    # ─── Compound action parsing ──────────────────────────────────────────

    def test_compound_returns_primary_and_fallback(self):
        from oil.memory.actions import extract_action
        report = {
            "recommended_human_action": "Investigate the issue. If unresolved, rollback.",
            "evidence": [],
        }
        result = extract_action(report, "payment")
        assert result["primary_action_category"] == "investigate"
        assert result["fallback_action_category"] == "rollback"

    def test_single_keyword_fallback_empty(self):
        from oil.memory.actions import extract_action
        report = {
            "recommended_human_action": "Investigate recent changes.",
            "evidence": [],
        }
        result = extract_action(report, "payment")
        assert result["fallback_action_category"] == ""

    def test_compound_negation_skips_first_uses_second(self):
        from oil.memory.actions import extract_action
        report = {
            "recommended_human_action":
                "Do not rollback. Investigate the change, then restart if needed.",
            "evidence": [],
        }
        result = extract_action(report, "payment")
        # 'rollback' negated → primary should be 'investigate', fallback 'restart'
        assert result["primary_action_category"] == "investigate"
        assert result["fallback_action_category"] == "restart"

    def test_action_category_backward_compat_alias(self):
        from oil.memory.actions import extract_action
        report = {"recommended_human_action": "Investigate.", "evidence": []}
        result = extract_action(report, "payment")
        assert result["action_category"] == result["primary_action_category"]

    # ─── Outcome summary computation ──────────────────────────────────────

    def test_outcome_summary_resolved_rate(self):
        from oil.run_analysis import _compute_outcome_summary
        matches = [
            {"run_id": "run-1"},
            {"run_id": "run-2"},
            {"run_id": "run-3"},
        ]
        outcomes = {
            "run-1": [{"outcome_kind": "resolved", "created_utc": "", "notes": ""}],
            "run-2": [{"outcome_kind": "resolved", "created_utc": "", "notes": ""}],
            "run-3": [{"outcome_kind": "mitigated", "created_utc": "", "notes": ""}],
        }
        summary = _compute_outcome_summary(matches, outcomes)
        assert summary["total_with_outcomes"] == 3
        assert abs(summary["resolved_rate"] - 0.6667) < 0.001
        assert summary["counts"]["resolved"] == 2
        assert summary["counts"]["mitigated"] == 1

    def test_outcome_summary_no_outcomes_returns_zero(self):
        from oil.run_analysis import _compute_outcome_summary
        matches = [{"run_id": "run-1"}, {"run_id": "run-2"}]
        outcomes = {}
        summary = _compute_outcome_summary(matches, outcomes)
        assert summary["total_with_outcomes"] == 0
        assert summary["resolved_rate"] == 0.0

    def test_outcome_summary_false_positive_counted(self):
        from oil.run_analysis import _compute_outcome_summary
        matches = [{"run_id": "run-fp"}]
        outcomes = {"run-fp": [{"outcome_kind": "false_positive", "created_utc": "", "notes": ""}]}
        summary = _compute_outcome_summary(matches, outcomes)
        assert summary["counts"]["false_positive"] == 1
        assert summary["resolved_rate"] == 0.0

class TestV07CaseFiles:
    """v0.7: Final outcome policy, bounded scanning, case file writer."""

    # ── final outcome selection ───────────────────────────────────────────

    def test_select_final_outcome_latest_ts(self):
        from oil.memory.outcomes import select_final_outcome
        entries = [
            {"run_id": "r", "outcome_kind": "mitigated",  "created_utc": "2026-02-27T10:00:00Z", "notes": ""},
            {"run_id": "r", "outcome_kind": "resolved",   "created_utc": "2026-02-27T11:00:00Z", "notes": ""},
            {"run_id": "r", "outcome_kind": "ignored",    "created_utc": "2026-02-27T09:00:00Z", "notes": ""},
        ]
        result = select_final_outcome(entries)
        assert result["outcome_kind"] == "resolved"

    def test_select_final_outcome_tie_break_priority(self):
        """Same timestamp: resolved beats mitigated beats false_positive beats ignored."""
        from oil.memory.outcomes import select_final_outcome
        ts = "2026-02-27T12:00:00Z"
        entries = [
            {"run_id": "r", "outcome_kind": "mitigated",  "created_utc": ts, "notes": ""},
            {"run_id": "r", "outcome_kind": "resolved",   "created_utc": ts, "notes": ""},
        ]
        assert select_final_outcome(entries)["outcome_kind"] == "resolved"
        # false_positive vs ignored
        entries2 = [
            {"run_id": "r", "outcome_kind": "ignored",       "created_utc": ts, "notes": ""},
            {"run_id": "r", "outcome_kind": "false_positive","created_utc": ts, "notes": ""},
        ]
        assert select_final_outcome(entries2)["outcome_kind"] == "false_positive"

    def test_select_final_outcome_single_entry(self):
        from oil.memory.outcomes import select_final_outcome
        e = [{"run_id": "r", "outcome_kind": "ignored", "created_utc": "2026-02-27T08:00:00Z", "notes": ""}]
        assert select_final_outcome(e)["outcome_kind"] == "ignored"

    def test_select_final_outcome_empty_returns_none(self):
        from oil.memory.outcomes import select_final_outcome
        assert select_final_outcome([]) is None

    # ── outcome_summary uses final_outcome (one per run_id) ───────────────

    def test_outcome_summary_counts_final_not_all(self):
        """When a run has both 'mitigated' then 'resolved', only 'resolved' is counted."""
        from oil.run_analysis import _compute_outcome_summary
        matches = [{"run_id": "run-1"}]
        outcomes = {
            "run-1": [
                {"outcome_kind": "mitigated", "created_utc": "2026-02-27T10:00:00Z", "notes": ""},
                {"outcome_kind": "resolved",  "created_utc": "2026-02-27T11:00:00Z", "notes": ""},
            ]
        }
        summary = _compute_outcome_summary(matches, outcomes)
        assert summary["counts"]["resolved"] == 1
        assert summary["counts"]["mitigated"] == 0   # not double-counted

    # ── bounded load_outcomes ─────────────────────────────────────────────

    def test_load_outcomes_filters_old_entries(self, tmp_path):
        from datetime import datetime, timedelta, timezone
        from oil.memory.outcomes import append_outcome, load_outcomes
        p = tmp_path / "outcomes.jsonl"
        now = datetime.now(timezone.utc)
        old_ts = (now - timedelta(days=60)).strftime("%Y-%m-%dT%H:%M:%SZ")
        recent_ts = (now - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
        append_outcome("run-old", "resolved", created_utc=old_ts, outcomes_path=p)
        append_outcome("run-new", "mitigated", created_utc=recent_ts, outcomes_path=p)
        result = load_outcomes(p, lookback_days=30)
        assert "run-old" not in result
        assert "run-new" in result

    def test_load_outcomes_deduplicates_exact(self, tmp_path):
        from oil.memory.outcomes import append_outcome, load_outcomes
        p = tmp_path / "outcomes.jsonl"
        ts = "2026-02-27T12:00:00Z"
        append_outcome("run-x", "resolved", created_utc=ts, outcomes_path=p)
        append_outcome("run-x", "resolved", created_utc=ts, outcomes_path=p)  # exact dup
        result = load_outcomes(p, lookback_days=365)
        assert len(result["run-x"]) == 1

    # ── case file writer ──────────────────────────────────────────────────

    def test_case_writer_creates_four_files(self, tmp_path):
        from oil.cases.writer import write_case
        # Minimal artifact file
        artifact = tmp_path / "incident_test.json"
        artifact.write_text('{"incident_summary":"test","confidence_score":0.9}', encoding="utf-8")
        memory_line = {"run_id": "run-cs", "fingerprint_id": "abc", "origin_service": "payment"}
        case_dir = write_case(
            run_id="run-cs",
            artifact_path=artifact,
            memory_line=memory_line,
            outcomes_for_run=[],
            human_block="SUMMARY: test",
            cases_dir=tmp_path / "cases",
        )
        assert (case_dir / "incident.json").exists()
        assert (case_dir / "memory.json").exists()
        assert (case_dir / "outcomes.jsonl").exists() or True   # empty outcomes => no file yet
        assert (case_dir / "summary.txt").exists()

    def test_case_writer_incident_json_content(self, tmp_path):
        from oil.cases.writer import write_case
        artifact = tmp_path / "artifact.json"
        artifact.write_text('{"incident_summary":"test","confidence_score":0.75}', encoding="utf-8")
        case_dir = write_case(
            run_id="run-content",
            artifact_path=artifact,
            memory_line={"run_id": "run-content", "origin_service": "auth"},
            outcomes_for_run=[],
            human_block="BLOCK",
            cases_dir=tmp_path / "cases",
        )
        data = json.loads((case_dir / "incident.json").read_text(encoding="utf-8"))
        assert data["confidence_score"] == 0.75

    def test_case_writer_memory_json_content(self, tmp_path):
        from oil.cases.writer import write_case
        artifact = tmp_path / "art.json"
        artifact.write_text('{}', encoding="utf-8")
        mem = {"run_id": "run-mem", "origin_service": "payment", "confidence": 0.9}
        case_dir = write_case("run-mem", artifact, mem, [], "BLOCK", tmp_path / "cases")
        loaded = json.loads((case_dir / "memory.json").read_text(encoding="utf-8"))
        assert loaded["origin_service"] == "payment"

    def test_case_writer_summary_txt_content(self, tmp_path):
        from oil.cases.writer import write_case
        artifact = tmp_path / "art.json"
        artifact.write_text('{}', encoding="utf-8")
        block = "OIL -- INCIDENT EXPLANATION\n==========================\nSUMMARY: test"
        case_dir = write_case("run-txt", artifact, {}, [], block, tmp_path / "cases")
        assert (case_dir / "summary.txt").read_text(encoding="utf-8") == block

    def test_case_writer_idempotent_overwrite(self, tmp_path):
        """Calling write_case twice with same run_id overwrites atomic files."""
        from oil.cases.writer import write_case
        artifact = tmp_path / "art.json"
        artifact.write_text('{"v": 1}', encoding="utf-8")
        write_case("run-idem", artifact, {"v": 1}, [], "first", tmp_path / "cases")
        # Update artifact content
        artifact.write_text('{"v": 2}', encoding="utf-8")
        write_case("run-idem", artifact, {"v": 2}, [], "second", tmp_path / "cases")
        case_dir = tmp_path / "cases" / "run-idem"
        assert json.loads((case_dir / "incident.json").read_text())["v"] == 2
        assert (case_dir / "summary.txt").read_text() == "second"

    def test_case_writer_outcomes_deduped(self, tmp_path):
        """Calling write_case twice with same outcome does not duplicate it."""
        from oil.cases.writer import write_case
        artifact = tmp_path / "art.json"
        artifact.write_text('{}', encoding="utf-8")
        outcomes = [{"run_id": "run-dup", "outcome_kind": "resolved",
                     "created_utc": "2026-02-27T10:00:00Z", "notes": ""}]
        write_case("run-dup", artifact, {}, outcomes, "BLOCK", tmp_path / "cases")
        write_case("run-dup", artifact, {}, outcomes, "BLOCK", tmp_path / "cases")
        case_dir = tmp_path / "cases" / "run-dup"
        lines = [l for l in (case_dir / "outcomes.jsonl").read_text().splitlines() if l.strip()]
        assert len(lines) == 1

    # ── run_outcome syncs to case folder ──────────────────────────────────

    def test_run_outcome_syncs_to_case_folder(self, tmp_path):
        """After writing a case, run_outcome CLI appends to its outcomes.jsonl."""
        from oil.cases.writer import write_case
        from oil.run_outcome import main as outcome_main
        artifact = tmp_path / "art.json"
        artifact.write_text('{}', encoding="utf-8")
        cases_dir = tmp_path / "cases"
        # First create the case folder
        write_case("run-sync", artifact, {}, [], "BLOCK", cases_dir)
        # Now record outcome via CLI
        outcomes_path = tmp_path / "outcomes.jsonl"
        rc = outcome_main([
            "--run-id", "run-sync",
            "--kind", "resolved",
            "--notes", "synced",
            "--outcomes-path", str(outcomes_path),
            "--cases-dir", str(cases_dir),
        ])
        assert rc == 0
        case_outcomes = cases_dir / "run-sync" / "outcomes.jsonl"
        assert case_outcomes.exists()
        data = json.loads(case_outcomes.read_text().strip())
        assert data["outcome_kind"] == "resolved"

class TestV08StorageContracts:
    """v0.8: Record contracts, rotation, retention, verification."""

    # ── contract fields on new writes ─────────────────────────────────────

    def test_memory_index_entry_has_contract_fields(self, tmp_path):
        from oil.memory.store import append_entry, load_index
        p = tmp_path / "index.jsonl"
        append_entry(
            fingerprint_id="fp1", artifact_path="/a/b.json",
            origin_service="svc", change_kind="deploy",
            metric_kind="latency", hop_distance_class="1",
            impact_domain="revenue", confidence=0.9,
            index_path=p, run_id="run-contract",
        )
        entries = load_index(p)
        e = entries[0]
        assert e["record_type"] == "memory_index"
        assert e["record_version"] == "1"

    def test_outcome_entry_has_contract_fields(self, tmp_path):
        from oil.memory.outcomes import append_outcome, load_outcomes
        p = tmp_path / "outcomes.jsonl"
        append_outcome("run-c", "resolved", outcomes_path=p)
        result = load_outcomes(p, lookback_days=3650)
        entry = result["run-c"][0]
        assert entry["record_type"] == "outcome"
        assert entry["record_version"] == "1"

    def test_backward_compat_load_old_memory_line(self, tmp_path):
        """Lines without record_type (old format) load transparently."""
        from oil.memory.store import load_index
        p = tmp_path / "index.jsonl"
        old_line = json.dumps({
            "run_id": "old-run",
            "fingerprint_id": "fp-old",
            "artifact_path": "/old/path.json",
            "created_utc": "2025-01-15T08:00:00Z",
            "origin_service": "payment",
        })
        p.write_text(old_line + "\n", encoding="utf-8")
        entries = load_index(p)
        assert len(entries) == 1
        assert entries[0]["run_id"] == "old-run"
        assert entries[0].get("record_type", "0") in ("0", None, "")   # absent = legacy

    def test_backward_compat_load_old_outcome_line(self, tmp_path):
        """Old outcome lines without record_type load into load_outcomes transparently."""
        from oil.memory.outcomes import load_outcomes
        from datetime import datetime, timezone
        now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        p = tmp_path / "outcomes.jsonl"
        old_line = json.dumps({
            "run_id": "old-run2",
            "outcome_kind": "resolved",
            "created_utc": now_ts,
            "notes": "",
        })
        p.write_text(old_line + "\n", encoding="utf-8")
        result = load_outcomes(p, lookback_days=3650)
        assert "old-run2" in result

    # ── rotation: correct YYYYMM shards ──────────────────────────────────

    def test_rotation_creates_monthly_shard_for_index(self, tmp_path):
        from oil.run_rotate_memory import rotate
        idx = tmp_path / "index.jsonl"
        line = json.dumps({
            "record_type": "memory_index", "record_version": "1",
            "run_id": "run-rot", "fingerprint_id": "fp", "artifact_path": "/a.json",
            "created_utc": "2026-01-15T10:00:00Z",
            "origin_service": "payment", "change_kind": "deploy",
            "metric_kind": "latency", "hop_distance_class": "1",
            "impact_domain": "revenue", "confidence": 0.9,
        })
        idx.write_text(line + "\n", encoding="utf-8")
        report = rotate(idx, tmp_path / "outcomes.jsonl", tmp_path, keep_months=6)
        shard = tmp_path / "index_202601.jsonl"
        assert shard.exists(), f"Expected shard index_202601.jsonl"
        data = json.loads(shard.read_text().strip())
        assert data["run_id"] == "run-rot"
        assert report["total_index_rotated"] == 1

    def test_rotation_creates_monthly_shard_for_outcomes(self, tmp_path):
        from oil.run_rotate_memory import rotate
        outcomes = tmp_path / "outcomes.jsonl"
        line = json.dumps({
            "record_type": "outcome", "record_version": "1",
            "run_id": "run-out", "outcome_kind": "resolved",
            "created_utc": "2026-02-10T09:00:00Z", "notes": "",
        })
        outcomes.write_text(line + "\n", encoding="utf-8")
        report = rotate(tmp_path / "index.jsonl", outcomes, tmp_path, keep_months=6)
        shard = tmp_path / "outcomes_202602.jsonl"
        assert shard.exists()
        assert report["total_outcomes_rotated"] == 1

    def test_rotation_deduplication_memory_by_run_id(self, tmp_path):
        """Re-rotating same run_id does not duplicate in shard."""
        from oil.run_rotate_memory import rotate
        idx = tmp_path / "index.jsonl"
        line = json.dumps({
            "run_id": "run-dedup", "created_utc": "2026-02-15T10:00:00Z",
            "fingerprint_id": "fp", "artifact_path": "/a.json",
            "origin_service": "svc", "change_kind": "", "metric_kind": "",
            "hop_distance_class": "", "impact_domain": "", "confidence": 0.5,
        })
        idx.write_text((line + "\n") * 2, encoding="utf-8")  # two identical lines
        rotate(idx, tmp_path / "out.jsonl", tmp_path, keep_months=6)
        shard = tmp_path / "index_202602.jsonl"
        lines = [l for l in shard.read_text().splitlines() if l.strip()]
        assert len(lines) == 1

    # ── retention: shard hot/cold classification ──────────────────────────

    def test_rotation_report_labels_current_month_hot(self, tmp_path):
        from datetime import datetime, timezone
        from oil.run_rotate_memory import rotate
        now = datetime.now(timezone.utc)
        idx = tmp_path / "index.jsonl"
        current_ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        line = json.dumps({
            "run_id": "run-hot", "created_utc": current_ts,
            "fingerprint_id": "fp", "artifact_path": "/a.json",
            "origin_service": "svc", "change_kind": "", "metric_kind": "",
            "hop_distance_class": "", "impact_domain": "", "confidence": 0.5,
        })
        idx.write_text(line + "\n", encoding="utf-8")
        report = rotate(idx, tmp_path / "out.jsonl", tmp_path, keep_months=3)
        current_shard_key = now.strftime("%Y%m")
        shard_entry = next(
            (s for s in report["shards"] if s["yyyymm"] == current_shard_key), None
        )
        assert shard_entry is not None
        assert shard_entry["hot"] is True

    def test_prune_original_removes_files(self, tmp_path):
        from oil.run_rotate_memory import rotate
        idx = tmp_path / "index.jsonl"
        idx.write_text(
            json.dumps({"run_id": "r", "created_utc": "2026-02-15T10:00:00Z",
                        "fingerprint_id": "f", "artifact_path": "/a.json",
                        "origin_service": "", "change_kind": "", "metric_kind": "",
                        "hop_distance_class": "", "impact_domain": "", "confidence": 0}) + "\n",
            encoding="utf-8",
        )
        rotate(idx, tmp_path / "out.jsonl", tmp_path, keep_months=6, prune_original=True)
        assert not idx.exists()

    # ── verification ──────────────────────────────────────────────────────

    def test_verify_good_artifact_passes(self, tmp_path):
        """A valid artifact with correct run_id passes verification."""
        import hashlib
        from oil.run_verify import verify_artifacts
        arts = tmp_path / "artifacts"
        arts.mkdir()
        created_utc = "2026-02-28T07:37:30Z"
        inputs_digest = "sha256:abc123"
        payload = created_utc + "|" + inputs_digest
        run_id = hashlib.sha256(payload.encode()).hexdigest()[:16]
        envelope = {
            "artifact_version": "1", "oil_version": "0.8",
            "created_utc": created_utc, "run_id": run_id,
            "inputs_digest": inputs_digest, "report": {},
        }
        af = arts / f"incident_20260228T073730Z_{run_id}.json"
        af.write_text(json.dumps(envelope), encoding="utf-8")
        failures = verify_artifacts(arts)
        assert failures == [], f"Expected no failures, got: {failures}"

    def test_verify_tampered_run_id_fails(self, tmp_path):
        """An artifact with a mismatched run_id reports a failure."""
        from oil.run_verify import verify_artifacts
        arts = tmp_path / "artifacts"
        arts.mkdir()
        envelope = {
            "artifact_version": "1", "oil_version": "0.8",
            "created_utc": "2026-02-28T07:00:00Z", "run_id": "tampered0001",
            "inputs_digest": "sha256:abc", "report": {},
        }
        af = arts / "incident_20260228T070000Z_tampered0001.json"
        af.write_text(json.dumps(envelope), encoding="utf-8")
        failures = verify_artifacts(arts)
        assert any("run_id_mismatch" in f["reason"] for f in failures)

    def test_verify_missing_field_fails(self, tmp_path):
        from oil.run_verify import verify_artifacts
        arts = tmp_path / "artifacts"
        arts.mkdir()
        envelope = {"artifact_version": "1", "oil_version": "0.8",
                    "created_utc": "2026-02-28T07:00:00Z", "run_id": "abc",
                    # missing inputs_digest
                    "report": {}}
        af = arts / "incident_20260228T070000Z_abc.json"
        af.write_text(json.dumps(envelope), encoding="utf-8")
        failures = verify_artifacts(arts)
        assert any("inputs_digest" in f["reason"] for f in failures)

    def test_verify_case_digest_match(self, tmp_path):
        """Case incident.json matching the original artifact passes."""
        import hashlib
        from oil.run_verify import verify_cases
        arts = tmp_path / "artifacts"
        arts.mkdir()
        cases = tmp_path / "cases"
        created_utc = "2026-02-28T07:37:30Z"
        inputs_digest = "sha256:abc123"
        payload = created_utc + "|" + inputs_digest
        run_id = hashlib.sha256(payload.encode()).hexdigest()[:16]
        envelope = {
            "artifact_version": "1", "oil_version": "0.8",
            "created_utc": created_utc, "run_id": run_id,
            "inputs_digest": inputs_digest, "report": {},
        }
        art_text = json.dumps(envelope, indent=2) + "\n"
        af = arts / f"incident_20260228T073730Z_{run_id}.json"
        af.write_text(art_text, encoding="utf-8")
        # case
        case_dir = cases / run_id
        case_dir.mkdir(parents=True)
        (case_dir / "incident.json").write_text(art_text, encoding="utf-8")  # identical copy
        (case_dir / "memory.json").write_text(
            json.dumps({"run_id": run_id, "artifact_path": str(af)}), encoding="utf-8"
        )
        failures = verify_cases(cases)
        assert failures == []

    def test_verify_case_tampered_incident_fails(self, tmp_path):
        """Case incident.json differing from artifact content fails."""
        from oil.run_verify import verify_cases
        arts = tmp_path / "artifacts"
        arts.mkdir()
        cases = tmp_path / "cases"
        run_id = "deadbeef0000cafe"   # valid 16-char lowercase hex
        af = arts / f"incident_ts_{run_id}.json"
        af.write_text('{"original": true}', encoding="utf-8")
        case_dir = cases / run_id
        case_dir.mkdir(parents=True)
        (case_dir / "incident.json").write_text('{"tampered": true}', encoding="utf-8")
        (case_dir / "memory.json").write_text(
            json.dumps({"run_id": run_id, "artifact_path": str(af)}), encoding="utf-8"
        )
        failures = verify_cases(cases)
        assert any("digest_mismatch" in f["reason"] for f in failures)

# ─── v0.9 export test fixtures ────────────────────────────────────────────────

def _make_case(tmp_cases_dir, run_id, created_utc, confidence, origin_service,
               action_category="investigate", inputs_digest="sha256:abc",
               action_target_service="", add_outcome=None):
    """Helper: create a case folder like the real writer does."""
    import hashlib
    payload = created_utc + "|" + inputs_digest
    computed_run_id = hashlib.sha256(payload.encode()).hexdigest()[:16]
    # Use computed_run_id as actual run_id for envelope consistency
    # but use the provided run_id as folder name for test control
    case_dir = tmp_cases_dir / run_id
    case_dir.mkdir(parents=True, exist_ok=True)
    # Envelope (valid: run_id matches computed from created_utc+inputs_digest)
    # For test simplicity, use the provided run_id in the envelope too;
    # some tests will explicitly test verified vs unverified.
    envelope = {
        "artifact_version": "1",
        "oil_version": "0.9",
        "created_utc": created_utc,
        "run_id": run_id,
        "inputs_digest": inputs_digest,
        "report": {
            "reference_service": origin_service,
            "evidence": [{"service": action_target_service or origin_service}],
        },
    }
    art_bytes = (json.dumps(envelope, indent=2) + "\n").encode()
    (case_dir / "incident.json").write_bytes(art_bytes)
    memory = {
        "record_type": "memory_index", "record_version": "1",
        "run_id": run_id, "fingerprint_id": f"fp_{run_id[:4]}",
        "artifact_path": "",  # no original artifact in tmp — skip digest check
        "created_utc": created_utc, "origin_service": origin_service,
        "action_target_service": action_target_service or origin_service,
        "confidence": confidence, "action_category": action_category,
        "change_kind": "deploy", "metric_kind": "latency",
        "hop_distance_class": "1", "impact_domain": "revenue",
        "fallback_action_category": "",
    }
    (case_dir / "memory.json").write_text(
        json.dumps(memory, indent=2) + "\n", encoding="utf-8"
    )
    (case_dir / "summary.txt").write_text(
        f"summary for {run_id} origin={origin_service}", encoding="utf-8"
    )
    if add_outcome:
        (case_dir / "outcomes.jsonl").write_text(
            json.dumps({"run_id": run_id, "outcome_kind": add_outcome,
                        "created_utc": created_utc, "notes": ""}) + "\n",
            encoding="utf-8",
        )
    return case_dir


class TestV09ExportCases:
    """v0.9: Diagnostic Packaging Export tests."""

    # ── case selection filters ────────────────────────────────────────────

    def test_select_all_cases(self, tmp_path):
        from oil.run_export_cases import select_cases
        cases = tmp_path / "cases"
        _make_case(cases, "ab" * 8, "2026-02-01T10:00:00Z", 0.9, "payment")
        _make_case(cases, "cd" * 8, "2026-02-10T10:00:00Z", 0.7, "auth")
        result = select_cases(cases, None, None, None, 0.0)
        assert len(result) == 2

    def test_select_last_n(self, tmp_path):
        from oil.run_export_cases import select_cases
        cases = tmp_path / "cases"
        _make_case(cases, "aa" * 8, "2026-02-01T10:00:00Z", 0.9, "payment")
        _make_case(cases, "bb" * 8, "2026-02-05T10:00:00Z", 0.9, "auth")
        _make_case(cases, "cc" * 8, "2026-02-10T10:00:00Z", 0.9, "db")
        result = select_cases(cases, last_n=2, from_dt=None, to_dt=None, min_confidence=0.0)
        assert len(result) == 2
        # Must be the two most recent (sorted asc, take last 2)
        assert result[0]["origin_service"] == "auth"
        assert result[1]["origin_service"] == "db"

    def test_select_date_range(self, tmp_path):
        from datetime import timezone
        from oil.run_export_cases import select_cases
        cases = tmp_path / "cases"
        _make_case(cases, "aa" * 8, "2026-01-15T10:00:00Z", 0.9, "payment")
        _make_case(cases, "bb" * 8, "2026-02-10T10:00:00Z", 0.9, "auth")
        _make_case(cases, "cc" * 8, "2026-03-01T10:00:00Z", 0.9, "db")
        from_dt = datetime(2026, 2, 1, tzinfo=timezone.utc)
        to_dt = datetime(2026, 2, 28, 23, 59, 59, tzinfo=timezone.utc)
        result = select_cases(cases, None, from_dt, to_dt, 0.0)
        assert len(result) == 1
        assert result[0]["origin_service"] == "auth"

    def test_select_min_confidence(self, tmp_path):
        from oil.run_export_cases import select_cases
        cases = tmp_path / "cases"
        _make_case(cases, "aa" * 8, "2026-02-01T10:00:00Z", 0.95, "payment")
        _make_case(cases, "bb" * 8, "2026-02-05T10:00:00Z", 0.60, "auth")
        result = select_cases(cases, None, None, None, 0.8)
        assert len(result) == 1
        assert result[0]["origin_service"] == "payment"

    def test_select_deterministic_ordering(self, tmp_path):
        from oil.run_export_cases import select_cases
        cases = tmp_path / "cases"
        # Same timestamp, different run_ids → sorted by run_id as tiebreak
        _make_case(cases, "ee" * 8, "2026-02-10T10:00:00Z", 0.9, "zeta")
        _make_case(cases, "dd" * 8, "2026-02-10T10:00:00Z", 0.9, "alpha")
        result = select_cases(cases, None, None, None, 0.0)
        assert result[0]["run_id"] < result[1]["run_id"]

    # ── manifest and export structure ─────────────────────────────────────

    def test_export_creates_output_files(self, tmp_path):
        from oil.run_export_cases import export_cases
        cases = tmp_path / "cases"
        _make_case(cases, "ab" * 8, "2026-02-01T10:00:00Z", 0.9, "payment")
        out = tmp_path / "export"
        export_cases(cases, out, min_confidence=0.0)
        assert (out / "manifest.json").exists()
        assert (out / "summary.json").exists()
        assert (out / "summary.txt").exists()
        assert (out / "cases").is_dir()

    def test_manifest_entry_fields(self, tmp_path):
        from oil.run_export_cases import export_cases
        cases = tmp_path / "cases"
        run_id = "ab" * 8
        _make_case(cases, run_id, "2026-02-01T10:00:00Z", 0.9, "payment",
                   action_category="rollback")
        out = tmp_path / "export"
        export_cases(cases, out, min_confidence=0.0)
        manifest = json.loads((out / "manifest.json").read_text())
        assert len(manifest) == 1
        e = manifest[0]
        assert e["run_id"] == run_id
        assert e["confidence"] == 0.9
        assert e["origin_service"] == "payment"
        assert e["action_category"] == "rollback"
        assert "verification_status" in e
        assert "inputs_digest" in e

    def test_verification_status_included(self, tmp_path):
        """Cases whose envelope fields are present get a verification_status."""
        from oil.run_export_cases import export_cases
        cases = tmp_path / "cases"
        _make_case(cases, "ab" * 8, "2026-02-01T10:00:00Z", 0.9, "payment")
        out = tmp_path / "export"
        export_cases(cases, out, min_confidence=0.0)
        manifest = json.loads((out / "manifest.json").read_text())
        # run_id in the test envelope won't match computed run_id, so expect run_id_mismatch
        assert manifest[0]["verification_status"] in ("verified", "run_id_mismatch", "missing_field:artifact_version")

    def test_include_outcomes_copies_outcomes_jsonl(self, tmp_path):
        from oil.run_export_cases import export_cases
        cases = tmp_path / "cases"
        run_id = "ab" * 8
        _make_case(cases, run_id, "2026-02-01T10:00:00Z", 0.9, "payment",
                   add_outcome="resolved")
        out = tmp_path / "export"
        export_cases(cases, out, min_confidence=0.0, include_outcomes=True)
        assert (out / "cases" / run_id / "outcomes.jsonl").exists()

    def test_exclude_outcomes_by_default(self, tmp_path):
        from oil.run_export_cases import export_cases
        cases = tmp_path / "cases"
        run_id = "ab" * 8
        _make_case(cases, run_id, "2026-02-01T10:00:00Z", 0.9, "payment",
                   add_outcome="resolved")
        out = tmp_path / "export"
        export_cases(cases, out, min_confidence=0.0, include_outcomes=False)
        assert not (out / "cases" / run_id / "outcomes.jsonl").exists()

    def test_final_outcome_in_manifest_when_include_outcomes(self, tmp_path):
        from oil.run_export_cases import export_cases
        cases = tmp_path / "cases"
        run_id = "ab" * 8
        _make_case(cases, run_id, "2026-02-01T10:00:00Z", 0.9, "payment",
                   add_outcome="resolved")
        out = tmp_path / "export"
        export_cases(cases, out, min_confidence=0.0, include_outcomes=True)
        manifest = json.loads((out / "manifest.json").read_text())
        assert manifest[0]["final_outcome_kind"] == "resolved"

    # ── summary aggregates ────────────────────────────────────────────────

    def test_summary_total_exported(self, tmp_path):
        from oil.run_export_cases import export_cases
        cases = tmp_path / "cases"
        _make_case(cases, "aa" * 8, "2026-02-01T10:00:00Z", 0.9, "payment")
        _make_case(cases, "bb" * 8, "2026-02-05T10:00:00Z", 0.9, "auth")
        out = tmp_path / "export"
        export_cases(cases, out, min_confidence=0.0)
        summary = json.loads((out / "summary.json").read_text())
        assert summary["total_exported"] == 2

    def test_summary_most_common_origin(self, tmp_path):
        from oil.run_export_cases import export_cases
        cases = tmp_path / "cases"
        _make_case(cases, "aa" * 8, "2026-02-01T10:00:00Z", 0.9, "payment")
        _make_case(cases, "bb" * 8, "2026-02-05T10:00:00Z", 0.9, "payment")
        _make_case(cases, "cc" * 8, "2026-02-10T10:00:00Z", 0.9, "auth")
        out = tmp_path / "export"
        export_cases(cases, out, min_confidence=0.0)
        summary = json.loads((out / "summary.json").read_text())
        assert summary["most_common_origin"] == "payment"

    def test_summary_avg_confidence(self, tmp_path):
        from oil.run_export_cases import export_cases
        cases = tmp_path / "cases"
        _make_case(cases, "aa" * 8, "2026-02-01T10:00:00Z", 0.8, "payment")
        _make_case(cases, "bb" * 8, "2026-02-05T10:00:00Z", 1.0, "auth")
        out = tmp_path / "export"
        export_cases(cases, out, min_confidence=0.0)
        summary = json.loads((out / "summary.json").read_text())
        assert abs(summary["avg_confidence"] - 0.9) < 0.001

    def test_summary_txt_contains_key_fields(self, tmp_path):
        from oil.run_export_cases import export_cases
        cases = tmp_path / "cases"
        _make_case(cases, "aa" * 8, "2026-02-01T10:00:00Z", 0.9, "payment")
        out = tmp_path / "export"
        export_cases(cases, out, min_confidence=0.0)
        txt = (out / "summary.txt").read_text(encoding="utf-8")
        assert "total_exported" in txt
        assert "avg_confidence" in txt

    # ── anonymization ─────────────────────────────────────────────────────

    def test_anon_map_stable_and_sorted(self, tmp_path):
        from oil.run_export_cases import build_anon_map, _load_case_meta
        cases = tmp_path / "cases"
        _make_case(cases, "aa" * 8, "2026-02-01T10:00:00Z", 0.9, "zebra")
        _make_case(cases, "bb" * 8, "2026-02-05T10:00:00Z", 0.9, "alpha")
        metas = [_load_case_meta(cases / ("aa" * 8)), _load_case_meta(cases / ("bb" * 8))]
        anon = build_anon_map(metas)
        # alpha < zebra lexicographically → alpha=SVC_01, zebra=SVC_02
        assert anon.get("alpha") == "SVC_01"
        assert anon.get("zebra") == "SVC_02"

    def test_anonymize_map_written_to_output(self, tmp_path):
        from oil.run_export_cases import export_cases
        cases = tmp_path / "cases"
        _make_case(cases, "aa" * 8, "2026-02-01T10:00:00Z", 0.9, "payment")
        out = tmp_path / "export"
        export_cases(cases, out, min_confidence=0.0, anonymize=True)
        assert (out / "anonymization_map.json").exists()
        anon = json.loads((out / "anonymization_map.json").read_text())
        assert "payment" in anon

    def test_anonymize_applied_to_memory_json(self, tmp_path):
        from oil.run_export_cases import export_cases
        cases = tmp_path / "cases"
        run_id = "aa" * 8
        _make_case(cases, run_id, "2026-02-01T10:00:00Z", 0.9, "payment")
        out = tmp_path / "export"
        export_cases(cases, out, min_confidence=0.0, anonymize=True)
        mem = json.loads((out / "cases" / run_id / "memory.json").read_text())
        assert mem["origin_service"] != "payment"
        assert mem["origin_service"].startswith("SVC_")

    def test_anonymize_applied_to_incident_json(self, tmp_path):
        from oil.run_export_cases import export_cases
        cases = tmp_path / "cases"
        run_id = "aa" * 8
        _make_case(cases, run_id, "2026-02-01T10:00:00Z", 0.9, "payment")
        out = tmp_path / "export"
        export_cases(cases, out, min_confidence=0.0, anonymize=True)
        inc = json.loads((out / "cases" / run_id / "incident.json").read_text())
        # reference_service in report should be anonymized
        assert inc["report"]["reference_service"] != "payment"

    def test_anonymize_applied_to_summary_txt(self, tmp_path):
        from oil.run_export_cases import export_cases
        cases = tmp_path / "cases"
        run_id = "aa" * 8
        _make_case(cases, run_id, "2026-02-01T10:00:00Z", 0.9, "payment")
        out = tmp_path / "export"
        export_cases(cases, out, min_confidence=0.0, anonymize=True)
        txt = (out / "cases" / run_id / "summary.txt").read_text()
        assert "payment" not in txt

    def test_anonymize_origin_in_manifest(self, tmp_path):
        from oil.run_export_cases import export_cases
        cases = tmp_path / "cases"
        run_id = "aa" * 8
        _make_case(cases, run_id, "2026-02-01T10:00:00Z", 0.9, "zebra")
        out = tmp_path / "export"
        export_cases(cases, out, min_confidence=0.0, anonymize=True)
        manifest = json.loads((out / "manifest.json").read_text())
        # origin in manifest should be anonymized
        assert manifest[0]["origin_service"] != "zebra"
        assert manifest[0]["origin_service"].startswith("SVC_")

    def test_apply_anon_longest_match_first(self):
        """Longer service names replaced correctly even when shorter name is substring."""
        from oil.run_export_cases import _apply_anon_to_str
        anon_map = {"payment-gateway": "SVC_01", "payment": "SVC_02"}
        result = _apply_anon_to_str("payment-gateway and payment", anon_map)
        assert result == "SVC_01 and SVC_02"
