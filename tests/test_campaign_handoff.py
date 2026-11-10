"""Integration and regression checks for provisional, traceable campaign handoffs."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from signal_agent.campaigns.core import CampaignValidationError, load_principles
from signal_agent.campaigns import service as campaign_service
from signal_agent.campaigns.service import CampaignNotReadyError, build_handoff, write_handoff
from signal_agent.governed_authoring import GovernedAuthoringRuntime
from signal_agent.governed_authoring.path_policy import PathPolicyError
from signal_agent.governed_authoring.workspace import LocalAuthoringWorkspace
from tests.test_campaign_decisions import (
    EVALUATED_AT,
    QUALIFIED_CLAIM,
    ROOT,
    SOURCE_TEXT,
    assert_schema,
    campaign_context,
    campaign_lineage,
)


EXPORT_FILES = {
    "inputs/campaign_context.json",
    "inputs/source_packet.json",
    "results/authoring_result.json",
    "metadata/campaign_decision.json",
    "metadata/source_to_series_task_packet.json",
    "metadata/campaign_handoff.json",
    "summaries/handoff.md",
    "validation/checksums.json",
}


def production_campaign() -> dict:
    campaign = campaign_context()
    campaign["requested_outputs"].append(
        {
            "output_id": "output.test.script",
            "kind": "video_script",
            "description": "Draft a script that distinguishes the hypothesis from demonstrated effects.",
        }
    )
    return campaign


def snapshot_files(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in root.rglob("*") if path.is_file() and not path.is_symlink()
    }


def test_handoff_runs_the_actual_governed_authoring_runtime_without_a_ledger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_run = GovernedAuthoringRuntime.run
    ledger_paths = []

    def observe_real_run(self: GovernedAuthoringRuntime, source_packet):
        ledger_paths.append(self.canonical_ledger_path)
        return original_run(self, source_packet)

    monkeypatch.setattr(GovernedAuthoringRuntime, "run", observe_real_run)

    handoff = build_handoff(production_campaign(), evaluated_at=EVALUATED_AT)
    independently_run = original_run(GovernedAuthoringRuntime(), handoff["source_packet"]).to_dict()

    assert ledger_paths == [None]
    assert handoff["authoring_result"] == independently_run
    assert independently_run["formal_decision"]["decision"] == "EMIT_PROVISIONAL_DRAFT"
    assert independently_run["output_manifest"]["output_status"] == "provisional"
    assert independently_run["review_decision"] is None
    assert independently_run["canonical_ledger_entry"] is None


def test_handoff_outputs_satisfy_existing_authoring_and_new_packet_schemas() -> None:
    handoff = build_handoff(production_campaign(), evaluated_at=EVALUATED_AT)

    for output in (
        handoff,
        handoff["decision"],
        handoff["source_packet"],
        handoff["authoring_result"]["draft_candidate"],
        handoff["authoring_result"]["output_manifest"],
        handoff["production_packet"],
    ):
        assert_schema(output, output["schema_version"])


def test_handoff_preserves_source_claim_qualifications_and_traceable_task_parents() -> None:
    campaign = production_campaign()

    handoff = build_handoff(campaign, evaluated_at=EVALUATED_AT)

    packet = handoff["production_packet"]
    source_packet = handoff["source_packet"]
    assert source_packet["source_material"][0]["text"] == SOURCE_TEXT
    assert source_packet["source_material"][0]["content_hash"] == hashlib.sha256(SOURCE_TEXT.encode("utf-8")).hexdigest()
    assert source_packet["claims"][0]["statement"] == QUALIFIED_CLAIM
    assert source_packet["claims"][0]["status"] == "qualified"
    assert packet["claim_refs"] == campaign["claims"]
    assert packet["constraints"] == campaign["constraints"]
    assert packet["purpose"] == campaign["purpose"]
    assert packet["decision_id"] == handoff["decision"]["decision_id"]
    assert packet["source_packet_id"] == source_packet["source_packet_id"]
    assert packet["campaign_digest"] == handoff["campaign_digest"] == handoff["decision"]["campaign_digest"]
    assert packet["campaign_id"] == campaign["campaign_id"]
    assert {item["source_id"] for item in packet["source_refs"]} == {"source.test.essay.v1"}
    assert len(packet["tasks"]) == len(campaign["requested_outputs"])
    assert len({task["task_id"] for task in packet["tasks"]}) == len(packet["tasks"])
    for task in packet["tasks"]:
        assert task["source_ids"] == ["source.test.essay.v1"]
        assert task["claim_ids"] == ["claim.test.qualified"]
        assert task["status"] == "pending"


def test_editorial_review_does_not_manufacture_publication_authority_or_completed_media() -> None:
    campaign = production_campaign()
    campaign["review"]["by"] = "human:campaign-owner"

    handoff = build_handoff(campaign, evaluated_at=EVALUATED_AT)

    assert handoff["publication_authorized"] is False
    assert handoff["execution_status"] == "prepared_not_executed"
    assert handoff["decision"]["authority_status"] == "not_granted_by_evaluation"
    assert handoff["production_packet"]["publication_authorized"] is False
    assert handoff["production_packet"]["execution_status"] == "pending_external_executor"
    assert all(task["status"] == "pending" for task in handoff["production_packet"]["tasks"])
    assert handoff["source_packet"]["review_decision"] is None
    assert handoff["authoring_result"]["output_manifest"]["review_decision_id"] == ""
    assert handoff["authoring_result"]["output_manifest"]["canonical_ledger_entry_id"] == ""


def test_executor_receives_the_selected_principle_guidance_and_evidence_limits() -> None:
    campaign = production_campaign()
    handoff = build_handoff(campaign, evaluated_at=EVALUATED_AT)
    packet = handoff["production_packet"]
    catalog = load_principles()
    expected_guidance = {
        item["id"]: item for item in catalog["principles"] if item["id"] in campaign["principle_ids"]
    }

    assert {item["id"]: item for item in packet["principle_guidance"]} == expected_guidance
    assert packet["catalog_version"] == handoff["decision"]["catalog_version"]
    assert packet["catalog_digest"] == handoff["decision"]["catalog_digest"]
    assert packet["proposed_action"] == handoff["decision"]["proposed_action"]
    assert packet["working_hypothesis"] == handoff["decision"]["working_hypothesis"]
    assert packet["evidence_limits"] == handoff["decision"]["limitations"]


def test_predecessor_and_correction_lineage_survives_the_executor_packet_and_export(tmp_path: Path) -> None:
    campaign = production_campaign()
    campaign["lineage"] = campaign_lineage()
    target = tmp_path / "linked-derivative"

    handoff = build_handoff(campaign, evaluated_at=EVALUATED_AT)
    write_handoff(campaign, evaluated_at=EVALUATED_AT, output_dir=target, repo_root=ROOT)

    assert handoff["decision"]["lineage"] == campaign["lineage"]
    assert handoff["production_packet"]["lineage"] == campaign["lineage"]
    assert_schema(handoff, handoff["schema_version"])
    assert_schema(handoff["production_packet"], handoff["production_packet"]["schema_version"])
    exported_packet = json.loads((target / "metadata/source_to_series_task_packet.json").read_text(encoding="utf-8"))
    exported_context = json.loads((target / "inputs/campaign_context.json").read_text(encoding="utf-8"))
    assert exported_packet["lineage"] == campaign["lineage"]
    assert exported_context["lineage"] == campaign["lineage"]
    assert exported_packet["publication_authorized"] is False


def test_unverified_claims_remain_unverified_and_keep_their_blocking_tension() -> None:
    campaign = production_campaign()
    campaign["claims"][0]["status"] = "unverified"
    campaign["claims"][0]["evidence_refs"] = []

    handoff = build_handoff(campaign, evaluated_at=EVALUATED_AT)

    assert handoff["production_packet"]["claim_refs"][0]["status"] == "unverified"
    assert handoff["authoring_result"]["output_manifest"]["output_status"] == "provisional"
    tensions = handoff["authoring_result"]["output_manifest"]["unresolved_tensions"]
    assert any(item["blocking"] and QUALIFIED_CLAIM in item["description"] for item in tensions)
    assert handoff["publication_authorized"] is False


def test_build_handoff_is_deterministic_immutable_and_does_not_write_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign = production_campaign()
    before = deepcopy(campaign)
    monkeypatch.chdir(tmp_path)

    first = build_handoff(campaign, evaluated_at=EVALUATED_AT)
    second = build_handoff(campaign, evaluated_at=EVALUATED_AT)

    assert first == second
    assert campaign == before
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("problem", ["misaligned", "source_violated", "unknown_review", "paused", "archived"])
def test_unsafe_or_closed_campaigns_cannot_be_exported_as_production_tasks(problem: str, tmp_path: Path) -> None:
    campaign = production_campaign()
    if problem in {"paused", "archived"}:
        campaign["phase"] = problem
    elif problem == "misaligned":
        campaign["review"]["mission"] = "misaligned"
    elif problem == "source_violated":
        campaign["review"]["source_fidelity"] = "violated"
    else:
        campaign["review"]["source_fidelity"] = "unknown"
    target = tmp_path / "blocked-handoff"

    with pytest.raises(CampaignNotReadyError) as build_error:
        build_handoff(campaign, evaluated_at=EVALUATED_AT)
    with pytest.raises(CampaignNotReadyError) as write_error:
        write_handoff(campaign, evaluated_at=EVALUATED_AT, output_dir=target, repo_root=ROOT)

    assert build_error.value.decision["production_eligible"] is False
    assert write_error.value.decision == build_error.value.decision
    assert not target.exists()


@pytest.mark.parametrize("mode", ["only_uri", "additional_unread_source"])
def test_a_source_reference_cannot_be_exported_as_if_its_text_had_been_retrieved(mode: str, tmp_path: Path) -> None:
    campaign = production_campaign()
    if mode == "only_uri":
        campaign["sources"][0]["text"] = ""
    else:
        campaign["sources"].append({"source_id": "source.test.not-retrieved", "uri": "https://example.invalid/unread"})
    target = tmp_path / "missing-source"

    with pytest.raises(CampaignNotReadyError):
        build_handoff(campaign, evaluated_at=EVALUATED_AT)
    with pytest.raises(CampaignNotReadyError):
        write_handoff(campaign, evaluated_at=EVALUATED_AT, output_dir=target, repo_root=ROOT)

    assert not target.exists()


def test_tampered_source_bytes_cannot_reuse_a_previously_valid_source_hash(tmp_path: Path) -> None:
    campaign = production_campaign()
    build_handoff(campaign, evaluated_at=EVALUATED_AT)
    campaign["sources"][0]["text"] += "An unsupported certainty was added."

    with pytest.raises(CampaignValidationError):
        write_handoff(campaign, evaluated_at=EVALUATED_AT, output_dir=tmp_path / "tampered", repo_root=ROOT)

    assert not (tmp_path / "tampered").exists()


def test_a_supplied_stale_or_forged_decision_cannot_override_re_evaluation() -> None:
    campaign = production_campaign()
    handoff = build_handoff(campaign, evaluated_at=EVALUATED_AT)
    campaign["phase"] = "archived"
    campaign["decision"] = deepcopy(handoff["decision"])
    campaign["decision"]["production_eligible"] = True

    with pytest.raises(CampaignValidationError):
        build_handoff(campaign, evaluated_at=EVALUATED_AT)


def test_changed_source_gets_new_traceable_handoff_and_task_identities() -> None:
    campaign = production_campaign()
    original = build_handoff(campaign, evaluated_at=EVALUATED_AT)
    updated_text = SOURCE_TEXT + "A second qualified source paragraph.\n"
    campaign["sources"][0]["text"] = updated_text
    campaign["sources"][0]["content_hash"] = "sha256:" + hashlib.sha256(updated_text.encode("utf-8")).hexdigest()

    updated = build_handoff(campaign, evaluated_at=EVALUATED_AT)

    assert updated["campaign_digest"] != original["campaign_digest"]
    assert updated["decision"]["decision_id"] != original["decision"]["decision_id"]
    assert updated["source_packet"]["source_packet_id"] != original["source_packet"]["source_packet_id"]
    assert updated["handoff_id"] != original["handoff_id"]
    assert {task["task_id"] for task in updated["production_packet"]["tasks"]}.isdisjoint(
        task["task_id"] for task in original["production_packet"]["tasks"]
    )
    assert updated["source_packet"]["source_material"][0]["text"] == updated_text


def test_missing_requested_outputs_do_not_create_invented_tasks_or_an_export(tmp_path: Path) -> None:
    campaign = production_campaign()
    campaign["requested_outputs"] = []

    with pytest.raises(CampaignNotReadyError):
        write_handoff(campaign, evaluated_at=EVALUATED_AT, output_dir=tmp_path / "no-outputs", repo_root=ROOT)

    assert not (tmp_path / "no-outputs").exists()


def test_claim_free_input_is_blocked_until_an_explicit_qualified_claim_can_keep_its_lineage(tmp_path: Path) -> None:
    campaign = production_campaign()
    qualified_text = (
        "Opening background material. " * 24
        + "\nQualification: no behavioral effect has been demonstrated."
    )
    campaign["sources"][0]["text"] = qualified_text
    campaign["sources"][0]["content_hash"] = ""
    campaign["claims"] = []
    target = tmp_path / "claim-free"

    with pytest.raises(CampaignNotReadyError) as blocked:
        build_handoff(campaign, evaluated_at=EVALUATED_AT)
    with pytest.raises(CampaignNotReadyError):
        write_handoff(campaign, evaluated_at=EVALUATED_AT, output_dir=target, repo_root=ROOT)

    assert blocked.value.decision["production_eligible"] is False
    assert not target.exists()

    campaign["claims"] = [{
        "claim_id": "claim.test.explicit-qualified",
        "statement": qualified_text,
        "status": "qualified",
        "evidence_refs": ["evidence:source.essay.v1"],
    }]
    handoff = build_handoff(campaign, evaluated_at=EVALUATED_AT)
    expected_ids = ["claim.test.explicit-qualified"]

    assert handoff["source_packet"]["source_material"][0]["text"] == qualified_text
    assert handoff["authoring_result"]["draft_candidate"]["claim_refs"][0]["statement"] == qualified_text
    assert handoff["authoring_result"]["output_manifest"]["claim_refs"] == expected_ids
    assert handoff["production_packet"]["claim_refs"] == campaign["claims"]
    assert all(task["claim_ids"] == expected_ids for task in handoff["production_packet"]["tasks"])


def test_export_uses_local_workspace_policy_and_preserves_exact_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign = production_campaign()
    target = tmp_path / "campaign-export"
    original_validate = LocalAuthoringWorkspace.validate.__func__
    checked_roots = []

    def observe_validation(cls, root, **kwargs):
        checked_roots.append(Path(root).resolve())
        return original_validate(cls, root, **kwargs)

    monkeypatch.setattr(LocalAuthoringWorkspace, "validate", classmethod(observe_validation))

    receipt = write_handoff(campaign, evaluated_at=EVALUATED_AT, output_dir=target, repo_root=ROOT)

    assert checked_roots == [target.resolve()]
    assert set(receipt["files"]) == EXPORT_FILES
    assert set(receipt["sha256"]) == EXPORT_FILES
    assert receipt["workspace"] == str(target.resolve())
    assert receipt["status"] == "prepared_not_executed"
    assert receipt["publication_authorized"] is False
    for relative, absolute in receipt["files"].items():
        path = Path(absolute)
        assert path == target / relative
        assert not path.is_symlink()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == receipt["sha256"][relative]
    source_packet = json.loads((target / "inputs/source_packet.json").read_text(encoding="utf-8"))
    assert source_packet["source_material"][0]["text"] == SOURCE_TEXT
    assert source_packet["claims"][0]["statement"] == QUALIFIED_CLAIM
    exported_handoff = json.loads((target / "metadata/campaign_handoff.json").read_text(encoding="utf-8"))
    assert exported_handoff == build_handoff(campaign, evaluated_at=EVALUATED_AT)
    checksums = json.loads((target / "validation/checksums.json").read_text(encoding="utf-8"))
    assert set(checksums["files"]) == EXPORT_FILES - {"validation/checksums.json"}
    assert all(checksums["files"][path] == receipt["sha256"][path] for path in checksums["files"])
    assert not list((target / "ledgers").iterdir())


def test_repeated_export_refuses_to_overwrite_any_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "existing-export"
    campaign = production_campaign()
    write_handoff(campaign, evaluated_at=EVALUATED_AT, output_dir=target, repo_root=ROOT)
    before = snapshot_files(target)

    with pytest.raises(PathPolicyError) as error:
        write_handoff(campaign, evaluated_at=EVALUATED_AT, output_dir=target, repo_root=ROOT)

    assert error.value.code == "OVERWRITE_DENIED"
    assert snapshot_files(target) == before


def test_parent_traversal_is_rejected_before_creating_an_export(tmp_path: Path) -> None:
    target = tmp_path / "allowed" / ".." / "escaped"

    with pytest.raises(PathPolicyError):
        write_handoff(production_campaign(), evaluated_at=EVALUATED_AT, output_dir=target, repo_root=ROOT)

    assert not (tmp_path / "allowed").exists()
    assert not (tmp_path / "escaped").exists()


@pytest.mark.parametrize("target_exists", [True, False])
def test_output_root_symlinks_cannot_redirect_or_create_external_files(target_exists: bool, tmp_path: Path) -> None:
    destination = tmp_path / "external"
    if target_exists:
        destination.mkdir()
        (destination / "sentinel.txt").write_text("leave unchanged", encoding="utf-8")
    link = tmp_path / "workspace-link"
    link.symlink_to(destination, target_is_directory=True)

    with pytest.raises(PathPolicyError):
        write_handoff(production_campaign(), evaluated_at=EVALUATED_AT, output_dir=link, repo_root=ROOT)

    if target_exists:
        assert snapshot_files(destination) == {"sentinel.txt": b"leave unchanged"}
    else:
        assert not destination.exists()


def test_a_symlinked_parent_cannot_redirect_an_apparently_new_child_workspace(tmp_path: Path) -> None:
    destination = tmp_path / "external"
    destination.mkdir()
    link = tmp_path / "linked-parent"
    link.symlink_to(destination, target_is_directory=True)

    with pytest.raises(PathPolicyError):
        write_handoff(production_campaign(), evaluated_at=EVALUATED_AT, output_dir=link / "new-export", repo_root=ROOT)

    assert list(destination.iterdir()) == []


def test_existing_workspace_with_nested_symlink_is_not_populated(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    destination = tmp_path / "external-results"
    destination.mkdir()
    (destination / "sentinel.txt").write_text("unchanged", encoding="utf-8")
    (workspace / "results").symlink_to(destination, target_is_directory=True)

    with pytest.raises(PathPolicyError):
        write_handoff(production_campaign(), evaluated_at=EVALUATED_AT, output_dir=workspace, repo_root=ROOT)

    assert snapshot_files(destination) == {"sentinel.txt": b"unchanged"}
    assert set(path.name for path in workspace.iterdir()) == {"results"}


@pytest.mark.parametrize("relative", ["data", "data/governed_authoring", "data/outputs/authoring", "signal_agent/new-export", "config/new-export"])
def test_production_or_source_paths_are_rejected_without_touching_existing_data(relative: str, tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    data = repository / "data"
    data.mkdir(parents=True)
    sentinel = data / "artifact_registry.jsonl"
    sentinel.write_text('{"production":"unchanged"}\n', encoding="utf-8")
    before = snapshot_files(repository)

    with pytest.raises(PathPolicyError):
        write_handoff(
            production_campaign(), evaluated_at=EVALUATED_AT,
            output_dir=repository / relative, repo_root=repository,
        )

    assert snapshot_files(repository) == before
    assert set(path.name for path in repository.iterdir()) == {"data"}


def test_an_additional_repo_root_cannot_remove_protection_from_the_executing_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    executing_checkout = tmp_path / "executing-checkout"
    data = executing_checkout / "data"
    data.mkdir(parents=True)
    (data / "artifact_registry.jsonl").write_text('{"production":"unchanged"}\n', encoding="utf-8")
    additional_repository = tmp_path / "additional-repository"
    additional_repository.mkdir()
    monkeypatch.setattr(
        campaign_service, "__file__",
        str(executing_checkout / "signal_agent" / "campaigns" / "service.py"),
    )
    before = snapshot_files(executing_checkout)

    with pytest.raises(PathPolicyError):
        write_handoff(
            production_campaign(), evaluated_at=EVALUATED_AT,
            output_dir=data / "forbidden-export", repo_root=additional_repository,
        )

    assert snapshot_files(executing_checkout) == before
    assert not (data / "forbidden-export").exists()
