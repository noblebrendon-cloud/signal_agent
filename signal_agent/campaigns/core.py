"""Deterministic campaign proposals grounded in explicit, bounded evidence.

This module reads its versioned catalog and returns data. It does not publish,
approve releases, retrieve sources, or mutate campaign or artifact state.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any


CONTEXT_VERSION = "campaign_context.v1"
DECISION_VERSION = "campaign_decision.v1"
MAX_PAYLOAD_BYTES = 1_048_576
MAX_OBSERVATIONS = 1000
MAX_SOURCES = 32
MAX_SOURCE_CHARS = 200_000
MAX_CLAIMS = 200
MAX_OUTPUTS = 32
MAX_REFERENCES = 200
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_HASH = re.compile(r"(?:sha256:)?([a-fA-F0-9]{64})\Z")
PHASES = {"planned", "testing", "reviewing", "paused", "archived"}
OBSERVATION_KINDS = {
    "recognition", "request_for_depth", "misunderstanding", "conflict",
    "repeat_value", "performance", "other",
}
OUTPUT_KINDS = {"short_post", "essay", "video_script", "visual_brief", "narration_script"}
ACTIONS = {
    "observe_more", "revise_hook", "clarify_message", "deepen_explanation",
    "vary_format", "repeat_theme", "run_small_test", "adapt_platform",
    "expand_campaign", "propose_lane_routing", "pause", "archive",
}
PRODUCTION_ACTIONS = {
    "revise_hook", "clarify_message", "deepen_explanation", "vary_format",
    "repeat_theme", "run_small_test", "adapt_platform",
}


class CampaignValidationError(ValueError):
    """Input cannot be evaluated under the versioned campaign contract."""


def _fail(path: str, message: str) -> None:
    raise CampaignValidationError(f"{path}: {message}")


def _json_guard(value: Any, path: str = "$", depth: int = 0) -> None:
    if depth > 12:
        _fail(path, "JSON nesting exceeds 12 levels")
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float:
        if not math.isfinite(value):
            _fail(path, "numbers must be finite")
        return
    if type(value) is list:
        if len(value) > 10_000:
            _fail(path, "array exceeds input bound")
        for i, item in enumerate(value):
            _json_guard(item, f"{path}[{i}]", depth + 1)
        return
    if type(value) is dict:
        if len(value) > 1000:
            _fail(path, "object exceeds input bound")
        for key, item in value.items():
            if type(key) is not str:
                _fail(path, "object keys must be strings")
            _json_guard(item, f"{path}.{key}", depth + 1)
        return
    _fail(path, "must contain JSON values only")


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False,
                          sort_keys=True, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, OverflowError) as exc:
        raise CampaignValidationError("Input must be finite, UTF-8 JSON") from exc


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def _object(value: Any, allowed: set[str], required: set[str], path: str) -> dict:
    if type(value) is not dict:
        _fail(path, "must be an object")
    unknown = set(value) - allowed
    missing = required - set(value)
    if unknown:
        _fail(path, "unknown fields: " + ", ".join(sorted(unknown)))
    if missing:
        _fail(path, "missing fields: " + ", ".join(sorted(missing)))
    return value


def _text(value: Any, path: str, *, maximum: int = 4000,
          empty: bool = False, preserve: bool = False) -> str:
    if type(value) is not str:
        _fail(path, "must be a string")
    result = value if preserve else value.strip()
    if len(result) > maximum or (not empty and not result.strip()):
        _fail(path, f"must contain {'0' if empty else '1'} to {maximum} characters")
    return result


def _identifier(value: Any, path: str) -> str:
    result = _text(value, path, maximum=128)
    if not _ID.fullmatch(result):
        _fail(path, "must use letters, digits, dots, underscores, colons, or hyphens")
    return result


def _choice(value: Any, choices: set[str], path: str) -> str:
    result = _text(value, path, maximum=128)
    if result not in choices:
        _fail(path, "unsupported value: " + result)
    return result


def _integer(value: Any, path: str, *, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value <= 10**12:
        _fail(path, f"must be an integer between {minimum} and 1000000000000")
    return value


def _array(value: Any, path: str, maximum: int) -> list:
    if type(value) is not list or len(value) > maximum:
        _fail(path, f"must be an array of at most {maximum} items")
    return value


def _strings(value: Any, path: str, *, maximum: int = MAX_REFERENCES,
             item_maximum: int = 2048) -> list[str]:
    rows = _array(value, path, maximum)
    result = [_text(item, f"{path}[{i}]", maximum=item_maximum) for i, item in enumerate(rows)]
    if len(result) != len(set(result)):
        _fail(path, "duplicate references or values are not allowed")
    return result


def _unique(rows: list[dict], key: str, path: str) -> None:
    ids = [row[key] for row in rows]
    if len(ids) != len(set(ids)):
        _fail(path, f"duplicate {key} values are not allowed")


def _timestamp(value: Any, path: str) -> str:
    raw = _text(value, path, maximum=64)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if "T" not in raw or parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("timezone required")
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except (ValueError, OverflowError) as exc:
        raise CampaignValidationError(f"{path}: must be a timezone-aware ISO 8601 timestamp") from exc


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@lru_cache(maxsize=1)
def _catalog() -> dict:
    path = Path(__file__).with_name("principles.json")
    catalog = json.loads(path.read_text(encoding="utf-8"))
    _json_guard(catalog)
    if catalog.get("schema_version") != "campaign_principle_catalog.v1":
        raise CampaignValidationError("Unsupported principle catalog schema")
    principles = catalog.get("principles", [])
    expected = {"mirror", "future_self", "messaging", "enemy", "before", "consistency",
                "polarity", "transformation", "levels", "gap", "repeated_offender"}
    if len(principles) != 11 or {p.get("id") for p in principles} != expected:
        raise CampaignValidationError("Principle catalog must contain the eleven distinct source labels")
    return catalog


def load_principles() -> dict:
    """Return an independent copy of the versioned, source-qualified catalog."""
    return copy.deepcopy(_catalog())


def validate_campaign(payload: Any) -> dict:
    """Validate a bounded JSON context and return a normalized independent copy."""
    _json_guard(payload)
    if len(_canonical(payload)) > MAX_PAYLOAD_BYTES:
        _fail("$", f"encoded input exceeds {MAX_PAYLOAD_BYTES} bytes")
    fields = {"schema_version", "campaign_id", "title", "purpose", "phase", "principle_ids",
              "constraints", "sources", "claims", "review", "evaluation_plan", "observations",
              "requested_outputs", "operator_request", "lineage"}
    root = _object(payload, fields, {"schema_version", "campaign_id", "title", "purpose", "phase"}, "$")
    if root["schema_version"] != CONTEXT_VERSION:
        _fail("$.schema_version", "unsupported schema version")
    result = {
        "schema_version": CONTEXT_VERSION,
        "campaign_id": _identifier(root["campaign_id"], "$.campaign_id"),
        "title": _text(root["title"], "$.title", maximum=256),
        "purpose": _text(root["purpose"], "$.purpose", maximum=8000),
        "phase": _choice(root["phase"], PHASES, "$.phase"),
        "principle_ids": _strings(root.get("principle_ids", []), "$.principle_ids", maximum=11, item_maximum=128),
        "constraints": _strings(root.get("constraints", []), "$.constraints", maximum=50),
    }
    known = {row["id"] for row in _catalog()["principles"]}
    if set(result["principle_ids"]) - known:
        _fail("$.principle_ids", "unknown principle IDs")

    sources = []
    for i, raw in enumerate(_array(root.get("sources", []), "$.sources", MAX_SOURCES)):
        p = f"$.sources[{i}]"
        row = _object(raw, {"source_id", "text", "uri", "content_hash", "evidence_refs"}, {"source_id"}, p)
        text = _text(row.get("text", ""), p + ".text", maximum=MAX_SOURCE_CHARS, empty=True, preserve=True)
        given_hash = _text(row.get("content_hash", ""), p + ".content_hash", maximum=71, empty=True)
        if given_hash:
            match = _HASH.fullmatch(given_hash)
            if not match:
                _fail(p + ".content_hash", "must be a SHA-256 digest")
            given_hash = "sha256:" + match.group(1).lower()
        actual_hash = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest() if text else ""
        if text and given_hash and actual_hash != given_hash:
            _fail(p + ".content_hash", "does not match the supplied raw UTF-8 source text")
        sources.append({
            "source_id": _identifier(row["source_id"], p + ".source_id"),
            "text": text,
            "uri": _text(row.get("uri", ""), p + ".uri", maximum=4096, empty=True),
            "content_hash": given_hash or actual_hash,
            "evidence_refs": _strings(row.get("evidence_refs", []), p + ".evidence_refs"),
        })
    _unique(sources, "source_id", "$.sources")
    result["sources"] = sources

    claims = []
    for i, raw in enumerate(_array(root.get("claims", []), "$.claims", MAX_CLAIMS)):
        p = f"$.claims[{i}]"
        row = _object(raw, {"claim_id", "statement", "status", "evidence_refs"}, {"claim_id", "statement"}, p)
        claim = {
            "claim_id": _identifier(row["claim_id"], p + ".claim_id"),
            "statement": _text(row["statement"], p + ".statement", maximum=8000),
            "status": _choice(row.get("status", "unverified"), {"confirmed", "qualified", "unverified"}, p + ".status"),
            "evidence_refs": _strings(row.get("evidence_refs", []), p + ".evidence_refs"),
        }
        if claim["status"] == "confirmed" and not claim["evidence_refs"]:
            _fail(p + ".evidence_refs", "confirmed claims require recorded evidence references")
        claims.append(claim)
    _unique(claims, "claim_id", "$.claims")
    result["claims"] = claims

    review = _object(root.get("review", {}), {"mission", "source_fidelity", "by", "reason", "evidence_refs"}, set(), "$.review")
    result["review"] = {
        "mission": _choice(review.get("mission", "unknown"), {"aligned", "misaligned", "unknown"}, "$.review.mission"),
        "source_fidelity": _choice(review.get("source_fidelity", "unknown"), {"preserved", "violated", "unknown"}, "$.review.source_fidelity"),
        "by": _text(review.get("by", ""), "$.review.by", maximum=256, empty=True),
        "reason": _text(review.get("reason", ""), "$.review.reason", empty=True),
        "evidence_refs": _strings(review.get("evidence_refs", []), "$.review.evidence_refs"),
    }
    if any(result["review"][key] != "unknown" for key in ("mission", "source_fidelity")):
        if not result["review"]["by"] or not result["review"]["reason"]:
            _fail("$.review", "an editorial assessment requires attributed by and reason fields")

    plan = root.get("evaluation_plan")
    result["evaluation_plan"] = None
    if plan is not None:
        keys = {"window_start", "window_end", "platform", "format", "minimum_observations",
                "minimum_exposures", "minimum_independent_variants"}
        plan = _object(plan, keys, set(), "$.evaluation_plan")
        normalized = {}
        for key in sorted(keys):
            value = plan.get(key)
            if value is None:
                normalized[key] = None
            elif key.startswith("minimum_"):
                normalized[key] = _integer(value, "$.evaluation_plan." + key, minimum=1)
            elif key.startswith("window_"):
                normalized[key] = _timestamp(value, "$.evaluation_plan." + key)
            else:
                normalized[key] = _text(value, "$.evaluation_plan." + key, maximum=128).casefold()
        if normalized["window_start"] and normalized["window_end"]:
            if _time(normalized["window_end"]) <= _time(normalized["window_start"]):
                _fail("$.evaluation_plan", "window_end must follow window_start")
        result["evaluation_plan"] = normalized

    observations = []
    required = {"observation_id", "variant_id", "kind", "summary", "source_ref", "observed_at",
                "platform", "format", "verification"}
    for i, raw in enumerate(_array(root.get("observations", []), "$.observations", MAX_OBSERVATIONS)):
        p = f"$.observations[{i}]"
        row = _object(raw, required | {"verified_by", "exposures", "metric"}, required, p)
        observation = {
            "observation_id": _identifier(row["observation_id"], p + ".observation_id"),
            "variant_id": _identifier(row["variant_id"], p + ".variant_id"),
            "kind": _choice(row["kind"], OBSERVATION_KINDS, p + ".kind"),
            "summary": _text(row["summary"], p + ".summary"),
            "source_ref": _text(row["source_ref"], p + ".source_ref", maximum=4096, empty=True),
            "observed_at": _timestamp(row["observed_at"], p + ".observed_at"),
            "platform": _text(row["platform"], p + ".platform", maximum=128).casefold(),
            "format": _text(row["format"], p + ".format", maximum=128).casefold(),
            "verification": _choice(row["verification"], {"verified", "reported", "unverified", "contradicted"}, p + ".verification"),
            "verified_by": _text(row.get("verified_by", ""), p + ".verified_by", maximum=256, empty=True),
            "exposures": None if row.get("exposures") is None else _integer(row["exposures"], p + ".exposures"),
            "metric": None,
        }
        if observation["verification"] == "verified" and (not observation["verified_by"] or not observation["source_ref"]):
            _fail(p, "verified observations require verified_by and source_ref")
        metric = row.get("metric")
        if metric is not None:
            metric = _object(metric, {"name", "numerator", "denominator"}, {"name", "numerator", "denominator"}, p + ".metric")
            numerator = _integer(metric["numerator"], p + ".metric.numerator")
            denominator = _integer(metric["denominator"], p + ".metric.denominator", minimum=1)
            if numerator > denominator:
                _fail(p + ".metric", "count-rate numerator must not exceed its denominator")
            if observation["exposures"] is not None and denominator > observation["exposures"]:
                _fail(p + ".metric", "denominator must not exceed recorded exposures")
            observation["metric"] = {"name": _text(metric["name"], p + ".metric.name", maximum=128),
                                     "numerator": numerator, "denominator": denominator}
        observations.append(observation)
    _unique(observations, "observation_id", "$.observations")
    result["observations"] = observations

    outputs = []
    for i, raw in enumerate(_array(root.get("requested_outputs", []), "$.requested_outputs", MAX_OUTPUTS)):
        p = f"$.requested_outputs[{i}]"
        row = _object(raw, {"output_id", "kind", "description"}, {"output_id", "kind", "description"}, p)
        outputs.append({"output_id": _identifier(row["output_id"], p + ".output_id"),
                        "kind": _choice(row["kind"], OUTPUT_KINDS, p + ".kind"),
                        "description": _text(row["description"], p + ".description")})
    _unique(outputs, "output_id", "$.requested_outputs")
    result["requested_outputs"] = outputs

    request = root.get("operator_request")
    result["operator_request"] = None
    if request is not None:
        request = _object(request, {"action", "reason", "by", "evidence_refs"}, {"action", "reason", "by"}, "$.operator_request")
        result["operator_request"] = {
            "action": _choice(request["action"], ACTIONS, "$.operator_request.action"),
            "reason": _text(request["reason"], "$.operator_request.reason"),
            "by": _text(request["by"], "$.operator_request.by", maximum=256),
            "evidence_refs": _strings(request.get("evidence_refs", []), "$.operator_request.evidence_refs"),
        }
    lineage = root.get("lineage")
    result["lineage"] = None
    if lineage is not None:
        lineage = _object(lineage, {"parent_campaign_digest", "parent_decision_id", "parent_variant_ids",
                                    "corrected_claim_ids", "change_note"}, set(), "$.lineage")
        normalized_lineage = {
            "parent_campaign_digest": lineage.get("parent_campaign_digest"),
            "parent_decision_id": lineage.get("parent_decision_id"),
            "parent_variant_ids": _strings(lineage.get("parent_variant_ids", []), "$.lineage.parent_variant_ids", maximum=200, item_maximum=128),
            "corrected_claim_ids": _strings(lineage.get("corrected_claim_ids", []), "$.lineage.corrected_claim_ids", maximum=200, item_maximum=128),
            "change_note": _text(lineage.get("change_note", ""), "$.lineage.change_note", maximum=4000, empty=True),
        }
        for key, prefix in (("parent_campaign_digest", "sha256:"), ("parent_decision_id", "campaign_decision.")):
            value = normalized_lineage[key]
            if value is not None:
                value = _text(value, "$.lineage." + key, maximum=128)
                if not re.fullmatch(re.escape(prefix) + r"[a-f0-9]{64}", value):
                    _fail("$.lineage." + key, "must contain the expected prefix and 64 lowercase hexadecimal characters")
                normalized_lineage[key] = value
        for key in ("parent_variant_ids", "corrected_claim_ids"):
            normalized_lineage[key] = [_identifier(value, f"$.lineage.{key}[{i}]")
                                       for i, value in enumerate(normalized_lineage[key])]
        if normalized_lineage["corrected_claim_ids"]:
            if not normalized_lineage["change_note"]:
                _fail("$.lineage.change_note", "claim corrections require an explicit change note")
            if not any(normalized_lineage[key] for key in ("parent_campaign_digest", "parent_decision_id", "parent_variant_ids")):
                _fail("$.lineage", "claim corrections require at least one parent reference")
        result["lineage"] = normalized_lineage
    return result


def _assess_evidence(campaign: dict, evaluated_at: str) -> tuple[dict, list[dict], list[dict]]:
    plan = campaign["evaluation_plan"] or {}
    now = _time(evaluated_at)
    eligible, references, excluded = [], [], []
    seen_measurements = set()
    qualitative_signals = set()
    exposures: dict[str, int | None] = {}
    duplicates = 0
    # A recorded correction can invalidate an earlier reference even when the
    # correction itself was recorded after the original evaluation window.
    # It must still be a past, comparable-context record for this campaign.
    contradicted_refs = {
        row["source_ref"] for row in campaign["observations"]
        if row["verification"] == "contradicted" and row["source_ref"]
        and _time(row["observed_at"]) <= now
        and (not plan.get("platform") or row["platform"] == plan["platform"])
        and (not plan.get("format") or row["format"] == plan["format"])
    }
    for row in campaign["observations"]:
        reasons = []
        when = _time(row["observed_at"])
        if row["verification"] != "verified":
            reasons.append("observation_not_verified")
        if when > now:
            reasons.append("observation_in_future")
        if plan.get("window_start") and when < _time(plan["window_start"]):
            reasons.append("outside_evaluation_window")
        if plan.get("window_end") and when > _time(plan["window_end"]):
            reasons.append("outside_evaluation_window")
        if plan.get("platform") and row["platform"] != plan["platform"]:
            reasons.append("platform_not_comparable")
        if plan.get("format") and row["format"] != plan["format"]:
            reasons.append("format_not_comparable")
        if row["source_ref"] in contradicted_refs:
            reasons.append("observation_reference_contradicted")
        qualitatively_eligible = not reasons
        if not reasons:
            # Semantic signals may share a source, but that source cannot count
            # twice toward sample/variant criteria. Granular references should
            # identify genuinely separate measurements in a shared report.
            qualitative_signals.add(row["kind"])
            measurement = row["source_ref"]
            if measurement in seen_measurements:
                duplicates += 1
                reasons.append("duplicate_measurement_reference")
            else:
                seen_measurements.add(measurement)
                eligible.append(row)
                # A variant contributes its largest accepted total once.
                # Excluded duplicate reports must not alter that total.
                previous = exposures.get(row["variant_id"])
                count = row["exposures"]
                exposures[row["variant_id"]] = max(previous or 0, count) if count is not None else previous
        if reasons:
            excluded.append({"observation_id": row["observation_id"], "reason_codes": reasons})
        references.append({
            "observation_id": row["observation_id"], "variant_id": row["variant_id"],
            "source_ref": row["source_ref"], "verification": row["verification"],
            "verified_by": row["verified_by"], "eligible_for_assessment": not reasons,
            "eligible_for_qualitative_assessment": qualitatively_eligible,
            "exclusion_reasons": reasons,
        })
    plan_complete = bool(plan) and all(value is not None for value in plan.values())
    window_complete = bool(plan.get("window_end")) and now >= _time(plan["window_end"])
    exposure_complete = bool(exposures) and all(value is not None for value in exposures.values())
    total_exposures = sum(value for value in exposures.values() if value is not None)
    variants = {row["variant_id"] for row in eligible}
    checks = {
        "minimum_observations": len(eligible) >= plan["minimum_observations"] if plan.get("minimum_observations") is not None else None,
        "minimum_exposures": exposure_complete and total_exposures >= plan["minimum_exposures"] if plan.get("minimum_exposures") is not None else None,
        "minimum_independent_variants": len(variants) >= plan["minimum_independent_variants"] if plan.get("minimum_independent_variants") is not None else None,
    }
    criteria_met = plan_complete and window_complete and all(value is True for value in checks.values())
    repeat_variants = {row["variant_id"] for row in eligible if row["kind"] == "repeat_value"}
    repeat_required = max(2, plan.get("minimum_independent_variants") or 2)
    repeat_supported = bool(criteria_met and len(repeat_variants) >= repeat_required
                            and not qualitative_signals.intersection({"misunderstanding", "conflict"}))
    quality = {
        "status": "no_observations" if not campaign["observations"] else "insufficient",
        "total_observations": len(campaign["observations"]),
        "verified_observations": sum(row["verification"] == "verified" for row in campaign["observations"]),
        "eligible_observations": len(eligible),
        "independent_variants": len(variants),
        "counted_exposures": total_exposures,
        "exposure_counts_complete": exposure_complete,
        "exposures_by_variant": dict(sorted(exposures.items())),
        "duplicate_measurements": duplicates,
        "contradicted_reference_count": len(contradicted_refs),
        "excluded_observations": excluded,
        "qualitative_signals": sorted(qualitative_signals),
        "window_complete": window_complete,
        "plan_complete": plan_complete,
        "criteria_met": bool(criteria_met),
        "repeat_support_independent_variants": len(repeat_variants),
        "repeat_supported": repeat_supported,
        "checks": checks,
        "comparison_context": {key: plan.get(key) for key in ("platform", "format", "window_start", "window_end")},
        "verification_basis": "recorded_attestation_not_independent_verification",
        "causal_effect_established": False,
    }
    if repeat_supported:
        quality["status"] = "adequate_for_bounded_repeat"
    elif qualitative_signals.intersection({"misunderstanding", "request_for_depth"}):
        quality["status"] = "qualitative_only"
    return quality, eligible, references


def evaluate_campaign(payload: Any, *, evaluated_at: str) -> dict:
    """Return a versioned next-action proposal; never execute or grant authority."""
    campaign = validate_campaign(payload)
    at = _timestamp(evaluated_at, "evaluated_at")
    catalog = _catalog()
    quality, eligible, evidence_refs = _assess_evidence(campaign, at)
    codes, reasons = [], []
    limitations = [
        "Creative principles are proposed adaptations of visible video labels; the spoken definitions were not verified.",
        "Recorded evidence and editorial assessments are attributed inputs, not independent verification by this evaluator.",
        "Observational records do not establish causal improvement or authorize publication, spending, or state changes.",
        "Exposure totals count instances across distinct recorded variants, not unique people; audience overlap and statistical independence are not established.",
    ]

    def note(code: str, reason: str) -> None:
        if code not in codes:
            codes.append(code)
            reasons.append(reason)

    review = campaign["review"]
    request = campaign["operator_request"]
    requested_action = request["action"] if request else None
    readable = bool(campaign["sources"]) and all(source["text"].strip() for source in campaign["sources"])
    editorial_ready = review["mission"] == "aligned" and review["source_fidelity"] == "preserved"
    kinds = set(quality["qualitative_signals"])
    action = "observe_more"

    if campaign["phase"] == "archived":
        action = "archive"
        note("campaign_archived", "The campaign is already archived; evaluation preserves that state.")
    elif campaign["phase"] == "paused":
        action = "pause"
        note("campaign_paused", "The campaign is paused; this evaluator cannot resume it.")
    elif review["mission"] == "misaligned" or review["source_fidelity"] == "violated":
        action = "pause"
        if review["mission"] == "misaligned":
            note("mission_misaligned", "The attributed editorial assessment identifies a conflict with the campaign purpose.")
        if review["source_fidelity"] == "violated":
            note("source_fidelity_violated", "The attributed editorial assessment reports a source-fidelity violation.")
    elif requested_action in {"pause", "archive"}:
        action = requested_action
        note("operator_requested_" + action, request["reason"])
    elif requested_action == "propose_lane_routing":
        action = "propose_lane_routing"
        note("operator_requested_lane_review", request["reason"])
        note("durable_lane_evidence_requires_review", "The existing protocol must assess meaning-based fit and durable evidence before any lane decision.")
        limitations.append("This requests review of an existing meaning-based lane; no lane is created, assigned, or authorized.")
    elif not readable:
        note("source_text_unavailable", "Readable text is required for every source included in a production packet; a URI or hash alone does not prove retrieval.")
    elif not editorial_ready:
        note("editorial_review_incomplete", "Record an attributed mission and source-fidelity assessment before preparing production work; this is not a release approval.")
    elif requested_action == "observe_more":
        note("operator_requested_observation", request["reason"])
    elif requested_action in PRODUCTION_ACTIONS - {"repeat_theme"}:
        action = requested_action
        note("operator_requested_bounded_experiment", request["reason"])
        note("hypothesis_only", "The requested variation is a bounded creative hypothesis, not demonstrated audience success.")
    elif requested_action in {"repeat_theme", "expand_campaign"}:
        if quality["repeat_supported"] and not kinds.intersection({"misunderstanding", "conflict"}):
            action = requested_action
            note("repeated_comparable_evidence", "The completed evaluation window meets the supplied criteria and includes repeat-value observations across distinct variants.")
            if action == "expand_campaign":
                note("expansion_scope_requires_review", "Broader production capacity, scope, and authority require a separate governed decision.")
        else:
            action = "run_small_test"
            note("repeat_evidence_insufficient", "The request does not establish adequate comparable repeated evidence; propose only a bounded additional test.")
            note("hypothesis_only", "No winning pattern, causal lift, or campaign expansion has been established.")
    elif "misunderstanding" in kinds:
        action = "clarify_message"
        note("verified_misunderstanding", "A relevant attributed observation supports testing a clearer explanation of the same qualified claim.")
        note("hypothesis_only", "This is a bounded response to recorded confusion, not a performance-success claim.")
    elif "request_for_depth" in kinds:
        action = "deepen_explanation"
        note("verified_request_for_depth", "A relevant attributed request supports preparing a bounded deeper explanation.")
        note("hypothesis_only", "A request for detail supports an editorial response; it does not establish causal impact or broad demand.")
    elif not campaign["observations"] and campaign["phase"] == "planned":
        action = "run_small_test"
        note("no_observations", "No audience observations have been recorded.")
        note("exploratory_hypothesis_only", "Prepare a bounded initial test and record what happens before inferring a repeatable pattern.")
    elif not campaign["observations"]:
        note("no_observations", "This campaign has entered testing or review without recorded audience observations.")
        note("await_observation_evidence", "Record the existing test outcome before inferring another production step, or explicitly request a bounded variation.")
    elif quality["repeat_supported"] and "conflict" not in kinds:
        action = "repeat_theme"
        note("repeated_comparable_evidence", "The completed window meets the campaign-specific criteria with repeat-value observations across distinct variants.")
        note("observational_repeat_only", "A bounded repetition is supported for further observation; no universal or causal claim follows.")
    else:
        note("evidence_insufficient_for_next_production", "Collect relevant comparable evidence or request a clearly labeled bounded variation.")

    if campaign["observations"] and not quality["plan_complete"]:
        note("evaluation_plan_incomplete", "A complete window, context, and campaign-specific minimums are needed to assess repeated audience evidence.")
    elif campaign["observations"] and not quality["window_complete"]:
        note("evaluation_window_incomplete", "The planned evaluation window has not completed.")
    if campaign["observations"] and quality["excluded_observations"]:
        limitations.append("Some observations were excluded from assessment; their references and exclusion reasons remain recorded.")
    if campaign["observations"] and not quality["criteria_met"]:
        limitations.append("The supplied evidence does not meet all completed-window comparison criteria; no winner or performance-based lane claim is established.")
    if "conflict" in kinds:
        limitations.append("Conflict or comment volume alone is not evidence of usefulness or mission success.")
    if any(row["status"] != "confirmed" for row in campaign["claims"]):
        limitations.append("Qualified and unverified claims must retain their qualifications in every derivative.")
    if campaign["constraints"]:
        limitations.append("Textual constraints accompany the handoff; arbitrary constraint prose is not automatically interpreted as executable policy.")
    if campaign["lineage"] is not None:
        limitations.append("Predecessor and correction links are caller-supplied references; this evaluator has not looked up or verified the existence of parent records.")
    if requested_action == "propose_lane_routing" and not quality["repeat_supported"]:
        limitations.append("Audience success is unestablished; any lane-review rationale must rest on meaning and separately reviewed durable evidence.")
    # Require explicit qualified claims for production. The existing authoring
    # model otherwise synthesizes a claim from a source prefix, which can drop
    # a qualification appearing later in the source text.
    production_eligible = bool(action in PRODUCTION_ACTIONS and readable and editorial_ready
                               and campaign["requested_outputs"] and campaign["claims"])
    if action in PRODUCTION_ACTIONS and not campaign["requested_outputs"]:
        note("requested_outputs_missing", "Specify bounded requested outputs before a production packet can be prepared.")
    if action in PRODUCTION_ACTIONS and not campaign["claims"]:
        note("requested_claims_missing", "Record at least one explicit claim with its qualifications before production; source text must not be truncated into an inferred claim.")
    hypothesis = {
        "run_small_test": "A bounded expression or variation may serve the stated purpose; outcomes remain to be observed.",
        "clarify_message": "A clearer expression may improve comprehension while preserving the source qualifications.",
        "deepen_explanation": "A bounded deeper explanation may serve the stated purpose; audience demand is limited to the evidence actually recorded.",
        "repeat_theme": "A distinct expression of the same theme may reproduce recorded usefulness in a comparable context.",
        "revise_hook": "A different truthful opening may make the same supported claim easier to understand.",
        "vary_format": "A different format may improve access to the same qualified meaning.",
        "adapt_platform": "A destination-specific presentation may convey the same meaning under that destination's constraints.",
    }.get(action, "No production-effect hypothesis is authorized by this evaluation.")
    decision = {
        "schema_version": DECISION_VERSION,
        "campaign_id": campaign["campaign_id"],
        "campaign_digest": _digest(campaign),
        "catalog_version": catalog["version"],
        "catalog_digest": _digest(catalog),
        "evaluated_at": at,
        "phase": campaign["phase"],
        "proposed_action": action,
        "reason_codes": codes,
        "reasons": reasons,
        "principle_ids": list(campaign["principle_ids"]),
        "evidence_references": evidence_refs,
        "evidence_quality": quality,
        "limitations": limitations,
        "working_hypothesis": hypothesis,
        "source_references": [{"source_id": s["source_id"], "uri": s["uri"], "content_hash": s["content_hash"],
                               "evidence_refs": list(s["evidence_refs"]), "text_available": bool(s["text"].strip())}
                              for s in campaign["sources"]],
        "requested_outputs": copy.deepcopy(campaign["requested_outputs"]),
        "constraints": list(campaign["constraints"]),
        "lineage": copy.deepcopy(campaign["lineage"]),
        "execution_status": "not_executed",
        "authority_status": "not_granted_by_evaluation",
        "production_eligible": production_eligible,
    }
    decision["decision_id"] = "campaign_decision." + hashlib.sha256(_canonical(decision)).hexdigest()
    return decision
