from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .errors import PolicyDeniedError, PolicyLoadError, PolicyValidationError
from .normalize import NormalizedProposal
from .proposal import dump_canonical_json
from .risk import RiskReport, derive_effective_risk


DEFAULT_POLICY_PATH = (
    Path(__file__).resolve().parents[2]
    / "config"
    / "policies"
    / "governed_shell_policy.yaml"
)

_WRITE_PARAMETER_NAMES = {
    "write_path",
    "output_path",
    "destination_path",
    "target_write_path",
}


@dataclass(frozen=True)
class PolicyValidationResult:
    clean: bool
    issues: list[str]
    policy_id: str | None
    policy_version: str | None
    policy_hash: str | None


@dataclass(frozen=True)
class PolicyDecision:
    clean: bool
    decision: str
    reason_code: str
    issues: list[str]
    matched_binding_id: str | None
    effective_risk: str | None
    confirmation_required: bool
    confirmation_mode: str
    proposal_hash: str
    policy_hash: str
    declared_reads: list[dict[str, str]]
    declared_writes: list[dict[str, str]]
    network_allowed: bool
    privilege_escalation_allowed: bool


def _compute_policy_hash(policy: dict) -> str:
    canonical_json = dump_canonical_json(policy)
    return f"sha256:{hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()}"


def _decision(
    *,
    normalized: NormalizedProposal,
    policy_hash: str,
    clean: bool,
    decision: str,
    reason_code: str,
    issues: list[str],
    matched_binding_id: str | None = None,
    effective_risk: str | None = None,
    confirmation_required: bool = False,
    confirmation_mode: str = "none",
    declared_reads: list[dict[str, str]] | None = None,
    declared_writes: list[dict[str, str]] | None = None,
    network_allowed: bool = False,
    privilege_escalation_allowed: bool = False,
) -> PolicyDecision:
    return PolicyDecision(
        clean=clean,
        decision=decision,
        reason_code=reason_code,
        issues=list(issues),
        matched_binding_id=matched_binding_id,
        effective_risk=effective_risk,
        confirmation_required=confirmation_required,
        confirmation_mode=confirmation_mode,
        proposal_hash=normalized.proposal_hash,
        policy_hash=policy_hash,
        declared_reads=list(declared_reads or []),
        declared_writes=list(declared_writes or []),
        network_allowed=network_allowed,
        privilege_escalation_allowed=privilege_escalation_allowed,
    )


def _root_path_map(normalized: NormalizedProposal) -> dict[str, dict]:
    mapping: dict[str, dict] = {}
    for path_ref in normalized.proposal.get("path_refs", []):
        if type(path_ref) is not dict:
            continue
        path_ref_id = path_ref.get("path_ref_id")
        if isinstance(path_ref_id, str):
            mapping[path_ref_id] = path_ref
    return mapping


def _operation_argument_items(operation: dict) -> list[dict]:
    for collection_name in ("parameters", "arguments"):
        items = operation.get(collection_name)
        if isinstance(items, list):
            return [item for item in items if type(item) is dict]
    return []


def _parameter_map(operation: dict) -> tuple[dict[str, dict], list[str]]:
    duplicates: list[str] = []
    mapping: dict[str, dict] = {}
    for item in _operation_argument_items(operation):
        name = item.get("name")
        if not isinstance(name, str):
            continue
        if name in mapping:
            duplicates.append(name)
            continue
        mapping[name] = item
    return mapping, duplicates


def _contains_forbidden_field(obj: Any, forbidden_fields: set[str], *, path: str = "$") -> list[str]:
    matches: list[str] = []
    if type(obj) is dict:
        for key, value in obj.items():
            child_path = f"{path}.{key}"
            if key in forbidden_fields:
                matches.append(child_path)
            matches.extend(_contains_forbidden_field(value, forbidden_fields, path=child_path))
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            matches.extend(_contains_forbidden_field(value, forbidden_fields, path=f"{path}[{index}]"))
    return matches


def _contains_forbidden_token(obj: Any, forbidden_tokens: set[str]) -> list[str]:
    matches: list[str] = []
    lowered_tokens = {token.lower() for token in forbidden_tokens}
    if type(obj) is dict:
        for value in obj.values():
            matches.extend(_contains_forbidden_token(value, forbidden_tokens))
    elif isinstance(obj, list):
        for value in obj:
            matches.extend(_contains_forbidden_token(value, forbidden_tokens))
    elif isinstance(obj, str):
        if obj.strip().lower() in lowered_tokens:
            matches.append(obj)
    return matches


def _resolve_declared_paths(
    *,
    binding_id: str,
    declaration: list[dict],
    parameter_map: dict[str, dict],
    path_refs_by_id: dict[str, dict],
) -> tuple[list[dict[str, str]], str | None, list[str]]:
    resolved: list[dict[str, str]] = []
    issues: list[str] = []

    for item in declaration:
        if type(item) is not dict:
            issues.append(f"binding {binding_id!r} contains a non-object surface declaration.")
            continue

        if item.get("source") != "parameter":
            issues.append(f"binding {binding_id!r} contains unsupported declaration source.")
            continue

        parameter_name = item.get("parameter")
        if not isinstance(parameter_name, str):
            issues.append(f"binding {binding_id!r} contains a declaration without parameter.")
            continue

        parameter_value = parameter_map.get(parameter_name)
        if type(parameter_value) is not dict:
            return [], "unknown_path_ref", [f"missing declared path parameter {parameter_name!r}."]
        if parameter_value.get("value_type") != "path_ref":
            return [], "unknown_path_ref", [f"declared path parameter {parameter_name!r} is not a path_ref."]

        path_ref_id = parameter_value.get("path_ref")
        if not isinstance(path_ref_id, str) or path_ref_id not in path_refs_by_id:
            return [], "unknown_path_ref", [f"unknown path_ref {path_ref_id!r}."]

        path_ref = path_refs_by_id[path_ref_id]
        root_id = path_ref.get("root_id")
        relative_path = path_ref.get("relative_path")
        if not isinstance(root_id, str) or not isinstance(relative_path, str):
            return [], "unknown_path_ref", [f"path_ref {path_ref_id!r} is incomplete."]

        resolved.append(
            {
                "binding_id": binding_id,
                "parameter": parameter_name,
                "path_ref_id": path_ref_id,
                "root_id": root_id,
                "relative_path": relative_path,
            }
        )

    return resolved, None, issues


def load_policy(path: Path | None = None) -> dict:
    """Load the governed shell policy YAML as a plain dict."""

    resolved_path = path or DEFAULT_POLICY_PATH
    if not resolved_path.exists():
        raise PolicyLoadError(f"Governed shell policy file not found: {resolved_path}")

    try:
        payload = yaml.safe_load(resolved_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise PolicyLoadError(f"Unable to read governed shell policy file: {exc}") from exc
    except yaml.YAMLError as exc:
        raise PolicyValidationError(f"Malformed governed shell policy YAML: {exc}") from exc

    if payload is None:
        payload = {}

    if type(payload) is not dict:
        raise PolicyValidationError("Governed shell policy must decode to a top-level mapping.")

    return payload


def validate_policy(policy: dict) -> PolicyValidationResult:
    """Validate the governed shell policy structure."""

    issues: list[str] = []
    policy_id: str | None = None
    policy_version: str | None = None
    policy_hash: str | None = None

    if type(policy) is not dict:
        return PolicyValidationResult(
            clean=False,
            issues=["policy must be a plain dict."],
            policy_id=None,
            policy_version=None,
            policy_hash=None,
        )

    policy_id_value = policy.get("policy_id")
    if isinstance(policy_id_value, str):
        policy_id = policy_id_value
    else:
        issues.append("policy_id must be a string.")

    policy_version_value = policy.get("policy_version")
    if isinstance(policy_version_value, (str, int)):
        policy_version = str(policy_version_value)
    else:
        issues.append("policy_version must be present.")

    required_mapping_fields = (
        "roots",
        "cmdlet_catalog",
        "script_catalog",
        "native_catalog",
        "global_deny",
        "risk_rules",
        "confirmation_rules",
    )
    for field_name in required_mapping_fields:
        if type(policy.get(field_name)) is not dict:
            issues.append(f"{field_name} must be a mapping.")

    if policy.get("default_action") != "deny":
        issues.append("default_action must be 'deny'.")
    if policy.get("network_allowed") is not False:
        issues.append("network_allowed must be false in MVP.")
    if policy.get("privilege_escalation_allowed") is not False:
        issues.append("privilege_escalation_allowed must be false in MVP.")

    if type(policy.get("global_deny")) is dict:
        global_deny = policy["global_deny"]
        for field_name in (
            "forbidden_fields",
            "forbidden_tokens",
            "path_escape_indicators",
        ):
            if not isinstance(global_deny.get(field_name), list):
                issues.append(f"global_deny.{field_name} must be a list.")

    cmdlet_catalog = policy.get("cmdlet_catalog")
    if type(cmdlet_catalog) is dict:
        binding = cmdlet_catalog.get("ps.get_child_items_v1")
        if type(binding) is not dict:
            issues.append("cmdlet_catalog.ps.get_child_items_v1 must be present.")
        else:
            if binding.get("operation_type") != "powershell_cmdlet":
                issues.append("ps.get_child_items_v1 must target powershell_cmdlet.")
            if binding.get("read_only") is not True:
                issues.append("ps.get_child_items_v1 must be marked read_only.")
            if binding.get("network_allowed") is not False:
                issues.append("ps.get_child_items_v1 must not allow network access.")
            if binding.get("privilege_escalation_allowed") is not False:
                issues.append("ps.get_child_items_v1 must not allow privilege escalation.")

    confirmation_rules = policy.get("confirmation_rules")
    if type(confirmation_rules) is dict:
        for risk_level in ("low", "medium", "high", "critical"):
            if type(confirmation_rules.get(risk_level)) is not dict:
                issues.append(f"confirmation_rules.{risk_level} must be defined.")

    if not issues:
        policy_hash = _compute_policy_hash(policy)

    return PolicyValidationResult(
        clean=not issues,
        issues=issues,
        policy_id=policy_id,
        policy_version=policy_version,
        policy_hash=policy_hash,
    )


def evaluate_policy(
    normalized: NormalizedProposal,
    policy: dict | None = None,
) -> PolicyDecision:
    """Evaluate a normalized proposal against the governed shell policy."""

    try:
        resolved_policy = copy.deepcopy(policy) if policy is not None else load_policy()
    except PolicyLoadError as exc:
        return _decision(
            normalized=normalized,
            policy_hash="sha256:" + ("0" * 64),
            clean=False,
            decision="deny",
            reason_code="policy_missing",
            issues=[str(exc)],
        )
    except PolicyValidationError as exc:
        return _decision(
            normalized=normalized,
            policy_hash="sha256:" + ("0" * 64),
            clean=False,
            decision="deny",
            reason_code="policy_invalid",
            issues=[str(exc)],
        )

    validation = validate_policy(resolved_policy)
    if not validation.clean or validation.policy_hash is None:
        return _decision(
            normalized=normalized,
            policy_hash=validation.policy_hash or ("sha256:" + ("0" * 64)),
            clean=False,
            decision="deny",
            reason_code="policy_invalid",
            issues=validation.issues,
        )

    if not normalized.path_validation.clean:
        return _decision(
            normalized=normalized,
            policy_hash=validation.policy_hash,
            clean=False,
            decision="deny",
            reason_code="path_invalid",
            issues=normalized.path_validation.errors,
        )

    proposal = normalized.proposal
    global_deny = resolved_policy["global_deny"]
    forbidden_fields = set(global_deny.get("forbidden_fields", []))
    forbidden_tokens = set(global_deny.get("forbidden_tokens", []))
    forbidden_field_matches = _contains_forbidden_field(proposal, forbidden_fields)
    if forbidden_field_matches:
        return _decision(
            normalized=normalized,
            policy_hash=validation.policy_hash,
            clean=False,
            decision="deny",
            reason_code="forbidden_field",
            issues=[f"forbidden field present at {match}" for match in forbidden_field_matches],
        )

    forbidden_token_matches = _contains_forbidden_token(proposal, forbidden_tokens)
    if forbidden_token_matches:
        return _decision(
            normalized=normalized,
            policy_hash=validation.policy_hash,
            clean=False,
            decision="deny",
            reason_code="forbidden_token",
            issues=[f"forbidden token present: {match}" for match in forbidden_token_matches],
        )

    roots = resolved_policy["roots"]
    path_refs_by_id = _root_path_map(normalized)
    for path_ref_id, path_ref in path_refs_by_id.items():
        root_id = path_ref.get("root_id")
        if not isinstance(root_id, str) or root_id not in roots:
            return _decision(
                normalized=normalized,
                policy_hash=validation.policy_hash,
                clean=False,
                decision="deny",
                reason_code="root_not_allowed",
                issues=[f"path_ref {path_ref_id!r} uses unknown root {root_id!r}."],
            )
        root_policy = roots.get(root_id, {})
        if type(root_policy) is not dict or root_policy.get("enabled") is not True:
            return _decision(
                normalized=normalized,
                policy_hash=validation.policy_hash,
                clean=False,
                decision="deny",
                reason_code="root_not_allowed",
                issues=[f"root {root_id!r} is not enabled by policy."],
            )

    matched_bindings: list[dict] = []
    declared_reads: list[dict[str, str]] = []
    declared_writes: list[dict[str, str]] = []

    operations = proposal.get("operations", [])
    if not isinstance(operations, list):
        return _decision(
            normalized=normalized,
            policy_hash=validation.policy_hash,
            clean=False,
            decision="deny",
            reason_code="unsupported_operation_type",
            issues=["proposal operations must be a list."],
        )

    for operation in operations:
        if type(operation) is not dict:
            return _decision(
                normalized=normalized,
                policy_hash=validation.policy_hash,
                clean=False,
                decision="deny",
                reason_code="unsupported_operation_type",
                issues=["operation must be an object."],
            )

        operation_type = operation.get("operation_type")
        if operation_type not in {"powershell_cmdlet", "registered_script", "registered_native"}:
            return _decision(
                normalized=normalized,
                policy_hash=validation.policy_hash,
                clean=False,
                decision="deny",
                reason_code="unsupported_operation_type",
                issues=[f"unsupported operation_type {operation_type!r}."],
            )

        parameter_map, duplicates = _parameter_map(operation)
        if duplicates:
            return _decision(
                normalized=normalized,
                policy_hash=validation.policy_hash,
                clean=False,
                decision="deny",
                reason_code="unknown_parameter",
                issues=[f"duplicate parameter name {name!r}." for name in duplicates],
            )

        if "network_access" in parameter_map:
            payload = parameter_map["network_access"]
            if payload.get("value_type") == "boolean" and bool(payload.get("boolean_value")):
                return _decision(
                    normalized=normalized,
                    policy_hash=validation.policy_hash,
                    clean=False,
                    decision="deny",
                    reason_code="network_denied_mvp",
                    issues=["network_access=true is denied in MVP."],
                )

        if "privilege_change" in parameter_map:
            payload = parameter_map["privilege_change"]
            if payload.get("value_type") == "boolean" and bool(payload.get("boolean_value")):
                return _decision(
                    normalized=normalized,
                    policy_hash=validation.policy_hash,
                    clean=False,
                    decision="deny",
                    reason_code="privilege_denied_mvp",
                    issues=["privilege_change=true is denied in MVP."],
                )

        if any(name in _WRITE_PARAMETER_NAMES for name in parameter_map):
            return _decision(
                normalized=normalized,
                policy_hash=validation.policy_hash,
                clean=False,
                decision="deny",
                reason_code="write_not_allowed",
                issues=["read-only MVP bindings must not declare write-like parameters."],
                effective_risk="high",
            )

        if operation_type == "registered_native":
            return _decision(
                normalized=normalized,
                policy_hash=validation.policy_hash,
                clean=False,
                decision="deny",
                reason_code="native_denied_mvp",
                issues=["registered_native operations are denied in MVP."],
            )

        if operation_type == "registered_script":
            binding_id = operation.get("script_id")
            if not isinstance(binding_id, str):
                return _decision(
                    normalized=normalized,
                    policy_hash=validation.policy_hash,
                    clean=False,
                    decision="deny",
                    reason_code="unknown_binding",
                    issues=["registered_script is missing script_id."],
                )
            binding = resolved_policy["script_catalog"].get(binding_id)
            if type(binding) is not dict:
                return _decision(
                    normalized=normalized,
                    policy_hash=validation.policy_hash,
                    clean=False,
                    decision="deny",
                    reason_code="unknown_binding",
                    issues=[f"script binding {binding_id!r} is not present in policy."],
                )
            if binding.get("enabled") is not True:
                return _decision(
                    normalized=normalized,
                    policy_hash=validation.policy_hash,
                    clean=False,
                    decision="deny",
                    reason_code="disabled_binding",
                    issues=[f"script binding {binding_id!r} is disabled in MVP."],
                    matched_binding_id=binding_id,
                )
            return _decision(
                normalized=normalized,
                policy_hash=validation.policy_hash,
                clean=False,
                decision="deny",
                reason_code="disabled_binding",
                issues=[f"script binding {binding_id!r} remains disabled in MVP."],
                matched_binding_id=binding_id,
            )

        binding_id = operation.get("cmdlet_id")
        if not isinstance(binding_id, str):
            return _decision(
                normalized=normalized,
                policy_hash=validation.policy_hash,
                clean=False,
                decision="deny",
                reason_code="unknown_binding",
                issues=["powershell_cmdlet is missing cmdlet_id."],
            )

        binding = resolved_policy["cmdlet_catalog"].get(binding_id)
        if type(binding) is not dict:
            return _decision(
                normalized=normalized,
                policy_hash=validation.policy_hash,
                clean=False,
                decision="deny",
                reason_code="unknown_binding",
                issues=[f"cmdlet binding {binding_id!r} is not present in policy."],
            )
        if binding.get("enabled") is not True:
            return _decision(
                normalized=normalized,
                policy_hash=validation.policy_hash,
                clean=False,
                decision="deny",
                reason_code="disabled_binding",
                issues=[f"cmdlet binding {binding_id!r} is disabled."],
                matched_binding_id=binding_id,
            )
        if binding.get("operation_type") != "powershell_cmdlet":
            return _decision(
                normalized=normalized,
                policy_hash=validation.policy_hash,
                clean=False,
                decision="deny",
                reason_code="unsupported_operation_type",
                issues=[f"binding {binding_id!r} does not match operation_type powershell_cmdlet."],
                matched_binding_id=binding_id,
            )

        allowed_parameters = binding.get("allowed_parameters", {})
        if type(allowed_parameters) is not dict:
            return _decision(
                normalized=normalized,
                policy_hash=validation.policy_hash,
                clean=False,
                decision="deny",
                reason_code="policy_invalid",
                issues=[f"binding {binding_id!r} has invalid allowed_parameters."],
                matched_binding_id=binding_id,
            )

        for name, payload in parameter_map.items():
            if name not in allowed_parameters:
                return _decision(
                    normalized=normalized,
                    policy_hash=validation.policy_hash,
                    clean=False,
                    decision="deny",
                    reason_code="unknown_parameter",
                    issues=[f"parameter {name!r} is not allowed for {binding_id!r}."],
                    matched_binding_id=binding_id,
                )
            rule = allowed_parameters[name]
            expected_value_type = rule.get("value_type")
            actual_value_type = payload.get("value_type")
            if expected_value_type != actual_value_type:
                return _decision(
                    normalized=normalized,
                    policy_hash=validation.policy_hash,
                    clean=False,
                    decision="deny",
                    reason_code="unknown_parameter",
                    issues=[
                        f"parameter {name!r} expects value_type {expected_value_type!r}, "
                        f"received {actual_value_type!r}."
                    ],
                    matched_binding_id=binding_id,
                )
            if actual_value_type == "path_ref":
                path_ref_id = payload.get("path_ref")
                if not isinstance(path_ref_id, str) or path_ref_id not in path_refs_by_id:
                    return _decision(
                        normalized=normalized,
                        policy_hash=validation.policy_hash,
                        clean=False,
                        decision="deny",
                        reason_code="unknown_path_ref",
                        issues=[f"unknown path_ref {path_ref_id!r}."],
                        matched_binding_id=binding_id,
                    )
                path_ref = path_refs_by_id[path_ref_id]
                root_id = path_ref.get("root_id")
                allowed_roots = binding.get("allowed_roots", [])
                if not isinstance(root_id, str) or root_id not in allowed_roots:
                    return _decision(
                        normalized=normalized,
                        policy_hash=validation.policy_hash,
                        clean=False,
                        decision="deny",
                        reason_code="root_not_allowed",
                        issues=[f"root {root_id!r} is not allowed for binding {binding_id!r}."],
                        matched_binding_id=binding_id,
                    )

        for required_name, rule in allowed_parameters.items():
            if rule.get("required") is True and required_name not in parameter_map:
                return _decision(
                    normalized=normalized,
                    policy_hash=validation.policy_hash,
                    clean=False,
                    decision="deny",
                    reason_code="unknown_parameter",
                    issues=[f"required parameter {required_name!r} is missing."],
                    matched_binding_id=binding_id,
                )

        if binding.get("network_allowed") is True:
            return _decision(
                normalized=normalized,
                policy_hash=validation.policy_hash,
                clean=False,
                decision="deny",
                reason_code="network_denied_mvp",
                issues=[f"binding {binding_id!r} requests network capability, denied in MVP."],
                matched_binding_id=binding_id,
            )
        if binding.get("privilege_escalation_allowed") is True:
            return _decision(
                normalized=normalized,
                policy_hash=validation.policy_hash,
                clean=False,
                decision="deny",
                reason_code="privilege_denied_mvp",
                issues=[f"binding {binding_id!r} requests privilege escalation, denied in MVP."],
                matched_binding_id=binding_id,
            )

        resolved_reads, read_reason, read_issues = _resolve_declared_paths(
            binding_id=binding_id,
            declaration=binding.get("declared_reads", []),
            parameter_map=parameter_map,
            path_refs_by_id=path_refs_by_id,
        )
        if read_reason is not None:
            return _decision(
                normalized=normalized,
                policy_hash=validation.policy_hash,
                clean=False,
                decision="deny",
                reason_code=read_reason,
                issues=read_issues,
                matched_binding_id=binding_id,
            )
        resolved_writes, write_reason, write_issues = _resolve_declared_paths(
            binding_id=binding_id,
            declaration=binding.get("declared_writes", []),
            parameter_map=parameter_map,
            path_refs_by_id=path_refs_by_id,
        )
        if write_reason is not None:
            return _decision(
                normalized=normalized,
                policy_hash=validation.policy_hash,
                clean=False,
                decision="deny",
                reason_code=write_reason,
                issues=write_issues,
                matched_binding_id=binding_id,
            )

        declared_reads.extend(resolved_reads)
        declared_writes.extend(resolved_writes)
        matched_bindings.append(
            {
                "binding_id": binding_id,
                "binding": binding,
                "operation": operation,
                "parameter_map": parameter_map,
            }
        )

    risk_report: RiskReport = derive_effective_risk(
        normalized,
        {
            "policy": resolved_policy,
            "bindings": matched_bindings,
        },
    )

    if risk_report.confirmation_required:
        return _decision(
            normalized=normalized,
            policy_hash=validation.policy_hash,
            clean=True,
            decision="require_confirmation",
            reason_code="risk_requires_confirmation",
            issues=list(risk_report.risk_factors),
            matched_binding_id=matched_bindings[-1]["binding_id"] if matched_bindings else None,
            effective_risk=risk_report.effective_risk,
            confirmation_required=True,
            confirmation_mode=risk_report.confirmation_mode,
            declared_reads=declared_reads,
            declared_writes=declared_writes,
            network_allowed=False,
            privilege_escalation_allowed=False,
        )

    return _decision(
        normalized=normalized,
        policy_hash=validation.policy_hash,
        clean=True,
        decision="allow",
        reason_code="allowed",
        issues=list(risk_report.risk_factors),
        matched_binding_id=matched_bindings[-1]["binding_id"] if matched_bindings else None,
        effective_risk=risk_report.effective_risk,
        confirmation_required=False,
        confirmation_mode=risk_report.confirmation_mode,
        declared_reads=declared_reads,
        declared_writes=declared_writes,
        network_allowed=False,
        privilege_escalation_allowed=False,
    )


def require_policy_allowed(
    normalized: NormalizedProposal,
    policy: dict | None = None,
) -> PolicyDecision:
    """Return an allow decision or raise PolicyDeniedError."""

    decision = evaluate_policy(normalized, policy=policy)
    if decision.decision == "allow":
        return decision

    issue_text = "; ".join(decision.issues) if decision.issues else decision.reason_code
    raise PolicyDeniedError(
        f"Governed shell policy denied proposal {normalized.proposal_hash}: "
        f"{decision.reason_code}: {issue_text}"
    )
