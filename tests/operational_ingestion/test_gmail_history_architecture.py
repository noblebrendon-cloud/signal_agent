from __future__ import annotations

import ast
import copy
import hashlib
import json
import re
from pathlib import Path

import pytest

from .gmail_test_support import (
    REPOSITORY_ROOT,
    fixture_path,
    load_projection,
    normalized_records,
    run_case,
)


PROTECTED_HASHES = {
    "signal_agent/relationship_signals/relationship_pipeline.py": "967df45db658ea28200a093385b82f85b98f265781c7232516890312cccdff44",
    "signal_agent/corpus_import/linkedin/adapter.py": "44d001c43ebd374bfd4688fd9db5d0ef1d389bb41b1ba420c0111f65a392e01d",
    "signal_agent/corpus_import/interaction_events/adapter.py": "76954c789a92c313c297cfe8c4745b322e02453482f5573c7e20e6d7cb4d0589",
    "signal_agent/corpus_import/cli.py": "5fc879ff45261fa3667bf14cee64fe134d86ea0c15bfb59e6f17c7d69e748eb7",
    "signal_agent/media_opportunities/gmail.py": "35f2e0b93ce88110f0da74f58b63021817ed1c5cbaa3beeb70b7f0ec7a52fad1",
    "signal_agent/operational_ingestion/kernel.py": "dec838d418c2d4337da9d34f9fa8d2b283cbe0111ccc808326dadb7b3bdf1f7a",
    "signal_agent/operational_ingestion/simulator.py": "7f16e571e650dadf2b68f793d72e00f79fb8a7ceae1a7777282b4a37a63d8bf9",
    "signal_agent/relationship_signals/simulated_operational_pipeline.py": "715c48896b6ffd0c98dd5221d34736dc1c4469503e12805c90369f543ebc1edf",
    "docs/architecture/MILESTONE_4C1_GMAIL_HISTORY_SOURCE_CONTRACT_REVIEW.md": "74ec88b7b5fa3b6a53fb453955066372429d8e884526fb05a8dccccb886f0e5a",
    "schemas/relationship_signals/relationship_record.v1.schema.json": "246e08373d0231004e7ad4fa99b0148953268ece1085a2086431e585f696149f",
    "schemas/relationship_signals/signal_packet.v1.schema.json": "50b0068357a3c984020466b23e06bebce3bf4fd5c4ddb9d7a2846f1fd49d49c9",
    "schemas/relationship_signals/campaign_context_packet.v1.schema.json": "69922cc274ae3234ebee4259d407a20ee01117b44de5d4a17d48a7b965609722",
    "tests/fixtures/linkedin_connections/compatibility_witness_v1.json": "52a581c65a0dde472a7eae4848219e7fda07e874100676a5537633f03ab77702",
    "tests/fixtures/interaction_events/compatibility_witness_v1.json": "823940b686bc7f0c0d6ccb5d348412ee7a39c2c15ea5ae2d457f62143146a14d",
    "tests/fixtures/identity_reconciliation/compatibility_witness_v1.json": "f6e253dbe0f9c5ab5cad83651d26584a084455abe0b010300b170ffe10c564e1",
    "tests/fixtures/operational_ingestion/compatibility_witness_v1.json": "a9610dd532c71d00e8fa120421660f1d367fa062ab9ca7a77184dab020858796",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _imports(path: Path) -> set[str]:
    result: set[str] = set()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


_LOCAL_SCHEMA_KEYWORDS = {
    "$id",
    "$schema",
    "additionalProperties",
    "const",
    "format",
    "items",
    "minimum",
    "minLength",
    "pattern",
    "properties",
    "required",
    "title",
    "type",
}

_LOCAL_SCHEMA_TYPES = {
    "array": list,
    "integer": int,
    "null": type(None),
    "object": dict,
    "string": str,
}


def _validate_local_schema_value(schema: dict, value) -> None:
    """Recursively validate the exact JSON Schema subset used by M4C1."""
    assert isinstance(schema, dict)
    assert set(schema) <= _LOCAL_SCHEMA_KEYWORDS

    declared = schema.get("type")
    if declared is not None:
        choices = [declared] if isinstance(declared, str) else declared
        assert isinstance(choices, list) and choices
        assert all(choice in _LOCAL_SCHEMA_TYPES for choice in choices)
        assert any(
            isinstance(value, _LOCAL_SCHEMA_TYPES[choice])
            and not (choice == "integer" and isinstance(value, bool))
            for choice in choices
        )
    if "const" in schema:
        assert value == schema["const"]
    if "minLength" in schema:
        assert isinstance(value, str)
        assert len(value) >= schema["minLength"]
    if "minimum" in schema:
        assert isinstance(value, (int, float)) and not isinstance(value, bool)
        assert value >= schema["minimum"]
    if "pattern" in schema:
        assert isinstance(value, str)
        assert re.search(schema["pattern"], value)

    if "required" in schema or "properties" in schema or "additionalProperties" in schema:
        assert isinstance(value, dict)
        required = schema.get("required", [])
        properties = schema.get("properties", {})
        assert isinstance(required, list) and all(isinstance(item, str) for item in required)
        assert isinstance(properties, dict)
        assert set(required) <= set(properties)
        assert set(required) <= set(value)
        additional = schema.get("additionalProperties", True)
        assert isinstance(additional, bool)
        if additional is False:
            assert set(value) <= set(properties)
        for name, child_schema in properties.items():
            if name in value:
                _validate_local_schema_value(child_schema, value[name])

    if "items" in schema:
        assert isinstance(value, list)
        item_schema = schema["items"]
        assert isinstance(item_schema, dict)
        for item in value:
            _validate_local_schema_value(item_schema, item)


def _validate_local_additive_schema(schema: dict, artifact: dict) -> None:
    """Validate the exact recursively supported subset used by both M4C1 schemas."""
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["type"] == "object"
    _validate_local_schema_value(schema, artifact)


def _minimal_projection() -> dict:
    digest = "sha256:" + ("0" * 64)
    return {
        "schema_version": "signal_agent.gmail_target_label_projection.v1",
        "projection_id": "projection",
        "source": {},
        "projection_policy": {},
        "target_label_ref": {},
        "prior_projection": None,
        "coverage_classification": "complete_captured_interval",
        "transitions": [{}],
        "final_states": [{}],
        "unresolved_relevance": [{}],
        "provider_observation_set_hash": digest,
        "target_label_projection_set_hash": digest,
        "semantic_identity_excludes": ["page_boundaries", "retry_history"],
        "projection_hash": digest,
    }


def _minimal_receipt() -> dict:
    digest = "sha256:" + ("0" * 64)
    return {
        "schema_version": "signal_agent.gmail_history_source_receipt.v1",
        "receipt_id": "receipt",
        "created_at": "2026-08-13T00:00:00Z",
        "status": "completed",
        "operational_input": {},
        "source_sha256": digest,
        "source_byte_size": 1,
        "preserved_source": {},
        "provider_observation_set_hash": digest,
        "target_label_projection": {},
        "identifier_protection": {},
        "source_records_mutated": False,
        "authorizations": {},
        "receipt_hash": digest,
    }


def _schema(name: str) -> dict:
    return json.loads(
        (REPOSITORY_ROOT / "schemas/operational_ingestion" / name).read_text(
            encoding="utf-8"
        )
    )


def _schema_features(schema: dict) -> tuple[set[str], set[str], set[str]]:
    keywords: set[str] = set()
    types: set[str] = set()
    item_types: set[str] = set()

    def visit(node: dict) -> None:
        keywords.update(node)
        declared = node.get("type")
        if declared is not None:
            types.update([declared] if isinstance(declared, str) else declared)
        properties = node.get("properties", {})
        for child in properties.values():
            visit(child)
        item_schema = node.get("items")
        if item_schema is not None:
            item_declared = item_schema.get("type")
            if isinstance(item_declared, str):
                item_types.add(item_declared)
            visit(item_schema)

    visit(schema)
    return keywords, types, item_types


def test_local_schema_validator_scope_matches_the_exact_m4c1_subset():
    features = [
        _schema_features(_schema(name))
        for name in (
            "gmail_history_source_receipt.v1.schema.json",
            "gmail_target_label_projection.v1.schema.json",
        )
    ]
    assert set().union(*(item[0] for item in features)) == _LOCAL_SCHEMA_KEYWORDS
    assert set().union(*(item[1] for item in features)) == {
        "array",
        "integer",
        "null",
        "object",
        "string",
    }
    assert set().union(*(item[2] for item in features)) == {"object", "string"}


def test_local_schema_validator_accepts_valid_string_and_object_item_arrays():
    _validate_local_additive_schema(
        _schema("gmail_target_label_projection.v1.schema.json"),
        _minimal_projection(),
    )


@pytest.mark.parametrize(
    "invalid_items",
    ([42], ["page_boundaries", 42]),
    ids=("integer-only", "mixed-string-integer"),
)
def test_local_schema_validator_rejects_closure_defect_non_string_array_items(
    invalid_items,
):
    projection = _minimal_projection()
    projection["semantic_identity_excludes"] = invalid_items
    with pytest.raises(AssertionError):
        _validate_local_additive_schema(
            _schema("gmail_target_label_projection.v1.schema.json"), projection
        )


@pytest.mark.parametrize(
    "case",
    (
        "missing_required",
        "unexpected_property",
        "wrong_const",
        "wrong_string_type",
        "wrong_array_type",
        "wrong_object_type",
        "wrong_nullable_union_type",
        "empty_min_length",
        "pattern_mismatch",
        "wrong_object_array_item_type",
        "wrong_integer_type",
        "below_minimum",
        "wrong_draft_uri",
    ),
)
def test_local_schema_validator_enforces_each_constraint_used_by_m4c1(case):
    projection_schema = _schema("gmail_target_label_projection.v1.schema.json")
    projection = _minimal_projection()
    receipt_schema = _schema("gmail_history_source_receipt.v1.schema.json")
    receipt = _minimal_receipt()

    if case == "missing_required":
        projection.pop("projection_id")
    elif case == "unexpected_property":
        projection["unexpected"] = True
    elif case == "wrong_const":
        projection["schema_version"] = "wrong"
    elif case == "wrong_string_type":
        projection["projection_id"] = 42
    elif case == "wrong_array_type":
        projection["transitions"] = {}
    elif case == "wrong_object_type":
        projection["source"] = []
    elif case == "wrong_nullable_union_type":
        projection["prior_projection"] = 42
    elif case == "empty_min_length":
        projection["projection_id"] = ""
    elif case == "pattern_mismatch":
        projection["projection_hash"] = "not-a-sha256"
    elif case == "wrong_object_array_item_type":
        projection["transitions"] = ["not-an-object"]
    elif case == "wrong_integer_type":
        receipt["source_byte_size"] = "1"
    elif case == "below_minimum":
        receipt["source_byte_size"] = 0
    elif case == "wrong_draft_uri":
        projection_schema["$schema"] = "https://example.invalid/not-the-draft"
    else:  # pragma: no cover - the parameter list is closed above
        raise AssertionError(case)

    with pytest.raises(AssertionError):
        if case in {"wrong_integer_type", "below_minimum"}:
            _validate_local_additive_schema(receipt_schema, receipt)
        else:
            _validate_local_additive_schema(projection_schema, projection)


def test_local_schema_validator_recurses_through_nested_object_and_array_items():
    nested_schema = {
        "type": "object",
        "required": ["entries"],
        "properties": {
            "entries": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["names"],
                    "properties": {
                        "names": {"type": "array", "items": {"type": "string"}}
                    },
                    "additionalProperties": False,
                },
            }
        },
        "additionalProperties": False,
    }
    valid = {"entries": [{"names": ["page_boundaries", "retry_history"]}]}
    _validate_local_schema_value(nested_schema, valid)

    invalid = copy.deepcopy(valid)
    invalid["entries"][0]["names"].append(42)
    with pytest.raises(AssertionError):
        _validate_local_schema_value(nested_schema, invalid)


def test_milestone_1_through_3_protected_files_are_byte_identical():
    assert {
        relative: _sha256(REPOSITORY_ROOT / relative)
        for relative in PROTECTED_HASHES
    } == PROTECTED_HASHES


def test_existing_kernel_and_source_adapters_do_not_import_m4c1():
    protected = [
        REPOSITORY_ROOT / "signal_agent/operational_ingestion",
        REPOSITORY_ROOT / "signal_agent/corpus_import/linkedin",
        REPOSITORY_ROOT / "signal_agent/corpus_import/interaction_events",
    ]
    for root in protected:
        for path in root.rglob("*.py"):
            assert "gmail_history" not in path.read_text(encoding="utf-8")


def test_m4c1_modules_have_no_network_or_live_gmail_client_imports():
    forbidden = {
        "google.auth",
        "google.oauth2",
        "googleapiclient",
        "httpx",
        "requests",
        "socket",
        "urllib.request",
    }
    paths = list(
        (REPOSITORY_ROOT / "signal_agent/corpus_import/gmail_history").glob("*.py")
    ) + [
        REPOSITORY_ROOT / "signal_agent/relationship_signals/gmail_history_pipeline.py"
    ]
    for path in paths:
        imports = _imports(path)
        assert not any(
            imported == denied or imported.startswith(denied + ".")
            for imported in imports
            for denied in forbidden
        )


def test_m4a_kernel_imports_neither_gmail_nor_relationship_packages():
    for path in (REPOSITORY_ROOT / "signal_agent/operational_ingestion").rglob("*.py"):
        imports = _imports(path)
        assert not any(item.startswith("signal_agent.corpus_import.gmail_history") for item in imports)
        assert not any(item.startswith("signal_agent.relationship_signals") for item in imports)


def test_offline_run_mutates_no_fixture_and_leaks_no_clear_identifier_downstream(tmp_path):
    source = fixture_path("gmail_bootstrap_nonempty.json")
    source_before = source.read_bytes()
    governed = tmp_path / "governed"
    result = run_case(
        tmp_path,
        script_name=source.name,
        governed_run_root=governed,
    )
    assert result.success and source.read_bytes() == source_before
    clear_canaries = (
        b"m-delete",
        b"m-leave",
        b"t-delete",
        b"t-leave",
        b"delete@synthetic.invalid",
        b"leave@synthetic.invalid",
        b"Label_TARGET",
    )
    for path in governed.rglob("*"):
        if not path.is_file() or "00_original" in path.parts:
            continue
        raw = path.read_bytes()
        assert not any(canary in raw for canary in clear_canaries), path
    records = normalized_records(governed)
    assert records
    assert all(item["privacy"]["message_body_retained"] is False for item in records)
    assert all(item["privacy"]["clear_email_retained"] is False for item in records)
    assert all(item["privacy"]["clear_message_id_retained"] is False for item in records)
    assert all(item["privacy"]["clear_thread_id_retained"] is False for item in records)
    assert all(
        item["deterministic_classification"]["source_platform"]
        == "gmail_history_offline"
        for item in records
    )


def test_projection_and_receipt_validate_against_additive_schemas(tmp_path):
    governed = tmp_path / "governed"
    result = run_case(
        tmp_path,
        script_name="gmail_bootstrap_nonempty.json",
        governed_run_root=governed,
    )
    assert result.success
    pairs = (
        (
            "schemas/operational_ingestion/gmail_target_label_projection.v1.schema.json",
            load_projection(governed),
        ),
        (
            "schemas/operational_ingestion/gmail_history_source_receipt.v1.schema.json",
            json.loads(
                (
                    governed / "05_receipts/gmail_history_source_receipt.json"
                ).read_text(encoding="utf-8")
            ),
        ),
    )
    for schema_path, artifact in pairs:
        schema = json.loads((REPOSITORY_ROOT / schema_path).read_text(encoding="utf-8"))
        _validate_local_additive_schema(schema, artifact)


def test_no_automatic_merge_or_external_authority_is_emitted(tmp_path):
    governed = tmp_path / "governed"
    result = run_case(
        tmp_path,
        script_name="gmail_bootstrap_nonempty.json",
        governed_run_root=governed,
    )
    assert result.success
    projection = load_projection(governed)
    assert all(item["automatic_merge_performed"] is False for item in projection["transitions"])
    manifest = json.loads(
        (governed / "05_receipts/gmail_operational_completed_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert not any(manifest["safety_flags"].values())
