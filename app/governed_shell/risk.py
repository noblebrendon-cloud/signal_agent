from __future__ import annotations

from dataclasses import dataclass

from .normalize import NormalizedProposal


_RISK_ORDER = {
    "low": 0,
    "medium": 1,
    "high": 2,
    "critical": 3,
}
_WRITE_PARAMETER_NAMES = {
    "write_path",
    "output_path",
    "destination_path",
    "target_write_path",
}


@dataclass(frozen=True)
class RiskReport:
    effective_risk: str
    risk_factors: list[str]
    model_declared_risk: str | None
    model_risk_accepted_as_authority: bool
    confirmation_required: bool
    confirmation_mode: str


def _max_risk(current: str, candidate: str) -> str:
    if _RISK_ORDER[candidate] > _RISK_ORDER[current]:
        return candidate
    return current


def _parameter_map(operation: dict) -> dict[str, dict]:
    parameter_map: dict[str, dict] = {}

    for collection_name in ("parameters", "arguments"):
        items = operation.get(collection_name)
        if not isinstance(items, list):
            continue
        for item in items:
            if type(item) is not dict:
                continue
            name = item.get("name")
            if isinstance(name, str) and name not in parameter_map:
                parameter_map[name] = item

    return parameter_map


def _boolean_parameter(parameter_map: dict[str, dict], name: str) -> bool:
    payload = parameter_map.get(name)
    if type(payload) is not dict:
        return False
    if payload.get("value_type") != "boolean":
        return False
    return bool(payload.get("boolean_value"))


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def derive_effective_risk(
    normalized_proposal: NormalizedProposal,
    policy_binding: dict,
) -> RiskReport:
    """Derive authoritative risk from matched policy bindings."""

    policy = policy_binding.get("policy", {})
    binding_contexts = policy_binding.get("bindings", [])
    model_annotations = normalized_proposal.proposal.get("model_annotations", {})
    model_declared_risk = model_annotations.get("model_declared_risk_level")

    effective_risk = "low"
    risk_factors: list[str] = []

    for binding_context in binding_contexts:
        binding = binding_context.get("binding", {})
        operation = binding_context.get("operation", {})
        binding_id = str(binding_context.get("binding_id") or "")
        operation_type = str(operation.get("operation_type") or "")
        parameter_map = binding_context.get("parameter_map", {})

        if binding.get("declared_writes"):
            effective_risk = _max_risk(effective_risk, "high")
            risk_factors.append("binding_declares_writes")

        if any(name in _WRITE_PARAMETER_NAMES for name in parameter_map):
            effective_risk = _max_risk(effective_risk, "high")
            risk_factors.append("write_like_parameter_requested")

        if operation_type == "registered_native":
            effective_risk = _max_risk(effective_risk, "critical")
            risk_factors.append("native_operation_requested")

        lowered_binding_id = binding_id.lower()
        if any(token in lowered_binding_id for token in ("delete", "remove", "rm.")):
            effective_risk = _max_risk(effective_risk, "critical")
            risk_factors.append("destructive_binding_identifier")

        if binding.get("network_allowed"):
            effective_risk = _max_risk(effective_risk, "high")
            risk_factors.append("network_capability_requested")

        if binding.get("privilege_escalation_allowed"):
            effective_risk = _max_risk(effective_risk, "high")
            risk_factors.append("privilege_capability_requested")

        if binding_id == "ps.get_child_items_v1":
            risk_factors.append("read_only_listing")
            if _boolean_parameter(parameter_map, "recurse"):
                effective_risk = _max_risk(effective_risk, "medium")
                risk_factors.append("recursive_read")
            else:
                effective_risk = _max_risk(effective_risk, "low")
                risk_factors.append("non_recursive_read")

    confirmation_rule = (
        policy.get("confirmation_rules", {}).get(effective_risk)
        if type(policy) is dict
        else None
    )
    if type(confirmation_rule) is dict:
        confirmation_required = bool(confirmation_rule.get("required", True))
        confirmation_mode = str(confirmation_rule.get("mode", "exact_proposal_hash"))
    else:
        confirmation_required = True
        confirmation_mode = "exact_proposal_hash"

    return RiskReport(
        effective_risk=effective_risk,
        risk_factors=_dedupe_preserve_order(risk_factors),
        model_declared_risk=model_declared_risk if isinstance(model_declared_risk, str) else None,
        model_risk_accepted_as_authority=False,
        confirmation_required=confirmation_required,
        confirmation_mode=confirmation_mode,
    )
