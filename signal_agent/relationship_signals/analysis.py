from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from signal_agent.evidence_sources.canonical import sha256_file


TOPIC_CLUSTER_SCHEMA_VERSION = "signal_agent.relationship_topic_cluster.v1"


class RelationshipAnalysisError(RuntimeError):
    pass


def _normalized_text(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    text = re.sub(r"[\u2010-\u2015]", "-", text)
    return " ".join(text.split())


def _phrase_present(text: str, phrase: str) -> bool:
    # Hyphens are meaningful in the bounded taxonomy; punctuation at the phrase
    # edges is not. This prevents substrings such as "content" in "discontent".
    pattern = rf"(?<![\w-]){re.escape(phrase)}(?![\w-])"
    return re.search(pattern, text) is not None


def load_taxonomy(path: str | Path) -> tuple[dict[str, Any], str]:
    taxonomy_path = Path(path).resolve(strict=True)
    try:
        taxonomy = json.loads(taxonomy_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RelationshipAnalysisError("relationship_taxonomy_unreadable") from exc
    if (
        not isinstance(taxonomy, dict)
        or taxonomy.get("taxonomy_id") != "governed_systems_v1"
        or not isinstance(taxonomy.get("clusters"), list)
        or len(taxonomy["clusters"]) != 1
    ):
        raise RelationshipAnalysisError("relationship_taxonomy_invalid")
    return taxonomy, sha256_file(taxonomy_path)


def analyze_relationship_topics(
    records: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    taxonomy: dict[str, Any],
    taxonomy_sha256: str,
) -> dict[str, Any]:
    cluster_rule = taxonomy["clusters"][0]
    deterministic_matches: list[dict[str, Any]] = []
    ambiguous_matches: list[dict[str, Any]] = []
    matched_record_ids: set[str] = set()
    matched_groups: set[str] = set()

    for record in records:
        record_id = record["relationship_record_id"]
        evidence_ref = record["source_provenance"]["evidence_ref"]
        fields = record.get("professional_context", {})
        record_had_direct_match = False
        for field in ("company", "position"):
            text = _normalized_text(fields.get(field))
            if not text:
                continue
            for group in cluster_rule["rule_groups"]:
                group_name = group["rule_group"]
                for term in group["terms"]:
                    normalized_term = _normalized_text(term)
                    if _phrase_present(text, normalized_term):
                        deterministic_matches.append(
                            {
                                "rule_id": f"{taxonomy['taxonomy_id']}.{group_name}.{normalized_term.replace(' ', '_')}",
                                "rule_group": group_name,
                                "field": field,
                                "matched_term": normalized_term,
                                "relationship_record_id": record_id,
                                "evidence_ref": evidence_ref,
                                "classification_method": "deterministic_exact_phrase",
                            }
                        )
                        record_had_direct_match = True
                        matched_groups.add(group_name)
            if not record_had_direct_match:
                generic_hits = sorted(
                    {
                        term
                        for term in taxonomy.get("ambiguous_generic_terms", [])
                        if _phrase_present(text, _normalized_text(term))
                    }
                )
                for term in generic_hits:
                    ambiguous_matches.append(
                        {
                            "field": field,
                            "matched_term": term,
                            "relationship_record_id": record_id,
                            "evidence_ref": evidence_ref,
                            "classification_state": "ambiguous_not_counted",
                        }
                    )
        if record_had_direct_match:
            matched_record_ids.add(record_id)

    deterministic_matches.sort(
        key=lambda item: (
            item["relationship_record_id"],
            item["rule_group"],
            item["field"],
            item["matched_term"],
        )
    )
    ambiguous_matches.sort(
        key=lambda item: (item["relationship_record_id"], item["field"], item["matched_term"])
    )
    supporting_count = len(matched_record_ids)
    group_count = len(matched_groups)
    if supporting_count >= 4 and group_count == 4:
        confidence = "high"
    elif supporting_count >= 2 and group_count >= 2:
        confidence = "moderate"
    elif supporting_count >= 2 and group_count == 1:
        confidence = "low"
    else:
        confidence = "insufficient"

    inference_evidence = sorted(
        {item["evidence_ref"] for item in deterministic_matches}
    )
    inferred_cluster = {
        "cluster_id": cluster_rule["cluster_id"],
        "label": cluster_rule["label"],
        "confidence_state": confidence,
        "supporting_record_count": supporting_count,
        "supporting_record_ids": sorted(matched_record_ids),
        "rule_groups": sorted(matched_groups),
        "evidence_refs": inference_evidence,
        "inference_method": "bounded_aggregate_thresholds",
        "inference_basis": {
            "high": "at_least_four_records_spanning_all_four_groups",
            "moderate": "at_least_two_records_spanning_at_least_two_groups",
            "low": "at_least_two_records_from_one_group",
            "insufficient": "fewer_than_two_supporting_records",
        }[confidence],
    }
    return {
        "schema_version": TOPIC_CLUSTER_SCHEMA_VERSION,
        "analysis_status": "insufficient" if confidence == "insufficient" else "classified",
        "taxonomy": {
            "taxonomy_id": taxonomy["taxonomy_id"],
            "taxonomy_version": taxonomy["taxonomy_version"],
            "file_sha256": f"sha256:{taxonomy_sha256}",
        },
        "analysis_method": "normalized_exact_phrase_rules_then_aggregate_inference",
        "deterministic_matches": deterministic_matches,
        "ambiguous_matches": ambiguous_matches,
        "unclassified_record_ids": sorted(
            record["relationship_record_id"]
            for record in records
            if record["relationship_record_id"] not in matched_record_ids
        ),
        "inferred_cluster": inferred_cluster,
        "matching_policy": {
            "fields": ["company", "position"],
            "generic_terms_count_toward_support": False,
            "rules_broadened_for_support": False,
        },
    }


@dataclass(frozen=True)
class GovernedSystemsRelationshipAnalyzer:
    """Concrete analyzer for the checked-in governed-systems taxonomy."""

    taxonomy_path: Path

    def analyze(self, records: tuple[dict[str, Any], ...]) -> dict[str, Any]:
        taxonomy, taxonomy_sha256 = load_taxonomy(self.taxonomy_path)
        return analyze_relationship_topics(
            records,
            taxonomy=taxonomy,
            taxonomy_sha256=taxonomy_sha256,
        )
