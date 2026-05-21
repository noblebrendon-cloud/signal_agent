"""
Spine Router — deterministic routing of promoted bundles into spine lanes.

Routes bundles by keyword + domain scoring against YAML config.
Copies (not moves) bundles into constraints/spines/<name>/incoming/.
Computes SHA256 of config for auditability.
Logs events to routing_log.jsonl.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.utils.io_contract import append_jsonl_atomic
from shared.contract import ContractResolutionError


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _get_root() -> Path:
    override = os.environ.get("SIGNAL_AGENT_ROOT")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[3]


def _get_capture_dir() -> Path:
    override = os.environ.get("CAPTURE_DIR")
    if override:
        return Path(override)
    return _get_root() / "data" / "capture"


def _canonical_state_paths(capture_dir: Path) -> tuple[Path, Path]:
    capture_root = capture_dir.resolve()
    if capture_root.name == "capture" and capture_root.parent.name == "data":
        repo_root = capture_root.parent.parent
    else:
        repo_root = capture_root.parent
    state_root = repo_root / "data" / "state"
    return (
        state_root / "artifact_registry.jsonl",
        state_root / "transition_gate_events.jsonl",
    )


def _now_utc() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _resolve_contract(
    bundle_path: Path,
    bundle_text: str,
    capture_dir: Path,
) -> Dict[str, Any]:
    """
    Narrow wrapper around shared.contract.resolve_bundle_contract.

    On ContractResolutionError, returns a structured failure dict and writes
    a minimal audit entry to routing_log.jsonl so the failure is traceable.

    Returns:
        contract dict on success: {lifecycle_state, contract_source, routable, confidence}
        failure dict on exception: {"_failed": True, "error": str, "contract_source": "unresolvable"}
    """
    try:
        from shared.contract import resolve_bundle_contract
        return resolve_bundle_contract(bundle_path, bundle_text)
    except ContractResolutionError as exc:
        err_str = str(exc)
        _append_routing_log(capture_dir, {
            "timestamp_utc": _now_utc(),
            "bundle_filename": bundle_path.name,
            "spine": None,
            "score": None,
            "rationale": {},
            "router_ruleset_hash": None,
            "contract_source": "unresolvable",
            "confidence": None,
            "status": "fail",
            "error": err_str,
        })
        return {"_failed": True, "error": err_str, "contract_source": "unresolvable"}
    except Exception as exc:
        err_str = f"contract resolver raised unexpected error: {exc}"
        _append_routing_log(capture_dir, {
            "timestamp_utc": _now_utc(),
            "bundle_filename": bundle_path.name,
            "spine": None,
            "score": None,
            "rationale": {},
            "router_ruleset_hash": None,
            "contract_source": "unresolvable",
            "confidence": None,
            "status": "fail",
            "error": err_str,
        })
        return {"_failed": True, "error": err_str, "contract_source": "unresolvable"}




def _parse_yaml_list(val: str) -> List[str]:
    """Parse YAML inline list: [a, b, c]."""
    val = val.strip()
    if val.startswith("[") and val.endswith("]"):
        inner = val[1:-1]
        if not inner.strip():
            return []
        items = [item.strip() for item in inner.split(",")]
        return [i for i in items if i]
    return []


def _parse_yaml_text_fallback(text: str) -> List[Dict[str, Any]]:
    """Minimal YAML parser for spine config text (no external deps)."""
    spines = []
    current: Optional[Dict[str, Any]] = None

    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
            
        if stripped.startswith("- name:"):
            if current:
                spines.append(current)
            name = stripped.split(":", 1)[1].strip()
            current = {"name": name, "keywords": [], "domains": []}
        elif stripped.startswith("keywords:") and current is not None:
            val = stripped.split(":", 1)[1].strip()
            current["keywords"] = _parse_yaml_list(val)
        elif stripped.startswith("domains:") and current is not None:
            val = stripped.split(":", 1)[1].strip()
            current["domains"] = _parse_yaml_list(val)

    if current:
        spines.append(current)
    return spines


def _load_spine_config(config_path: Optional[Path] = None) -> Tuple[List[Dict[str, Any]], str]:
    """
    Load spine definitions from YAML config.
    Returns (spines, config_hash).
    """
    if config_path is None:
        config_path = _get_root() / "config" / "spine_router.yaml"
    
    if not config_path.exists():
        return [{"name": "misc", "keywords": [], "domains": []}], "missing"

    # Compute hash of raw content
    try:
        raw_content = config_path.read_bytes()
        config_hash = hashlib.sha256(raw_content).hexdigest()[:12]
        text_content = raw_content.decode("utf-8")
    except OSError:
        return [{"name": "misc", "keywords": [], "domains": []}], "error"

    # Use internal fallback parser (no PyYAML dependency)
    spines = _parse_yaml_text_fallback(text_content)
    
    if not spines:
        spines = [{"name": "misc", "keywords": [], "domains": []}]
        
    return spines, config_hash


def _extract_tokens(text: str) -> List[str]:
    return _TOKEN_RE.findall(text.lower())


def score_bundle(
    tokens: List[str],
    domains: List[str],
    spine: Dict[str, Any],
) -> Tuple[float, Dict[str, Any]]:
    """
    Score a bundle against a spine definition.
    score = 0.65 * keyword_hit_rate + 0.35 * domain_hit_rate
    """
    spine_keywords = set(spine.get("keywords", []))
    spine_domains = set(spine.get("domains", []))

    if spine_keywords:
        token_set = set(tokens)
        matched_keywords = sorted(spine_keywords & token_set)
        keyword_rate = len(matched_keywords) / len(spine_keywords)
    else:
        matched_keywords = []
        keyword_rate = 0.0

    if spine_domains:
        domain_set = set(domains)
        matched_domains = sorted(spine_domains & domain_set)
        domain_rate = len(matched_domains) / len(spine_domains)
    else:
        matched_domains = []
        domain_rate = 0.0

    score = 0.65 * keyword_rate + 0.35 * domain_rate

    rationale = {
        "top_keywords": matched_keywords[:10],
        "matched_domains": matched_domains[:10],
    }
    return score, rationale


def route_bundle(
    bundle_path: Path,
    bundle_text: Optional[str] = None,
    dry_run: bool = False,
    config_path: Optional[Path] = None,
    capture_dir: Optional[Path] = None,
    spines_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Route a single bundle into the appropriate spine.

    Contract resolution is performed before scoring. Bundles that cannot
    establish a lifecycle contract are returned as structured failures without
    crashing; the failure is also written to routing_log.jsonl.
    """
    base = capture_dir or _get_capture_dir()
    root = base.resolve().parent.parent if base.name == "capture" and base.parent.name == "data" else base.resolve().parent
    registry_path, transition_ledger_path = _canonical_state_paths(base)

    if bundle_text is None:
        if not bundle_path.exists():
            from shared.result_schemas import make_route_result
            return make_route_result(
                status="fail",
                error=f"bundle not found: {bundle_path}",
                contract_source="unresolvable",
                confidence=None,
                details={}
            )
        bundle_text = bundle_path.read_text(encoding="utf-8", errors="replace")

    # -------------------------------------------------------------------------
    # Contract resolution (registry-first, with stale-file guard)
    # -------------------------------------------------------------------------
    contract = _resolve_contract(bundle_path, bundle_text, base)
    if contract.get("_failed"):
        from shared.result_schemas import make_route_result
        return make_route_result(
            status="fail",
            error=contract["error"],
            contract_source="unresolvable",
            confidence=None,
            details={}
        )

    contract_source = contract.get("contract_source", "unknown")
    confidence = contract.get("confidence")
    routable = bool(contract.get("routable", False))

    if not routable:
        error = (
            f"bundle '{bundle_path.name}' resolved only via non-authoritative contract source "
            f"'{contract_source}' and cannot be routed until registry or frontmatter evidence exists"
        )
        log_entry = {
            "timestamp_utc": _now_utc(),
            "bundle_filename": bundle_path.name,
            "spine": None,
            "score": None,
            "rationale": {},
            "router_ruleset_hash": None,
            "contract_source": contract_source,
            "confidence": confidence,
            "status": "fail",
            "error": error,
        }
        _append_routing_log(base, log_entry)

        from shared.result_schemas import make_route_result
        return make_route_result(
            status="fail",
            artifact_id=bundle_path.name,
            error=error,
            contract_source=contract_source,
            confidence=confidence,
            details={"lifecycle_state": contract.get("lifecycle_state")},
        )

    # Extract features
    tokens = _extract_tokens(bundle_text)

    # Extract domains
    import re as _re
    url_re = _re.compile(r"https?://[^\s\)>\]\"']+", _re.IGNORECASE)
    urls = url_re.findall(bundle_text)
    domains = []
    for url in urls:
        try:
            rest = url.split("://", 1)[1] if "://" in url else url
            domain = rest.split("/")[0].split("?")[0].split("#")[0]
            domains.append(domain.lower())
        except (IndexError, ValueError):
            pass
    domains = sorted(set(domains))

    # Load spine config & hash
    spines, config_hash = _load_spine_config(config_path)

    # Score each spine
    scores: List[Tuple[float, str, Dict[str, Any]]] = []
    for spine in spines:
        s, rationale = score_bundle(tokens, domains, spine)
        scores.append((s, spine["name"], rationale))

    # Sort: highest score, then alphabetical name (stable tie-break)
    scores.sort(key=lambda x: (-x[0], x[1]))

    best_score, best_name, best_rationale = scores[0]

    # If best score < 0.12, route to misc
    if best_score < 0.12:
        best_name = "misc"
        best_rationale = {"top_keywords": [], "matched_domains": []}

    # Route
    target_dir = spines_dir or (root / "constraints" / "spines")
    incoming = target_dir / best_name / "incoming"
    incoming.mkdir(parents=True, exist_ok=True)

    status = "dry_run" if dry_run else "ok"
    error = None
    if not dry_run:
        dest = incoming / bundle_path.name

        from shared.artifact_identity import normalize_artifact_ref
        norm_ref = normalize_artifact_ref(bundle_path.name)
        artifact_id = norm_ref["artifact_id"]

        # --- AUTHORITY RULES LAYER ---
        from shared.authority import check_preconditions_for_routing
        preconditions = check_preconditions_for_routing(
            artifact_id=artifact_id,
            expected_state="promoted",
            target_state="routed",
            registry_path=registry_path,
        )
        authority_result = preconditions["authority"]
        coherence_result = preconditions.get("coherence") or {}

        if not authority_result["allowed"]:
            status = "fail"
            if authority_result["authoritative_source"] == "coherence_guard":
                error = f"coherence check failed: {authority_result['blocking_reason']}"
            else:
                error = f"blocked by authority rules: {authority_result['blocking_reason']}"

            if authority_result["authoritative_source"] == "coherence_guard":
                try:
                    from shared.events import emit_event
                    emit_event(
                        "CoherenceCheckFailed",
                        artifact_id,
                        {
                            "bundle_path": str(bundle_path),
                            "expected_state": "promoted",
                            "reason": coherence_result.get("reason"),
                            "registry_state": coherence_result.get("registry_state"),
                            "registry_path": coherence_result.get("registry_path"),
                            "filesystem_exists": coherence_result.get("filesystem_exists"),
                        },
                    )
                except Exception:
                    pass

            log_entry = {
                "timestamp_utc": _now_utc(),
                "bundle_filename": bundle_path.name,
                "spine": best_name,
                "score": round(best_score, 4),
                "rationale": best_rationale,
                "router_ruleset_hash": config_hash,
                "contract_source": contract_source,
                "confidence": confidence,
                "status": status,
                "error": error,
                "coherence_reason": coherence_result.get("reason"),
                "registry_state": coherence_result.get("registry_state"),
                "filesystem_exists": coherence_result.get("filesystem_exists"),
                "authoritative_source": authority_result.get("authoritative_source"),
            }
            _append_routing_log(base, log_entry)

            from shared.result_schemas import make_route_result
            return make_route_result(
                status=status,
                artifact_id=artifact_id,
                error=error,
                contract_source=contract_source,
                confidence=confidence,
                coherence=coherence_result,
                details={"authority": authority_result}
            )
        # -----------------------

        try:
            from shared.state_registry import record_state, get_state
            from app.hq.governance import validate_transition, emit_transition_event, new_run_id

            prior = get_state(artifact_id, registry_path=registry_path)
            prior_state = prior.get("state") if prior else None
            lane_id = best_name  # spine name as lane reference
            routing_run_id = new_run_id("route")
            validation = validate_transition(
                current_state=prior_state,
                next_state="routed",
                lane_id=lane_id,
                context={
                    "module": "app.hq.capture.router",
                    "operation": "route_bundle",
                    "artifact_id": artifact_id,
                    "bundle_filename": bundle_path.name,
                    "spine": best_name,
                    "router_ruleset_hash": config_hash,
                },
            )
            if not validation.get("allowed"):
                emit_transition_event(
                    validation,
                    run_id=routing_run_id,
                    artifact_id=artifact_id,
                    ledger_path=transition_ledger_path,
                    context={
                        "module": "app.hq.capture.router",
                        "operation": "route_bundle",
                        "artifact_id": artifact_id,
                        "bundle_filename": bundle_path.name,
                        "spine": best_name,
                        "router_ruleset_hash": config_hash,
                    },
                    event_type="transition_rejected",
                )
                current_label = prior_state if prior_state else "missing"
                raise RuntimeError(
                    f"Canonical gate rejected routing: "
                    f"{current_label}->routed: {validation.get('reason')}"
                )

            emit_transition_event(
                validation,
                run_id=routing_run_id,
                artifact_id=artifact_id,
                ledger_path=transition_ledger_path,
                context={
                    "module": "app.hq.capture.router",
                    "operation": "route_bundle",
                    "bundle_filename": bundle_path.name,
                    "spine": best_name,
                    "router_ruleset_hash": config_hash,
                },
                event_type="transition_attempt",
            )
            shutil.copy2(str(bundle_path), str(dest))
            record_state(
                artifact_id=artifact_id,
                state="routed",
                path=str(dest),
                registry_path=registry_path,
            )

            # emit RoutingSucceeded only after copy + record_state attempted
            try:
                from shared.events import emit_event
                emit_event(
                    "RoutingSucceeded",
                    artifact_id,
                    {
                        "bundle_path": str(dest),
                        "spine": best_name,
                        "score": round(best_score, 4),
                    },
                )
            except Exception:
                pass

        except Exception as e:
            status = "fail"
            error = str(e)
            if "dest" in locals():
                try:
                    if dest.exists():
                        dest.unlink()
                except OSError:
                    pass

    # Log (includes contract_source and confidence for auditability)
    log_entry = {
        "timestamp_utc": _now_utc(),
        "bundle_filename": bundle_path.name,
        "spine": best_name,
        "score": round(best_score, 4),
        "rationale": best_rationale,
        "router_ruleset_hash": config_hash,
        "contract_source": contract_source,
        "confidence": confidence,
        "status": status,
        "error": error,
    }
    _append_routing_log(base, log_entry)

    from shared.result_schemas import make_route_result
    return make_route_result(
        status=status,
        artifact_id=bundle_path.name,
        error=error,
        contract_source=contract_source,
        confidence=confidence,
        coherence=None,
        details={
            "bundle": bundle_path.name,
            "spine": best_name,
            "score": round(best_score, 4),
            "rationale": best_rationale,
            "router_ruleset_hash": config_hash,
        }
    )


def _append_routing_log(
    capture_dir: Path,
    entry: Dict[str, Any],
) -> None:
    log_path = capture_dir / "routing_log.jsonl"
    try:
        append_jsonl_atomic(log_path, dict(sorted(entry.items())))
    except Exception as exc:
        raise RuntimeError(f"Failed to append routing log to {log_path}") from exc


def main(argv: Optional[list] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="brn capture.route",
        description="Route a promoted bundle into a spine lane.",
    )
    parser.add_argument("--bundle", required=True, help="Path to bundle file")
    parser.add_argument("--dry-run", action="store_true", help="Preview without copying")

    args = parser.parse_args(argv)
    result = route_bundle(
        bundle_path=Path(args.bundle),
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
