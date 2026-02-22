from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from app.utils.dsl import predicate_eval, DSLViolation

Decision = str  # "ALLOW" | "REQUIRE_APPROVAL" | "DENY"

SCOPE_PRIORITY = {
    "GLOBAL": 1,
    "DOMAIN": 2,
    "TASK": 3,
    "SESSION": 4,
    "EMERGENCY": 5,
}

@dataclass(frozen=True)
class EvalResult:
    decision: Decision
    reason: str
    matched_constraints: List[str]  # constraint_ids
    matched_packs: List[str]
    limits_applied: List[Dict[str, Any]]  # record effective limits used

def sort_packs(packs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def pr(p: Dict[str, Any]) -> int:
        scope = str(p.get("pack_metadata", {}).get("scope", "GLOBAL")).upper()
        return SCOPE_PRIORITY.get(scope, 999)
    return sorted(packs, key=pr)

def matches_activation(pack: Dict[str, Any], context: Dict[str, Any]) -> bool:
    # minimal: domain_match gate
    ac = pack.get("activation_conditions", {}) or {}
    domains = ac.get("domain_match") or []
    if not domains:
        return True
    ctx_domain = str(context.get("domain", "")).lower()
    return any(str(d).lower() == ctx_domain for d in domains)

def extract_limit_key(rule: Dict[str, Any]) -> Tuple[str, str]:
    """
    LIMIT rules must declare:
      parameters.metric_id  (e.g. "session_cost_usd", "http_requests_per_min")
      parameters.selector_key (e.g. "GLOBAL" or "http:request" or "llm:generate")
    """
    p = rule.get("parameters") or {}
    metric_id = str(p.get("metric_id", "")).strip()
    selector_key = str(p.get("selector_key", "")).strip()
    if not metric_id or not selector_key:
        raise ValueError(f"LIMIT rule missing metric_id/selector_key: {rule.get('constraint_id')}")
    return metric_id, selector_key

def resolve(action: Dict[str, Any], snapshot: Dict[str, Any], packs: List[Dict[str, Any]], context: Dict[str, Any]) -> EvalResult:
    active = [p for p in packs if matches_activation(p, context)]
    active_sorted = sort_packs(active)

    deny_hits: List[str] = []
    approval_hits: List[str] = []
    matched_packs: List[str] = []

    # LIMIT aggregation: effective limit = min across applicable LIMIT rules
    effective_limits: Dict[Tuple[str, str], Dict[str, Any]] = {}  # (metric_id, selector_key) -> {value, constraint_id, pack}

    emergency_allow = False
    emergency_pack_names: List[str] = []

    for pack in active_sorted:
        pm = pack.get("pack_metadata", {}) or {}
        pack_name = str(pm.get("name", "unknown_pack"))
        pack_scope = str(pm.get("scope", "GLOBAL")).upper()
        rules = pack.get("constraint_rules") or []

        matched_packs.append(pack_name)

        for rule in rules:
            cid = str(rule.get("constraint_id", ""))
            rtype = str(rule.get("rule_type", "")).upper()
            pred = rule.get("predicate") or {}

            # EMERGENCY: only acts if explicitly enabled in context/policy
            if pack_scope == "EMERGENCY":
                if not context.get("emergency_override_enabled", False):
                    continue

            # Evaluate predicate (fail-closed)
            try:
                # Pass context to DSL engine
                applies = predicate_eval(pred, action, snapshot, context)
            except DSLViolation:
                # DSL syntax/runtime error -> BLOCK ALL
                return EvalResult(
                    decision="DENY",
                    reason="DSL_VIOLATION",
                    matched_constraints=[cid] if cid else [],
                    matched_packs=[pack_name],
                    limits_applied=[]
                )
            except Exception:
                # fail-closed per spec: internal error -> BLOCK ALL
                return EvalResult(
                    decision="DENY",
                    reason="SYSTEM_GOVERNANCE_FAILURE",
                    matched_constraints=[cid] if cid else [],
                    matched_packs=[pack_name],
                    limits_applied=[]
                )

            if not applies:
                continue

            if pack_scope == "EMERGENCY" and rtype == "ALLOW":
                emergency_allow = True
                emergency_pack_names.append(pack_name)
                continue

            if rtype == "DENY":
                deny_hits.append(cid)

            elif rtype == "REQUIRE_APPROVAL":
                approval_hits.append(cid)

            elif rtype == "LIMIT":
                metric_id, selector_key = extract_limit_key(rule)
                val = rule.get("parameters", {}).get("max_value")
                if val is None:
                    return EvalResult("DENY", "SCHEMA_VIOLATION", [cid], [pack_name], [])
                key = (metric_id, selector_key)

                # take min(max_value)
                if key not in effective_limits or float(val) < float(effective_limits[key]["max_value"]):
                    effective_limits[key] = {
                        "metric_id": metric_id,
                        "selector_key": selector_key,
                        "max_value": val,
                        "constraint_id": cid,
                        "pack": pack_name,
                        "scope": pack_scope
                    }

            elif rtype == "ALLOW":
                # Allow does not loosen anything; it only records intent
                pass

    if emergency_allow:
        return EvalResult(
            decision="ALLOW",
            reason="EMERGENCY_OVERRIDE",
            matched_constraints=[],
            matched_packs=emergency_pack_names,
            limits_applied=[]
        )

    # Early exit on deny
    if deny_hits:
        return EvalResult("DENY", "DENY_RULE", deny_hits, matched_packs, [])

    # Evaluate effective limits deterministically
    # NOTE: you must define where snapshot stores these metrics.
    # Example: snapshot["budgets"]["session_cost_usd"]["used"] etc.
    for key, lim in sorted(effective_limits.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        metric_id, selector_key = key
        # minimal: metric lookup in snapshot
        current_val = snapshot.get("metrics", {}).get(metric_id)
        if current_val is None:
            return EvalResult("DENY", "MISSING_METRIC", [lim["constraint_id"]], matched_packs, list(effective_limits.values()))
        if float(current_val) > float(lim["max_value"]):
            return EvalResult("DENY", "LIMIT_EXCEEDED", [lim["constraint_id"]], matched_packs, list(effective_limits.values()))

    if approval_hits:
        return EvalResult("REQUIRE_APPROVAL", "REQUIRES_APPROVAL", approval_hits, matched_packs, list(effective_limits.values()))

    return EvalResult("ALLOW", "CONSENSUS", [], matched_packs, list(effective_limits.values()))
