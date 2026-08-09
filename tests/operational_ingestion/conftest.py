from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import pytest

from signal_agent.operational_ingestion import (
    AcquisitionIntent,
    CanonicalObservation,
    CapturedPage,
    CompletedRunReference,
    PolicyIdentity,
    RequestAttempt,
    SourceIdentity,
    canonical_json_bytes,
    sha256_bytes,
    sha256_canonical,
)
from signal_agent.operational_ingestion.canonical import derive_id, seal


FIXED_TIME = "2026-08-09T12:00:00Z"
SECOND_TIME = "2026-08-09T12:01:00Z"


def fixed_clock() -> str:
    return FIXED_TIME


def policy(name: str) -> PolicyIdentity:
    return PolicyIdentity(
        policy_id=name,
        version="1.0.0",
        file_sha256=sha256_canonical({"policy_id": name, "version": "1.0.0"}),
    )


def make_intent(*, prior=None) -> AcquisitionIntent:
    return AcquisitionIntent(
        source=SourceIdentity(
            source_type="synthetic_remote_observations.v1",
            source_instance_id="protected-fixture-source-v1",
        ),
        adapter=policy("fixture_remote_adapter"),
        acquisition_policy=policy("fixture_acquisition_policy"),
        assembly_policy=policy("fixture_canonical_observation_assembly"),
        retry_policy=policy("fixture_retry_policy"),
        secret_policy=policy("operational_secret_allowlist"),
        observation_boundary={"kind": "bounded_fixture_window", "lower": "root", "upper": "3"},
        credential_profile_ref="credential-profile-hash-fixture",
        authentication_mode="injected_fixture",
        prior_checkpoint_id=(None if prior is None else prior.payload["checkpoint_id"]),
        prior_checkpoint_hash=(None if prior is None else prior.payload["artifact_hash"]),
    )


def observation(record: str, version: int = 1) -> CanonicalObservation:
    return CanonicalObservation(
        record_type="synthetic_observation",
        protected_source_record_id=f"hmac:{record}",
        protection={
            "algorithm": "HMAC-SHA-256",
            "key_id": "fixture-protection-key",
            "version": "fixture_token.v1",
        },
        semantic_payload={
            "kind": "fixture_event",
            "state": f"version-{version}",
            "value": version,
        },
        source_event_time=f"2026-08-09T11:0{version}:00Z",
        remote_modified_at=f"2026-08-09T11:1{version}:00Z",
    )


def fingerprint(label: str) -> str:
    return sha256_canonical({"request": label})


def continuation(label: str) -> str:
    return sha256_canonical({"continuation": label})


def attempt(
    page: int,
    ordinal: int,
    *,
    outcome: str = "success",
    status: int | None = 200,
    request_label: str | None = None,
) -> RequestAttempt:
    return RequestAttempt(
        page_ordinal=page,
        attempt_ordinal=ordinal,
        request_fingerprint=fingerprint(request_label or f"page-{page}"),
        continuation_hash=continuation("root" if page == 1 else f"cursor-{page - 1}"),
        started_at=FIXED_TIME,
        completed_at=FIXED_TIME,
        outcome=outcome,
        status_code=status,
        provider_error_code=("rate_limit" if outcome == "rate_limited" else None),
        requested_delay_ms=(1000 if outcome == "rate_limited" else 0),
        applied_delay_ms=(1000 if outcome == "rate_limited" else 0),
        response_metadata={"provider_request_id": f"request-{page}-{ordinal}"},
    )


def page(
    page_ordinal: int,
    observations: Iterable[CanonicalObservation],
    *,
    terminal: bool,
    attempt_ordinal: int = 1,
    body_label: str | None = None,
) -> CapturedPage:
    records = tuple(observations)
    body = canonical_json_bytes(
        {
            "fixture_page": body_label or f"page-{page_ordinal}",
            "record_ids": [item.observation_id for item in records],
        }
    )
    return CapturedPage(
        page_ordinal=page_ordinal,
        successful_attempt_ordinal=attempt_ordinal,
        request_fingerprint=fingerprint(f"page-{page_ordinal}"),
        continuation_hash=continuation(
            "root" if page_ordinal == 1 else f"cursor-{page_ordinal - 1}"
        ),
        response_body=body,
        response_schema="synthetic_remote_page.v1",
        media_type="application/json",
        captured_at=FIXED_TIME,
        terminal=terminal,
        next_continuation=(
            {"kind": "end_of_stream"}
            if terminal
            else {"kind": "safe_fixture_cursor", "value": f"cursor-{page_ordinal}"}
        ),
        observations=records,
        response_metadata={"status": 200, "provider_request_id": f"request-{page_ordinal}"},
    )


def standard_history():
    first = observation("record-1")
    second = observation("record-2")
    attempts = (
        attempt(1, 1),
        attempt(2, 1, outcome="rate_limited", status=429),
        attempt(2, 2),
    )
    pages = (
        page(1, (first, second), terminal=False),
        page(2, (second,), terminal=True, attempt_ordinal=2),
    )
    return attempts, pages


def single_page_history():
    first = observation("record-1")
    second = observation("record-2")
    return (
        (attempt(1, 1),),
        (page(1, (second, first), terminal=True, body_label="repartitioned"),),
    )


def _write_exact(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        assert path.read_bytes() == payload
    else:
        path.write_bytes(payload)


class FakeGovernedProcessor:
    def __init__(self, *, fail_stage: str | None = None) -> None:
        self.fail_stage = fail_stage

    def process(self, *, bounded_material_path: Path, governed_run_root: Path, clock):
        bounded_bytes = bounded_material_path.read_bytes()
        bounded = json.loads(bounded_bytes.decode("utf-8"))
        governed_run_root.mkdir(parents=True, exist_ok=True)
        input_ref = {
            "bounded_material_id": bounded["bounded_material_id"],
            "bounded_material_hash": bounded["artifact_hash"],
            "observation_set_hash": bounded["observation_set_hash"],
        }
        if self.fail_stage == "before_preservation":
            raise RuntimeError("fake_before_preservation_failure")
        preserved_source_path = governed_run_root / "source/bounded_source_material.json"
        _write_exact(preserved_source_path, bounded_bytes)
        receipt_id = derive_id("fpr", input_ref)
        receipt = seal(
            {
                "schema_version": "signal_agent.fake_preservation_receipt.v1",
                "receipt_id": receipt_id,
                "created_at": clock(),
                "operational_input": input_ref,
                "source_sha256": sha256_bytes(bounded_bytes),
                "source_byte_size": len(bounded_bytes),
                "preserved_source": {
                    "path": "source/bounded_source_material.json",
                    "source_sha256": sha256_bytes(bounded_bytes),
                    "byte_size": len(bounded_bytes),
                },
                "source_records_mutated": False,
            },
            "receipt_hash",
        )
        receipt_path = governed_run_root / "source/preservation_receipt.json"
        _write_exact(receipt_path, canonical_json_bytes(receipt))
        if self.fail_stage == "after_preservation":
            raise RuntimeError("fake_after_preservation_failure")
        normalized = {
            "schema_version": "signal_agent.fake_normalized_observations.v1",
            "observation_set_hash": bounded["observation_set_hash"],
            "effects": [item["observation_id"] for item in bounded["observations"]],
        }
        normalized_path = governed_run_root / "normalized/observations.json"
        _write_exact(normalized_path, canonical_json_bytes(normalized))
        if self.fail_stage == "after_normalization":
            raise RuntimeError("fake_after_normalization_failure")
        output = {
            "schema_version": "signal_agent.fake_governed_output.v1",
            "observation_set_hash": bounded["observation_set_hash"],
            "effect_count": len(normalized["effects"]),
        }
        output_path = governed_run_root / "output/result.json"
        _write_exact(output_path, canonical_json_bytes(output))
        if self.fail_stage == "after_output_before_manifest":
            raise RuntimeError("fake_output_before_manifest_failure")
        run_id = derive_id("fgr", input_ref)
        manifest_id = derive_id("fgm", run_id, input_ref)
        receipt_bytes = receipt_path.read_bytes()
        manifest = seal(
            {
                "schema_version": "signal_agent.fake_governed_manifest.v1",
                "manifest_id": manifest_id,
                "run_id": run_id,
                "created_at": clock(),
                "completion_state": "completed",
                "operational_input": input_ref,
                "preservation_receipt": {
                    "path": "source/preservation_receipt.json",
                    "receipt_id": receipt_id,
                    "receipt_hash": receipt["receipt_hash"],
                    "file_sha256": sha256_bytes(receipt_bytes),
                },
                "preserved_source": {
                    "path": "source/bounded_source_material.json",
                    "source_sha256": sha256_bytes(bounded_bytes),
                    "byte_size": len(bounded_bytes),
                    "file_sha256": sha256_bytes(preserved_source_path.read_bytes()),
                },
                "artifacts": [
                    {
                        "path": "normalized/observations.json",
                        "sha256": sha256_bytes(normalized_path.read_bytes()),
                    },
                    {
                        "path": "output/result.json",
                        "sha256": sha256_bytes(output_path.read_bytes()),
                    },
                ],
                "safety_flags": {
                    "network_authorized": False,
                    "source_records_mutated": False,
                    "upstream_write_authorized": False,
                },
            },
            "manifest_hash",
        )
        manifest_path = governed_run_root / "manifest/completed_manifest.json"
        _write_exact(manifest_path, canonical_json_bytes(manifest))
        return CompletedRunReference(
            run_id=run_id,
            run_root=governed_run_root,
            run_root_ref="fake-governed-run",
            manifest_relative_path="manifest/completed_manifest.json",
            preservation_receipt_relative_path="source/preservation_receipt.json",
        )


def tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


@pytest.fixture
def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]
