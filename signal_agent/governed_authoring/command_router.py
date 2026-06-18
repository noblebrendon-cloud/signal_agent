from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .demo_bundle import DEMO_FIXTURES, FIXTURE_DIR, PROOF_SUMMARY_FILENAME
from .offline_harness import load_static_export_packet, run_offline_verification_file, write_static_import_packet
from .path_policy import PathPolicyError, classify_path, default_repo_root
from .workspace import LocalAuthoringWorkspace


ROUTER_SCHEMA_VERSION = "governed_authoring.local_command_router.v1"


@dataclass(frozen=True)
class RouterError:
    code: str
    category: str
    message: str
    path: str | None = None
    command: str | None = None
    recoverable: bool = True
    safe_to_retry: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "category": self.category,
            "message": self.message,
            "path": self.path,
            "command": self.command,
            "recoverable": self.recoverable,
            "safe_to_retry": self.safe_to_retry,
        }


class RouterErrorRaised(ValueError):
    def __init__(self, error: RouterError) -> None:
        super().__init__(error.message)
        self.error = error

    def to_dict(self) -> dict[str, Any]:
        return self.error.to_dict()


@dataclass(frozen=True)
class RouterCommandResult:
    command: str
    result_code: int
    status: str
    payload: dict[str, Any] = field(default_factory=dict)
    output_paths: list[str] = field(default_factory=list)
    errors: list[RouterError] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": ROUTER_SCHEMA_VERSION,
            "command": self.command,
            "result_code": self.result_code,
            "status": self.status,
            "payload": self.payload,
            "output_paths": self.output_paths,
            "errors": [error.to_dict() for error in self.errors],
        }


class LocalAuthoringCommandRouter:
    def __init__(
        self,
        *,
        repo_root: Path | None = None,
        temp_root: Path | None = None,
        fixture_dir: Path = FIXTURE_DIR,
    ) -> None:
        self.repo_root = (repo_root or default_repo_root()).resolve(strict=False)
        self.temp_root = Path(temp_root).resolve(strict=False) if temp_root else None
        self.fixture_dir = Path(fixture_dir)

    def route(self, command: str, **kwargs: Any) -> RouterCommandResult:
        if command == "verify-static-export":
            return self.verify_static_export(**kwargs)
        if command == "run-demo-bundle":
            return self.run_demo_bundle(**kwargs)
        if command == "inspect-result-packet":
            return self.inspect_result_packet(**kwargs)
        if command == "validate-output-directory":
            return self.validate_output_directory(**kwargs)
        if command == "summarize-proof-output":
            return self.summarize_proof_output(**kwargs)
        raise RouterErrorRaised(
            RouterError(
                code="UNSUPPORTED_COMMAND",
                category="input",
                message=f"unsupported router command: {command}",
                command=command,
            )
        )

    def workspace(self, path: Path | str) -> LocalAuthoringWorkspace:
        return LocalAuthoringWorkspace.validate(path, repo_root=self.repo_root, temp_root=self.temp_root)

    def validate_output_directory(self, *, workspace_path: Path | str) -> RouterCommandResult:
        workspace = self.workspace(workspace_path)
        classification = classify_path(
            workspace.root,
            repo_root=self.repo_root,
            workspace_root=workspace.root,
            temp_root=self.temp_root,
        )
        return RouterCommandResult(
            command="validate-output-directory",
            result_code=0,
            status="validated",
            payload={"classification": classification.to_dict()},
        )

    def verify_static_export(
        self,
        *,
        input_path: Path | str,
        workspace_path: Path | str,
        result_path: Path | str,
        canonical_ledger_path: Path | str | None = None,
        canonical_ledger_requested: bool = False,
        allow_overwrite: bool = False,
        raise_on_governance_error: bool = False,
    ) -> RouterCommandResult:
        command = "verify-static-export"
        input_file = self._require_input(input_path, command=command)
        workspace = self.workspace(workspace_path)
        output_file = workspace.validate_result_path(result_path, allow_overwrite=allow_overwrite)
        ledger_file = workspace.validate_ledger_path(
            canonical_ledger_path,
            ledger_requested=canonical_ledger_requested or canonical_ledger_path is not None,
        )

        self._load_json(input_file, command=command)
        result = run_offline_verification_file(input_file, canonical_ledger_path=ledger_file)
        if raise_on_governance_error:
            error = _governance_error(result, command=command)
            if error is not None:
                raise RouterErrorRaised(error)

        workspace.create_layout()
        write_static_import_packet(output_file, result)
        outputs = [str(output_file)]
        if ledger_file is not None:
            outputs.append(str(ledger_file))
        return RouterCommandResult(
            command=command,
            result_code=0,
            status="completed",
            payload={
                "static_import_packet": result["static_import_packet"],
                "backend_result": result["backend_result"],
            },
            output_paths=outputs,
        )

    def run_demo_bundle(
        self,
        *,
        workspace_path: Path | str,
        canonical_ledger_path: Path | str | None = None,
        canonical_ledger_requested: bool = False,
        allow_overwrite: bool = False,
    ) -> RouterCommandResult:
        command = "run-demo-bundle"
        workspace = self.workspace(workspace_path)
        ledger_file = workspace.validate_ledger_path(
            canonical_ledger_path,
            ledger_requested=canonical_ledger_requested or canonical_ledger_path is not None,
        )
        planned_results = [
            workspace.validate_result_path(
                workspace.root / "results" / f"{Path(fixture.filename).stem}.result.json",
                allow_overwrite=allow_overwrite,
            )
            for fixture in DEMO_FIXTURES
        ]
        summary_path = workspace.validate_summary_path(
            workspace.root / "summaries" / PROOF_SUMMARY_FILENAME,
            allow_overwrite=allow_overwrite,
        )

        workspace.create_layout()
        entries: list[dict[str, Any]] = []
        for fixture, output_file in zip(DEMO_FIXTURES, planned_results):
            result = run_offline_verification_file(
                self.fixture_dir / fixture.filename,
                canonical_ledger_path=ledger_file,
            )
            write_static_import_packet(output_file, result)
            packet = _as_mapping(result.get("static_import_packet"))
            actual_status = str(packet.get("output_status", ""))
            actual_review_status = str(packet.get("review_status", ""))
            entries.append(
                {
                    "fixture_name": fixture.filename,
                    "expected_result": fixture.expected_status,
                    "actual_result": actual_status,
                    "expected_review_status": fixture.expected_review_status,
                    "actual_review_status": actual_review_status,
                    "pass": actual_status == fixture.expected_status
                    and actual_review_status == fixture.expected_review_status,
                    "output_packet_path": str(output_file),
                    "canonical_ledger_entry_present": bool(packet.get("canonical_ledger_entry_id")),
                }
            )

        _write_summary(summary_path, entries=entries, canonical_ledger_path=ledger_file)
        outputs = [str(path) for path in planned_results]
        outputs.append(str(summary_path))
        if ledger_file is not None:
            outputs.append(str(ledger_file))
        return RouterCommandResult(
            command=command,
            result_code=0 if all(entry["pass"] for entry in entries) else 5,
            status="completed" if all(entry["pass"] for entry in entries) else "mismatch",
            payload={
                "passed": all(entry["pass"] for entry in entries),
                "results": entries,
                "canonical_ledger_path": str(ledger_file) if ledger_file else None,
                "proof_summary_path": str(summary_path),
            },
            output_paths=outputs,
        )

    def inspect_result_packet(
        self,
        *,
        input_path: Path | str,
        workspace_path: Path | str | None = None,
        report_path: Path | str | None = None,
        allow_overwrite: bool = False,
    ) -> RouterCommandResult:
        command = "inspect-result-packet"
        input_file = self._require_input(input_path, command=command)
        payload = self._load_json(input_file, command=command)
        if _as_mapping(payload).get("schema_version") != "governed_authoring.prototype_result.v1":
            raise RouterErrorRaised(
                RouterError(
                    code="UNSUPPORTED_PACKET_SHAPE",
                    category="input",
                    message="result packet is not a supported static import packet",
                    path=str(input_file),
                    command=command,
                )
            )

        outputs: list[str] = []
        if report_path is not None:
            if workspace_path is None:
                raise RouterErrorRaised(
                    RouterError(
                        code="MISSING_INPUT",
                        category="input",
                        message="workspace_path is required when report_path is provided",
                        command=command,
                    )
                )
            workspace = self.workspace(workspace_path)
            report_file = workspace.validate_summary_path(report_path, allow_overwrite=allow_overwrite)
            workspace.create_layout()
            report_file.parent.mkdir(parents=True, exist_ok=True)
            report_file.write_text(_inspection_report(payload), encoding="utf-8")
            outputs.append(str(report_file))

        return RouterCommandResult(
            command=command,
            result_code=0,
            status="inspected",
            payload={
                "schema_version": payload["schema_version"],
                "output_status": payload.get("output_status", ""),
                "review_status": payload.get("review_status", ""),
                "evidence_refs": list(payload.get("evidence_refs") or []),
                "unresolved_tensions": list(payload.get("unresolved_tensions") or []),
            },
            output_paths=outputs,
        )

    def summarize_proof_output(
        self,
        *,
        workspace_path: Path | str,
        summary_path: Path | str,
        allow_overwrite: bool = False,
    ) -> RouterCommandResult:
        command = "summarize-proof-output"
        workspace = self.workspace(workspace_path)
        output_file = workspace.validate_summary_path(summary_path, allow_overwrite=allow_overwrite)
        results_root = workspace.root / "results"
        result_files = sorted(results_root.glob("*.json")) if results_root.exists() else []
        rows: list[dict[str, Any]] = []
        for result_file in result_files:
            payload = json.loads(result_file.read_text(encoding="utf-8"))
            rows.append(
                {
                    "path": str(result_file),
                    "output_status": payload.get("output_status", ""),
                    "review_status": payload.get("review_status", ""),
                }
            )
        workspace.create_layout()
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(_proof_output_summary(rows), encoding="utf-8")
        return RouterCommandResult(
            command=command,
            result_code=0,
            status="summarized",
            payload={"result_count": len(rows), "results": rows},
            output_paths=[str(output_file)],
        )

    def _require_input(self, path: Path | str, *, command: str) -> Path:
        input_file = Path(path).resolve(strict=False)
        if not input_file.exists():
            raise RouterErrorRaised(
                RouterError(
                    code="MISSING_INPUT",
                    category="input",
                    message=f"required input does not exist: {input_file}",
                    path=str(input_file),
                    command=command,
                )
            )
        return input_file

    def _load_json(self, path: Path, *, command: str) -> Any:
        try:
            return load_static_export_packet(path)
        except json.JSONDecodeError as exc:
            raise RouterErrorRaised(
                RouterError(
                    code="INVALID_JSON",
                    category="input",
                    message=f"input is not valid JSON: {exc}",
                    path=str(path),
                    command=command,
                )
            ) from exc


def router_error_from_path_policy(exc: PathPolicyError, *, command: str | None = None) -> RouterError:
    payload = exc.to_dict()
    return RouterError(
        code=str(payload["code"]),
        category=str(payload["category"]),
        message=str(payload["message"]),
        path=str(payload["path"]) if payload.get("path") else None,
        command=command,
        recoverable=True,
        safe_to_retry=False,
    )


def _as_mapping(value: Any) -> dict[str, Any]:
    return value if type(value) is dict else {}


def _governance_error(result: dict[str, Any], *, command: str) -> RouterError | None:
    backend_result = _as_mapping(result.get("backend_result"))
    formal_decision = _as_mapping(backend_result.get("formal_decision"))
    decision = str(formal_decision.get("decision", ""))
    if decision == "REJECT_SELF_APPROVAL":
        return RouterError(
            code="SELF_CERTIFICATION_ATTEMPT",
            category="governance",
            message="generated or model output attempted to certify itself",
            command=command,
            recoverable=False,
        )
    if decision == "DEFER_UNRESOLVED_TENSION":
        return RouterError(
            code="BLOCKING_UNRESOLVED_TENSION",
            category="governance",
            message="blocking unresolved tension prevents approval",
            command=command,
            recoverable=True,
        )
    if decision == "REJECT_MISSING_EVIDENCE":
        return RouterError(
            code="MISSING_EVIDENCE",
            category="governance",
            message="approval-ready output is missing evidence refs",
            command=command,
            recoverable=True,
        )
    return None


def _write_summary(path: Path, *, entries: list[dict[str, Any]], canonical_ledger_path: Path | None) -> None:
    lines = [
        "# Local Command Router Demo Bundle",
        "",
        "| Fixture | Expected result | Actual result | Pass/fail | Output packet path | Canonical ledger entry present |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for entry in entries:
        lines.append(
            "| {fixture_name} | {expected_result} | {actual_result} | {pass_fail} | {output_packet_path} | {canonical_ledger_entry_present} |".format(
                fixture_name=entry["fixture_name"],
                expected_result=entry["expected_result"],
                actual_result=entry["actual_result"],
                pass_fail="pass" if entry["pass"] else "fail",
                output_packet_path=entry["output_packet_path"],
                canonical_ledger_entry_present="yes" if entry["canonical_ledger_entry_present"] else "no",
            )
        )
    lines.extend(
        [
            "",
            f"Canonical ledger path: `{canonical_ledger_path}`" if canonical_ledger_path else "Canonical ledger path: not requested.",
            "",
            "Boundary: local command-router output only. No server, browser submission, production writes, or default ledger writes.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _inspection_report(payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Static Import Result Packet",
            "",
            f"Output status: `{payload.get('output_status', '')}`",
            f"Review status: `{payload.get('review_status', '')}`",
            f"Evidence refs: `{len(payload.get('evidence_refs') or [])}`",
            f"Unresolved tensions: `{len(payload.get('unresolved_tensions') or [])}`",
            "",
        ]
    )


def _proof_output_summary(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Local Proof Output Summary",
        "",
        "| Result packet | Output status | Review status |",
        "| --- | --- | --- |",
    ]
    for row in rows:
        lines.append(f"| {row['path']} | {row['output_status']} | {row['review_status']} |")
    lines.append("")
    return "\n".join(lines)
