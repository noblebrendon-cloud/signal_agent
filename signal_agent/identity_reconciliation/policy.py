from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from signal_agent.evidence_sources.canonical import sha256_file

from .errors import IdentityPolicyError


POLICY_SCHEMA_VERSION = "signal_agent.identity_comparison_policy.v1"
SUPPORTED_POLICY_ID = "linkedin_interaction_attribute_v1"
SUPPORTED_POLICY_VERSION = "1.0.0"
NORMALIZATION_RULE_ID = "nfkc_trim_collapse_whitespace_casefold.v1"
SUPPORTED_AUTHORITY_TYPE = "human_attestation"
SUPPORTED_ATTESTATION_VERSION = "identity_review_authority_attestation.v1"
SUPPORTED_REVIEWER_ROLE = "identity_reconciliation_reviewer"


@dataclass(frozen=True)
class IdentityComparisonPolicy:
    policy_id: str
    policy_version: str
    file_sha256: str
    payload: dict[str, Any]

    def descriptor(self) -> dict[str, str]:
        return {
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "file_sha256": f"sha256:{self.file_sha256}",
        }


def normalize_comparison_value(value: object) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).strip()
    return re.sub(r"\s+", " ", normalized).casefold()


def load_identity_comparison_policy(path: str | Path) -> IdentityComparisonPolicy:
    policy_path = Path(path).expanduser().resolve(strict=True)
    try:
        payload = json.loads(policy_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise IdentityPolicyError("identity_comparison_policy_unreadable") from exc
    if not isinstance(payload, dict):
        raise IdentityPolicyError("identity_comparison_policy_object_required")
    expected = {
        "schema_version": POLICY_SCHEMA_VERSION,
        "policy_id": SUPPORTED_POLICY_ID,
        "policy_version": SUPPORTED_POLICY_VERSION,
    }
    for field, value in expected.items():
        if payload.get(field) != value:
            raise IdentityPolicyError(f"identity_comparison_policy_{field}_unsupported")
    if payload.get("source_pair") != [
        "linkedin_connections_csv",
        "interaction_event_export.v1",
    ]:
        raise IdentityPolicyError("identity_comparison_policy_source_pair_unsupported")
    normalization = payload.get("normalization")
    if not isinstance(normalization, dict) or normalization.get("rule_id") != NORMALIZATION_RULE_ID:
        raise IdentityPolicyError("identity_comparison_policy_normalization_unsupported")
    required = payload.get("candidate_rule", {}).get("required_signals")
    if required != ["name_exact", "organization_exact", "position_exact"]:
        raise IdentityPolicyError("identity_comparison_policy_required_signals_unsupported")
    authority = payload.get("review_authority")
    if authority != {
        "authority_type": SUPPORTED_AUTHORITY_TYPE,
        "attestation_version": SUPPORTED_ATTESTATION_VERSION,
        "permitted_reviewer_roles": [SUPPORTED_REVIEWER_ROLE],
    }:
        raise IdentityPolicyError("identity_comparison_policy_review_authority_unsupported")
    return IdentityComparisonPolicy(
        policy_id=SUPPORTED_POLICY_ID,
        policy_version=SUPPORTED_POLICY_VERSION,
        file_sha256=sha256_file(policy_path),
        payload=payload,
    )
