from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from signal_agent.evidence_sources.canonical import canonical_json_bytes
from signal_agent.transport.schemas import derive_id

from .artifacts import (
    artifact_descriptor,
    build_reconciliation_manifest,
    prepare_empty_root,
    promote_artifacts,
    seal,
    write_exclusive_json,
)
from .errors import IdentityEvidenceError
from .inputs import VerifiedSourceRun, load_verified_source_run
from .models import CandidateGenerationResult, Clock
from .policy import (
    NORMALIZATION_RULE_ID,
    IdentityComparisonPolicy,
    load_identity_comparison_policy,
    normalize_comparison_value,
)


LINKEDIN_SOURCE_TYPE = "linkedin_connections_csv"
INTERACTION_SOURCE_TYPE = "interaction_event_export.v1"
EVIDENCE_BUNDLE_SCHEMA_VERSION = "signal_agent.identity_evidence_bundle.v1"
CANDIDATE_SCHEMA_VERSION = "signal_agent.identity_candidate.v1"
SOURCE_REFERENCES_SCHEMA_VERSION = "signal_agent.identity_source_run_references.v1"


def _offset_aware_rfc3339(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _identifier(record: dict[str, Any], kind: str) -> dict[str, Any]:
    values = [item for item in record.get("identifiers", []) if item.get("kind") == kind]
    if len(values) != 1:
        raise IdentityEvidenceError(f"identity_record_identifier_invalid:{kind}")
    return values[0]


def _identity_reference(
    run: VerifiedSourceRun,
    *,
    source_local_identity_reference_id: str,
    records: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    ordered = sorted(records, key=lambda item: item["relationship_record_id"])
    reference = run.reference()
    reference.pop("unresolved_artifact")
    reference.update(
        {
            "source_local_identity_reference_id": source_local_identity_reference_id,
            "relationship_record_ids": [item["relationship_record_id"] for item in ordered],
            "evidence_refs": sorted(
                item["source_provenance"]["evidence_ref"] for item in ordered
            ),
        }
    )
    return reference


def _linkedin_reference(run: VerifiedSourceRun, record: dict[str, Any]) -> dict[str, Any]:
    local_id = derive_id(
        "sli",
        LINKEDIN_SOURCE_TYPE,
        run.source_receipt_id,
        record["relationship_record_id"],
        length=20,
    )
    return _identity_reference(
        run,
        source_local_identity_reference_id=local_id,
        records=(record,),
    )


def _interaction_groups(
    run: VerifiedSourceRun,
) -> tuple[tuple[str, tuple[dict[str, Any], ...], dict[str, Any]], ...]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in run.records:
        actor = _identifier(record, "actor_id_hmac")
        protection = actor.get("protection") or {}
        key = (
            str(actor.get("value") or ""),
            str(actor.get("key_id") or ""),
            str(actor.get("algorithm") or protection.get("algorithm") or ""),
            str(
                actor.get("version")
                or actor.get("token_version")
                or protection.get("version")
                or ""
            ),
        )
        if not all(key):
            raise IdentityEvidenceError("interaction_actor_protection_descriptor_incomplete")
        grouped[key].append(record)
    result: list[tuple[str, tuple[dict[str, Any], ...], dict[str, Any]]] = []
    for key, records in grouped.items():
        ordered = tuple(sorted(records, key=lambda item: item["relationship_record_id"]))
        local_id = derive_id(
            "sli",
            INTERACTION_SOURCE_TYPE,
            run.source_receipt_id,
            *key,
            length=20,
        )
        result.append(
            (
                local_id,
                ordered,
                _identity_reference(
                    run,
                    source_local_identity_reference_id=local_id,
                    records=ordered,
                ),
            )
        )
    return tuple(sorted(result, key=lambda item: item[0]))


def _sanitized_conflicts(
    run: VerifiedSourceRun,
    record_ids: set[str],
) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    for group in run.unresolved_matches.get("candidate_groups", []):
        group_ids = set(group.get("relationship_record_ids") or [])
        conflicting_fields = group.get("conflicting_fields") or []
        if not record_ids.intersection(group_ids) or not conflicting_fields:
            continue
        conflicts.append(
            {
                "candidate_group_id": group["candidate_group_id"],
                "source_type": run.source_type,
                "match_basis": group["match_basis"],
                "conflicting_fields": sorted(str(item) for item in conflicting_fields),
                "relationship_record_ids": sorted(group_ids),
                "evidence_refs": sorted(group.get("evidence_refs") or []),
                "automatic_merge_performed": False,
                "canonical_identity_selected": False,
            }
        )
    return sorted(
        conflicts,
        key=lambda item: (item["source_type"], item["candidate_group_id"]),
    )


def _signal(
    *,
    signal_type: str,
    left_field_path: str,
    right_field_path: str,
    representation: str,
    left_record: dict[str, Any],
    right_record: dict[str, Any],
) -> dict[str, Any]:
    return {
        "signal_type": signal_type,
        "evidence_class": "B_strong_supporting_evidence",
        "left_field_path": left_field_path,
        "right_field_path": right_field_path,
        "normalization_rule_id": NORMALIZATION_RULE_ID,
        "match_representation": representation,
        "outcome": "exact_match",
        "left_relationship_record_ids": [left_record["relationship_record_id"]],
        "right_relationship_record_ids": [right_record["relationship_record_id"]],
        "left_evidence_refs": [left_record["source_provenance"]["evidence_ref"]],
        "right_evidence_refs": [right_record["source_provenance"]["evidence_ref"]],
    }


def _matching_occurrences(
    left: dict[str, Any],
    right_records: tuple[dict[str, Any], ...],
) -> list[tuple[dict[str, Any], str, str]]:
    person = left.get("person") or {}
    professional = left.get("professional_context") or {}
    display = normalize_comparison_value(person.get("display_name"))
    first_last = normalize_comparison_value(
        " ".join(
            value
            for value in (str(person.get("first_name") or ""), str(person.get("last_name") or ""))
            if value
        )
    )
    company = normalize_comparison_value(professional.get("company"))
    position = normalize_comparison_value(professional.get("position"))
    if not company or not position or (not display and not first_last):
        return []
    matches: list[tuple[dict[str, Any], str, str]] = []
    for right in right_records:
        right_name = normalize_comparison_value((right.get("person") or {}).get("display_name"))
        right_professional = right.get("professional_context") or {}
        right_company = normalize_comparison_value(right_professional.get("company"))
        right_position = normalize_comparison_value(right_professional.get("position"))
        if not right_name or not right_company or not right_position:
            continue
        if company != right_company or position != right_position:
            continue
        if display and display == right_name:
            matches.append((right, "display_name_exact", "person.display_name"))
        elif first_last and first_last == right_name:
            matches.append(
                (right, "first_last_to_display_name_exact", "person.first_name+person.last_name")
            )
    return matches


def _protection_compatibility(
    linkedin: VerifiedSourceRun,
    interaction: VerifiedSourceRun,
) -> dict[str, Any]:
    return {
        "comparable": False,
        "classification": "E_non_comparable_evidence",
        "reason_codes": [
            "input_semantic_type_mismatch",
            "canonicalization_mismatch",
            "protection_namespace_mismatch",
            "key_id_mismatch",
            "key_material_domain_unverified",
            "token_version_mismatch",
        ],
        "left_domain": {
            "input_semantic_type": "canonical_email",
            "canonicalization_id": "linkedin_email_nfkc_trim_casefold.v1",
            "protection_namespace": "linkedin_email",
            "algorithm": linkedin.identifier_protection["algorithm"],
            "key_id": linkedin.identifier_protection["key_id"],
            "token_version": linkedin.identifier_protection["version"],
            "shared_key_material_verifier_available": False,
        },
        "right_domain": {
            "input_semantic_type": "opaque_actor_id",
            "canonicalization_id": "interaction_event_actor_utf8_exact.v1",
            "protection_namespace": "interaction_event_actor",
            "algorithm": interaction.identifier_protection["algorithm"],
            "key_id": interaction.identifier_protection["key_id"],
            "token_version": interaction.identifier_protection["version"],
            "shared_key_material_verifier_available": False,
        },
        "verified_key_material_domain": False,
        "token_values_compared": False,
    }


def _candidate_artifacts(
    *,
    linkedin: VerifiedSourceRun,
    interaction: VerifiedSourceRun,
    policy: IdentityComparisonPolicy,
    generated_at: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    interaction_groups = _interaction_groups(interaction)
    name_index: dict[str, list[tuple[str, tuple[dict[str, Any], ...], dict[str, Any]]]] = defaultdict(list)
    for group in interaction_groups:
        names = {
            normalize_comparison_value((record.get("person") or {}).get("display_name"))
            for record in group[1]
        }
        for name in sorted(item for item in names if item):
            name_index[name].append(group)

    bundles: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    evaluated_pairs: set[tuple[str, str]] = set()
    indexed_pair_count = 0
    missing_input_count = 0
    weak_pair_count = 0
    for left in sorted(linkedin.records, key=lambda item: item["relationship_record_id"]):
        person = left.get("person") or {}
        professional = left.get("professional_context") or {}
        display = normalize_comparison_value(person.get("display_name"))
        first_last = normalize_comparison_value(
            " ".join(
                value
                for value in (
                    str(person.get("first_name") or ""),
                    str(person.get("last_name") or ""),
                )
                if value
            )
        )
        if not normalize_comparison_value(professional.get("company")) or not normalize_comparison_value(
            professional.get("position")
        ) or (not display and not first_last):
            missing_input_count += 1
            continue
        possible: dict[str, tuple[str, tuple[dict[str, Any], ...], dict[str, Any]]] = {}
        for name in {display, first_last}:
            if not name:
                continue
            for group in name_index.get(name, []):
                possible[group[0]] = group
        for local_id, right_records, right_reference in sorted(possible.values(), key=lambda item: item[0]):
            pair_key = (left["relationship_record_id"], local_id)
            if pair_key in evaluated_pairs:
                continue
            evaluated_pairs.add(pair_key)
            indexed_pair_count += 1
            matches = _matching_occurrences(left, right_records)
            if not matches:
                weak_pair_count += 1
                continue
            left_reference = _linkedin_reference(linkedin, left)
            conflict_evidence = _sanitized_conflicts(
                linkedin, {left["relationship_record_id"]}
            ) + _sanitized_conflicts(
                interaction, {item["relationship_record_id"] for item in right_records}
            )
            comparison_signals: list[dict[str, Any]] = []
            for right, representation, left_name_field in matches:
                comparison_signals.extend(
                    [
                        _signal(
                            signal_type="name_exact",
                            left_field_path=left_name_field,
                            right_field_path="person.display_name",
                            representation=representation,
                            left_record=left,
                            right_record=right,
                        ),
                        _signal(
                            signal_type="organization_exact",
                            left_field_path="professional_context.company",
                            right_field_path="professional_context.company",
                            representation="organization_exact",
                            left_record=left,
                            right_record=right,
                        ),
                        _signal(
                            signal_type="position_exact",
                            left_field_path="professional_context.position",
                            right_field_path="professional_context.position",
                            representation="position_exact",
                            left_record=left,
                            right_record=right,
                        ),
                    ]
                )
            comparison_signals.sort(
                key=lambda item: (
                    item["right_relationship_record_ids"],
                    item["signal_type"],
                    item["match_representation"],
                )
            )
            bundle_id = derive_id(
                "ieb",
                policy.file_sha256,
                linkedin.run_id,
                interaction.run_id,
                left_reference["source_local_identity_reference_id"],
                right_reference["source_local_identity_reference_id"],
                length=20,
            )
            bundle = seal(
                {
                    "schema_version": EVIDENCE_BUNDLE_SCHEMA_VERSION,
                    "evidence_bundle_id": bundle_id,
                    "generated_at": generated_at,
                    "comparison_policy": policy.descriptor(),
                    "left_identity_reference": deepcopy(left_reference),
                    "right_identity_reference": deepcopy(right_reference),
                    "comparison_signals": comparison_signals,
                    "conflict_evidence": conflict_evidence,
                    "missing_evidence": [],
                    "protection_compatibility": _protection_compatibility(
                        linkedin, interaction
                    ),
                    "prohibited_comparison_classes": sorted(policy.payload["prohibited_inputs"]),
                    "privacy": {
                        "clear_identifiers_read": False,
                        "clear_identifiers_serialized": False,
                        "protected_token_values_serialized": False,
                        "compared_attribute_values_serialized": False,
                        "reversible_value_digests_serialized": False,
                        "raw_interaction_text_read": False,
                    },
                },
                "bundle_hash",
            )
            status = "conflicting" if conflict_evidence else "proposed"
            candidate_id = derive_id(
                "idc",
                policy.file_sha256,
                linkedin.run_id,
                interaction.run_id,
                left_reference["source_local_identity_reference_id"],
                right_reference["source_local_identity_reference_id"],
                bundle_id,
                length=20,
            )
            candidate = seal(
                {
                    "schema_version": CANDIDATE_SCHEMA_VERSION,
                    "candidate_id": candidate_id,
                    "generated_at": generated_at,
                    "status": status,
                    "candidate_classification": (
                        "conflicting_attribute_candidate"
                        if status == "conflicting"
                        else "strong_attribute_candidate"
                    ),
                    "left_identity_reference": deepcopy(left_reference),
                    "right_identity_reference": deepcopy(right_reference),
                    "evidence_bundle": {
                        "evidence_bundle_id": bundle_id,
                        "path": f"01_evidence/{bundle_id}.json",
                        "bundle_hash": bundle["bundle_hash"],
                    },
                    "comparison_policy": policy.descriptor(),
                    "rationale_codes": sorted(
                        ["exact_attribute_triad_satisfied"]
                        + (
                            ["source_local_conflict_requires_review"]
                            if conflict_evidence
                            else []
                        )
                    ),
                    "conflict_evidence_count": len(conflict_evidence),
                    "missing_evidence_count": 0,
                    "human_review_required": True,
                    "automatic_merge_performed": False,
                    "projection_authorized": False,
                    "privacy": deepcopy(bundle["privacy"]),
                },
                "candidate_hash",
            )
            bundles.append(bundle)
            candidates.append(candidate)
    bundles.sort(key=lambda item: item["evidence_bundle_id"])
    candidates.sort(key=lambda item: item["candidate_id"])
    counts = {
        "linkedin_identity_reference_count": len(linkedin.records),
        "interaction_identity_reference_count": len(interaction_groups),
        "indexed_pair_count": indexed_pair_count,
        "weak_or_incomplete_pair_count": weak_pair_count + missing_input_count,
        "candidate_count": len(candidates),
        "proposed_candidate_count": sum(item["status"] == "proposed" for item in candidates),
        "conflicting_candidate_count": sum(
            item["status"] == "conflicting" for item in candidates
        ),
    }
    return bundles, candidates, counts


def generate_identity_candidates(
    linkedin_run_root: str | Path,
    interaction_event_run_root: str | Path,
    output_root: str | Path,
    policy_path: str | Path,
    clock: Clock,
) -> CandidateGenerationResult:
    policy = load_identity_comparison_policy(policy_path)
    linkedin = load_verified_source_run(
        linkedin_run_root, expected_source_type=LINKEDIN_SOURCE_TYPE
    )
    interaction = load_verified_source_run(
        interaction_event_run_root, expected_source_type=INTERACTION_SOURCE_TYPE
    )
    generated_at = clock()
    if not _offset_aware_rfc3339(generated_at):
        raise IdentityEvidenceError(
            "identity_candidate_generation_timestamp_offset_required"
        )
    root = prepare_empty_root(output_root)
    bundles, candidates, counts = _candidate_artifacts(
        linkedin=linkedin,
        interaction=interaction,
        policy=policy,
        generated_at=generated_at,
    )
    source_references = {
        "schema_version": SOURCE_REFERENCES_SCHEMA_VERSION,
        "comparison_policy": policy.descriptor(),
        "source_runs": [linkedin.reference(), interaction.reference()],
        "comparison_summary": counts,
        "privacy": {
            "preserved_sources_read": False,
            "clear_identifiers_read": False,
            "source_records_mutated": False,
        },
    }
    persisted: list[tuple[str, bytes]] = [
        ("00_inputs/source_run_references.json", canonical_json_bytes(source_references))
    ]
    for bundle in bundles:
        persisted.append(
            (
                f"01_evidence/{bundle['evidence_bundle_id']}.json",
                canonical_json_bytes(bundle),
            )
        )
    for candidate in candidates:
        persisted.append(
            (
                f"02_candidates/{candidate['candidate_id']}.json",
                canonical_json_bytes(candidate),
            )
        )
    descriptors = [
        artifact_descriptor(
            path,
            payload,
            schema_version=(
                SOURCE_REFERENCES_SCHEMA_VERSION
                if path.startswith("00_inputs/")
                else EVIDENCE_BUNDLE_SCHEMA_VERSION
                if path.startswith("01_evidence/")
                else CANDIDATE_SCHEMA_VERSION
            ),
        )
        for path, payload in persisted
    ]
    manifest = build_reconciliation_manifest(
        operation="candidate_generation",
        created_at=generated_at,
        identity_parts=(
            policy.file_sha256,
            linkedin.run_id,
            linkedin.manifest_hash,
            interaction.run_id,
            interaction.manifest_hash,
        ),
        inputs={
            "comparison_policy": policy.descriptor(),
            "source_runs": [linkedin.reference(), interaction.reference()],
        },
        artifacts=descriptors,
        counts=counts,
    )
    promote_artifacts(root, persisted)
    manifest_path = write_exclusive_json(
        root / "05_receipts" / "candidate_generation_manifest.json", manifest
    )
    candidate_paths = tuple(
        root / f"02_candidates/{item['candidate_id']}.json" for item in candidates
    )
    bundle_paths = tuple(
        root / f"01_evidence/{item['evidence_bundle_id']}.json" for item in bundles
    )
    return CandidateGenerationResult(
        success=True,
        run_root=root,
        run_id=manifest["manifest_id"],
        candidate_count=counts["candidate_count"],
        proposed_count=counts["proposed_candidate_count"],
        conflicting_count=counts["conflicting_candidate_count"],
        candidate_paths=candidate_paths,
        evidence_bundle_paths=bundle_paths,
        manifest_path=manifest_path,
    )
