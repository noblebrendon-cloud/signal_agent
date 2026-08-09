from __future__ import annotations

import ast
import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from signal_agent.operational_ingestion import (
    OperationalIngestionKernel,
    SecretBoundaryError,
)
from signal_agent.operational_ingestion.artifacts import write_immutable_json

from .conftest import (
    FIXED_TIME,
    FakeGovernedProcessor,
    attempt,
    fixed_clock,
    make_intent,
    standard_history,
)


PROTECTED_HASHES = {
    "signal_agent/relationship_signals/relationship_pipeline.py": "967df45db658ea28200a093385b82f85b98f265781c7232516890312cccdff44",
    "signal_agent/corpus_import/linkedin/adapter.py": "44d001c43ebd374bfd4688fd9db5d0ef1d389bb41b1ba420c0111f65a392e01d",
    "signal_agent/corpus_import/interaction_events/adapter.py": "76954c789a92c313c297cfe8c4745b322e02453482f5573c7e20e6d7cb4d0589",
    "schemas/relationship_signals/relationship_record.v1.schema.json": "32a6d191d16dee34f1b6ac563d87dbd8597072d731c99dd0260200819c0d1ee1",
    "tests/fixtures/linkedin_connections/compatibility_witness_v1.json": "00755207eb9dc889951e9c751a58bc4e359cdecfac7a843a032370056dd9ce02",
    "tests/fixtures/interaction_events/compatibility_witness_v1.json": "823940b686bc7f0c0d6ccb5d348412ee7a39c2c15ea5ae2d457f62143146a14d",
    "tests/fixtures/identity_reconciliation/compatibility_witness_v1.json": "80a3790f8c88e5e5ed3a827c37052f9572c8a6783dbfaa3de79cc96567fe862b",
    "signal_agent/media_opportunities/gmail.py": "35f2e0b93ce88110f0da74f58b63021817ed1c5cbaa3beeb70b7f0ec7a52fad1",
    "signal_agent/corpus_import/cli.py": "5fc879ff45261fa3667bf14cee64fe134d86ea0c15bfb59e6f17c7d69e748eb7",
}


def imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(item.name for item in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def test_m4a_package_is_source_domain_and_network_neutral(repository_root: Path) -> None:
    package = repository_root / "signal_agent/operational_ingestion"
    forbidden = (
        "aiohttp",
        "httpx",
        "requests",
        "socket",
        "urllib",
        "signal_agent.corpus_import",
        "signal_agent.identity_reconciliation",
        "signal_agent.media_opportunities",
        "signal_agent.relationship_signals",
    )
    for path in package.glob("*.py"):
        for module in imports(path):
            assert not any(module == prefix or module.startswith(prefix + ".") for prefix in forbidden), (
                path,
                module,
            )


def test_milestone_1_to_3_and_excluded_surfaces_remain_exact(repository_root: Path) -> None:
    for relative, expected in PROTECTED_HASHES.items():
        actual = hashlib.sha256((repository_root / relative).read_bytes()).hexdigest()
        assert actual == expected, relative


def test_secret_key_is_rejected_before_artifact_write(tmp_path: Path) -> None:
    with pytest.raises(SecretBoundaryError, match="secret_key_prohibited"):
        write_immutable_json(
            tmp_path / "forbidden.json",
            {
                "schema_version": "fixture",
                "artifact_id": "fixture",
                "access_token": "should-never-persist",
                "artifact_hash": "sha256:" + ("0" * 64),
            },
        )
    assert not (tmp_path / "forbidden.json").exists()


@pytest.mark.parametrize(
    "key",
    [
        "access_token",
        "refresh_token",
        "api_key",
        "client_secret",
        "cookie",
        "authorization",
        "oauth_code",
        "pkce_verifier",
        "signed_url",
    ],
)
def test_all_prohibited_secret_keys_are_rejected_before_write(
    tmp_path: Path, key: str
) -> None:
    target = tmp_path / f"forbidden-{key}.json"
    with pytest.raises(SecretBoundaryError, match="secret_key_prohibited"):
        write_immutable_json(
            target,
            {
                "schema_version": "fixture",
                "artifact_id": "fixture",
                key: "secret-value-must-not-persist",
                "artifact_hash": "sha256:" + ("0" * 64),
            },
        )
    assert not target.exists()


@pytest.mark.parametrize(
    "canary",
    [
        "Bearer abcdefghijklmnop",
        "access_token=abcdefghijkl",
        "refresh-token: abcdefghijkl",
        "api_key=abcdefghijkl",
        "client_secret=abcdefghijkl",
        "Authorization: Basic abcdefghijkl",
        "Cookie: session=abcdefghijkl",
        "https://example.invalid/object?X-Amz-Signature=abcdefghijkl",
        "https://example.invalid/path?token=abcdefghijkl",
        "https://example.invalid/path?oauth_code=abcdefghijkl",
        "https://example.invalid/path?code_verifier=abcdefghijkl",
        "-----BEGIN PRIVATE KEY-----",
    ],
)
def test_secret_bearing_strings_and_signed_urls_are_rejected_before_write(
    tmp_path: Path, canary: str
) -> None:
    target = tmp_path / "forbidden-string.json"
    with pytest.raises(SecretBoundaryError, match="secret_boundary_violation"):
        write_immutable_json(
            target,
            {
                "schema_version": "fixture",
                "artifact_id": "fixture",
                "safe_field": canary,
                "artifact_hash": "sha256:" + ("0" * 64),
            },
        )
    assert not target.exists()


def test_secret_in_attempt_metadata_is_rejected_by_frozen_model() -> None:
    base = attempt(1, 1)
    with pytest.raises(SecretBoundaryError, match="secret_key_prohibited"):
        replace(base, response_metadata={"Authorization": "Bearer secret-value"})


def test_secret_in_response_body_never_persists(tmp_path: Path) -> None:
    attempts, pages = standard_history()
    poisoned = replace(
        pages[0],
        response_body=b'{"error":"Bearer secret-value-must-not-persist"}\n',
    )
    kernel = OperationalIngestionKernel(tmp_path / "store", clock=fixed_clock)
    with pytest.raises(SecretBoundaryError):
        kernel.run_from_captured_pages(
            intent=make_intent(),
            session_started_at=FIXED_TIME,
            transport_kind="fixture_transport",
            mode="fixture",
            attempts=attempts,
            pages=(poisoned, pages[1]),
            processor=FakeGovernedProcessor(),
            governed_run_root=tmp_path / "governed",
        )
    for path in (tmp_path / "store").rglob("*"):
        if path.is_file():
            raw = path.read_bytes()
            assert b"secret-value-must-not-persist" not in raw
            assert b"Bearer" not in raw


def test_successful_operational_tree_contains_no_secret_canaries(tmp_path: Path) -> None:
    attempts, pages = standard_history()
    result = OperationalIngestionKernel(tmp_path / "store", clock=fixed_clock).run_from_captured_pages(
        intent=make_intent(),
        session_started_at=FIXED_TIME,
        transport_kind="fixture_transport",
        mode="fixture",
        attempts=attempts,
        pages=pages,
        processor=FakeGovernedProcessor(),
        governed_run_root=tmp_path / "governed",
    )
    forbidden = (b"Bearer ", b"access_token", b"refresh_token", b"client_secret", b"api_key")
    for path in result.source_root.rglob("*"):
        if path.is_file():
            raw = path.read_bytes()
            assert not any(value in raw for value in forbidden), path
