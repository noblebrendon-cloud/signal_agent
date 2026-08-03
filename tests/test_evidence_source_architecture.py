from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

import pytest

from signal_agent.corpus_import.hashing import canonical_json
from signal_agent.corpus_import.linkedin.adapter import LinkedInEvidenceAdapter
from signal_agent.evidence_sources.contracts import (
    ContextResolver,
    EvidenceSource,
    PacketBuilder,
    RelationshipAnalyzer,
    RelationshipNormalizer,
    RunManifestBuilder,
)
from signal_agent.evidence_sources.models import (
    NormalizedRelationshipBatch,
    PreservedEvidence,
    SourceReceiptDescriptor,
)
from signal_agent.relationship_signals.analysis import GovernedSystemsRelationshipAnalyzer
from signal_agent.relationship_signals.content_library import TeachingAtomContextResolver
from signal_agent.relationship_signals.manifest import DetachedRunManifestBuilder
from signal_agent.relationship_signals.packets import GovernedRelationshipPacketBuilder
from signal_agent.relationship_signals.relationship_pipeline import (
    run_relationship_signal_pipeline,
)


FIXED_CLOCK = "2026-08-02T12:00:00Z"
TEST_ONLY_KEY = bytes.fromhex(
    "6f4cda45d36a935e170c901da31c50f1"
    "ab2e248b823fc8354603c92f35d6f23e"
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _json_bytes(payload: object) -> bytes:
    return (canonical_json(payload) + "\n").encode("utf-8")


def _seal_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    sealed = dict(receipt)
    sealed.pop("receipt_hash", None)
    sealed["receipt_hash"] = "sha256:" + hashlib.sha256(
        canonical_json(sealed).encode("utf-8")
    ).hexdigest()
    return sealed


@dataclass(frozen=True)
class _SyntheticPrepared:
    source_path: Path
    source_bytes: bytes
    source_sha256: str
    receipt: dict[str, Any]
    record_id: str


@dataclass(frozen=True)
class _SyntheticRelationshipEvidenceAdapter:
    source_type: str = "synthetic_relationship_evidence"

    def prepare(
        self,
        source: str | Path,
        *,
        repository_root: Path,
        clock,
    ) -> _SyntheticPrepared:
        del repository_root
        source_path = Path(source).resolve(strict=True)
        source_bytes = source_path.read_bytes()
        source_sha256 = _sha256(source_bytes)
        receipt = _seal_receipt(
            {
                "schema_version": "test.synthetic_source_receipt.v1",
                "receipt_id": f"synthetic-source.{source_sha256[:16]}",
                "created_at": clock(),
                "source_sha256": f"sha256:{source_sha256}",
                "preserved_path": "00_original/synthetic.txt",
                "authorization_scope": "none",
            }
        )
        return _SyntheticPrepared(
            source_path=source_path,
            source_bytes=source_bytes,
            source_sha256=source_sha256,
            receipt=receipt,
            record_id=f"rel_synthetic_{source_sha256[:16]}",
        )

    def validate(
        self,
        prepared: _SyntheticPrepared,
        *,
        repository_root: Path,
        clock,
    ) -> None:
        del repository_root, clock
        if _sha256(prepared.source_path.read_bytes()) != prepared.source_sha256:
            raise RuntimeError("synthetic_source_changed")

    def preserve(
        self,
        prepared: _SyntheticPrepared,
        run_root: Path,
    ) -> PreservedEvidence:
        root = Path(run_root).resolve()
        root.mkdir(parents=True, exist_ok=False)
        original = root / "00_original/synthetic.txt"
        original.parent.mkdir(parents=True)
        original.write_bytes(prepared.source_bytes)
        (root / "00_original/synthetic.txt.sha256.txt").write_text(
            f"{prepared.source_sha256}  synthetic.txt\n",
            encoding="utf-8",
            newline="\n",
        )
        receipt_path = root / "05_receipts/source_receipt.json"
        receipt_path.parent.mkdir(parents=True)
        receipt_path.write_bytes(_json_bytes(prepared.receipt))
        descriptor = SourceReceiptDescriptor(
            receipt_id=prepared.receipt["receipt_id"],
            receipt_hash=prepared.receipt["receipt_hash"],
            source_sha256=prepared.source_sha256,
            persisted_relative_path="05_receipts/source_receipt.json",
            schema_version=prepared.receipt["schema_version"],
            protection_metadata=(
                ("algorithm", "none"),
                ("key_id", "synthetic-no-key"),
                ("version", "synthetic-protection.v1"),
            ),
        )
        return PreservedEvidence(
            source_sha256=prepared.source_sha256,
            preserved_relative_path="00_original/synthetic.txt",
            source_receipt=descriptor,
            provenance_metadata=(("source_type", self.source_type),),
        )

    def normalize(
        self,
        prepared: _SyntheticPrepared,
        preserved: PreservedEvidence,
    ) -> NormalizedRelationshipBatch:
        evidence_ref = f"synthetic-source:sha256:{preserved.source_sha256}:record:1"
        record = {
            "schema_version": "signal_agent.relationship_record.v1",
            "relationship_record_id": prepared.record_id,
            "source_provenance": {
                "source_sha256": f"sha256:{preserved.source_sha256}",
                "source_receipt_id": preserved.source_receipt.receipt_id,
                "record_number": 1,
                "line_start": 1,
                "line_end": 1,
                "raw_row_sha256": f"sha256:{preserved.source_sha256}",
                "evidence_ref": evidence_ref,
            },
            "person": {
                "first_name": "Synthetic",
                "middle_name": "",
                "last_name": "Evidence",
                "display_name": "Synthetic Evidence",
            },
            "professional_context": {
                "company": "Synthetic AI Governance Lab",
                "position": "Advisor",
            },
            "relationship": {
                "platform": "synthetic",
                "kind": "relationship",
                "connected_on_raw": "",
                "connected_on_date": None,
                "connected_on_state": "missing",
            },
            "identifiers": [],
            "deterministic_classification": {
                "source_platform": "synthetic",
                "source_format": "synthetic_relationship_evidence",
                "relationship_kind": "relationship",
            },
            "data_quality_issues": [],
            "privacy": {
                "contains_personal_data": False,
                "public_export_allowed": False,
            },
        }
        unresolved = {
            "schema_version": "signal_agent.unresolved_relationship_matches.v1",
            "state": "review_required",
            "source_sha256": f"sha256:{preserved.source_sha256}",
            "relationship_record_count": 1,
            "candidate_group_count": 0,
            "records_in_candidate_groups": [],
            "unresolved_record_ids": [prepared.record_id],
            "candidate_groups": [],
            "excluded_match_methods": [],
            "automatic_merge_performed": False,
            "canonical_identity_selected": False,
        }
        return NormalizedRelationshipBatch(
            preserved=preserved,
            records=(record,),
            unresolved_matches=unresolved,
        )


def _downstream_components(repository_root: Path):
    return {
        "analyzer": GovernedSystemsRelationshipAnalyzer(
            repository_root / "config/relationship_topics/governed_systems_v1.json"
        ),
        "resolver": TeachingAtomContextResolver(
            repository_root / "docs/operator/content_library"
        ),
        "packet_builder": GovernedRelationshipPacketBuilder(),
        "manifest_builder": DetachedRunManifestBuilder(),
    }


def test_neutral_models_expose_only_approved_fields() -> None:
    assert {item.name for item in fields(SourceReceiptDescriptor)} == {
        "receipt_id",
        "receipt_hash",
        "source_sha256",
        "persisted_relative_path",
        "schema_version",
        "protection_metadata",
    }
    assert {item.name for item in fields(PreservedEvidence)} == {
        "source_sha256",
        "preserved_relative_path",
        "source_receipt",
        "provenance_metadata",
    }


def test_concrete_components_satisfy_structural_protocols(tmp_path: Path) -> None:
    repository_root = Path(__file__).resolve().parents[1]
    adapter = LinkedInEvidenceAdapter(tmp_path / "unused-key", "unused-key-id")
    components = _downstream_components(repository_root)
    assert isinstance(adapter, EvidenceSource)
    assert isinstance(adapter, RelationshipNormalizer)
    assert isinstance(components["analyzer"], RelationshipAnalyzer)
    assert isinstance(components["resolver"], ContextResolver)
    assert isinstance(components["packet_builder"], PacketBuilder)
    assert isinstance(components["manifest_builder"], RunManifestBuilder)


def test_synthetic_relationship_source_uses_unchanged_downstream_pipeline(
    tmp_path: Path,
) -> None:
    repository_root = Path(__file__).resolve().parents[1]
    source = tmp_path / "synthetic-source.txt"
    source.write_text("synthetic governed relationship evidence\n", encoding="utf-8")
    source_adapter = _SyntheticRelationshipEvidenceAdapter()
    separate_normalizer_instance = _SyntheticRelationshipEvidenceAdapter()
    result = run_relationship_signal_pipeline(
        source=source,
        run_root=tmp_path / "synthetic-run",
        repository_root=repository_root,
        evidence_source=source_adapter,
        normalizer=separate_normalizer_instance,
        clock=lambda: FIXED_CLOCK,
        **_downstream_components(repository_root),
    )

    assert result.success is True
    assert result.record_count == 1
    assert result.cluster_confidence_state == "insufficient"
    signal = json.loads(
        (result.run_root / "04_packets/signal_packet.json").read_text(encoding="utf-8")
    )
    campaign = json.loads(
        (result.run_root / "04_packets/campaign_context_packet.json").read_text(
            encoding="utf-8"
        )
    )
    assert signal["status"] == "pending_human_approval"
    assert campaign["context_readiness"] == "insufficient_evidence"
    assert campaign["authorization"]["authorized"] is False


def test_later_failure_keeps_source_receipt_but_never_emits_run_manifest(
    tmp_path: Path,
) -> None:
    repository_root = Path(__file__).resolve().parents[1]
    source = tmp_path / "synthetic-source.txt"
    source.write_text("preserve before governed analysis failure\n", encoding="utf-8")
    run_root = tmp_path / "failed-run"

    class _FailingAnalyzer:
        def analyze(self, records: tuple[dict[str, Any], ...]) -> dict[str, Any]:
            assert len(records) == 1
            raise RuntimeError("injected_analysis_failure")

    with pytest.raises(RuntimeError, match="injected_analysis_failure"):
        run_relationship_signal_pipeline(
            source=source,
            run_root=run_root,
            repository_root=repository_root,
            evidence_source=_SyntheticRelationshipEvidenceAdapter(),
            normalizer=_SyntheticRelationshipEvidenceAdapter(),
            analyzer=_FailingAnalyzer(),
            clock=lambda: FIXED_CLOCK,
            **{
                key: value
                for key, value in _downstream_components(repository_root).items()
                if key != "analyzer"
            },
        )

    assert (run_root / "00_original/synthetic.txt").is_file()
    assert (run_root / "05_receipts/source_receipt.json").is_file()
    assert not (run_root / "05_receipts/run_manifest.json").exists()
    assert not (run_root / "01_normalized/relationship_records.jsonl").exists()
    assert not (run_root / ".staging").exists()


def test_synthetic_prepared_values_can_be_interleaved_across_instances(
    tmp_path: Path,
) -> None:
    repository_root = Path(__file__).resolve().parents[1]
    source_a = tmp_path / "a.txt"
    source_b = tmp_path / "b.txt"
    source_a.write_text("alpha", encoding="utf-8")
    source_b.write_text("beta", encoding="utf-8")
    adapter_a = _SyntheticRelationshipEvidenceAdapter()
    adapter_b = _SyntheticRelationshipEvidenceAdapter()
    prepared_a = adapter_a.prepare(
        source_a,
        repository_root=repository_root,
        clock=lambda: FIXED_CLOCK,
    )
    prepared_b = adapter_b.prepare(
        source_b,
        repository_root=repository_root,
        clock=lambda: FIXED_CLOCK,
    )

    adapter_b.validate(
        prepared_a,
        repository_root=repository_root,
        clock=lambda: FIXED_CLOCK,
    )
    adapter_a.validate(
        prepared_b,
        repository_root=repository_root,
        clock=lambda: FIXED_CLOCK,
    )
    preserved_b = adapter_a.preserve(prepared_b, tmp_path / "run-b")
    preserved_a = adapter_b.preserve(prepared_a, tmp_path / "run-a")
    batch_a = _SyntheticRelationshipEvidenceAdapter().normalize(prepared_a, preserved_a)
    batch_b = _SyntheticRelationshipEvidenceAdapter().normalize(prepared_b, preserved_b)

    assert batch_a.preserved is preserved_a
    assert batch_b.preserved is preserved_b
    assert batch_a.preserved.source_sha256 != batch_b.preserved.source_sha256
    assert batch_a.records[0]["relationship_record_id"] == prepared_a.record_id
    assert batch_b.records[0]["relationship_record_id"] == prepared_b.record_id


def test_linkedin_prepared_value_does_not_require_same_adapter_instance(
    tmp_path: Path,
) -> None:
    repository_root = Path(__file__).resolve().parents[1]
    source = repository_root / "tests/fixtures/linkedin_connections/Connections.csv"
    fake_repo = tmp_path / "repo"
    fake_repo.mkdir()
    key_file = tmp_path / "linkedin.relationship-hmac.key"
    key_file.write_bytes(TEST_ONLY_KEY)
    first = LinkedInEvidenceAdapter(key_file, "stateless-key-v1")
    second = LinkedInEvidenceAdapter(key_file, "stateless-key-v1")
    third = LinkedInEvidenceAdapter(key_file, "stateless-key-v1")

    prepared = first.prepare(
        source,
        repository_root=fake_repo,
        clock=lambda: FIXED_CLOCK,
    )
    second.validate(
        prepared,
        repository_root=fake_repo,
        clock=lambda: FIXED_CLOCK,
    )
    preserved = third.preserve(prepared, tmp_path / "linkedin-run")
    batch = second.normalize(prepared, preserved)

    assert batch.preserved is preserved
    assert len(batch.records) == 7


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
    return modules


def test_dependency_boundaries_have_no_importer_to_downstream_edge() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    linkedin_root = repository_root / "signal_agent/corpus_import/linkedin"
    prohibited = (
        "signal_agent.relationship_signals",
        "signal_agent.campaign",
        "signal_agent.content",
    )
    for path in linkedin_root.glob("*.py"):
        imports = _imports(path)
        assert not any(
            module.startswith(prefix)
            for module in imports
            for prefix in prohibited
        ), path

    generic_pipeline = repository_root / (
        "signal_agent/relationship_signals/relationship_pipeline.py"
    )
    generic_imports = _imports(generic_pipeline)
    assert not any(
        module.startswith("signal_agent.corpus_import.linkedin")
        for module in generic_imports
    )

    concrete_adapter_importers = []
    for path in (repository_root / "signal_agent").rglob("*.py"):
        if path.is_relative_to(linkedin_root):
            continue
        if "signal_agent.corpus_import.linkedin.adapter" in _imports(path):
            concrete_adapter_importers.append(path.relative_to(repository_root).as_posix())
    assert concrete_adapter_importers == ["signal_agent/relationship_signals/pipeline.py"]
    assert not any(
        module.startswith("signal_agent.relationship_signals.analysis")
        or module.startswith("signal_agent.relationship_signals.content_library")
        or module.startswith("signal_agent.relationship_signals.packets")
        or module.startswith("signal_agent.relationship_signals.manifest")
        for module in generic_imports
    )


@pytest.mark.parametrize(
    "imports",
    [
        [
            "signal_agent.evidence_sources.contracts",
            "signal_agent.relationship_signals.relationship_pipeline",
        ],
        [
            "signal_agent.corpus_import.linkedin.adapter",
            "signal_agent.relationship_signals.relationship_pipeline",
        ],
        [
            "signal_agent.relationship_signals.relationship_pipeline",
            "signal_agent.corpus_import.linkedin.adapter",
        ],
        ["signal_agent.relationship_signals.pipeline"],
    ],
)
def test_clean_import_orders_have_no_cycles(imports: list[str]) -> None:
    statements = ";".join(f"import {module}" for module in imports)
    if imports[-1] == "signal_agent.relationship_signals.relationship_pipeline":
        statements += (
            ";import sys;"
            "assert 'signal_agent.relationship_signals.pipeline' not in sys.modules"
        )
    completed = subprocess.run(
        [sys.executable, "-c", statements],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
