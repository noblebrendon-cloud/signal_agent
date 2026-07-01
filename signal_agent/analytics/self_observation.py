from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .metrics import build_metrics
from .report_builder import (
    render_self_observation_markdown,
    write_self_observation_report,
)
from .subsystem_detection import detect_subsystem_candidates


SELF_OBSERVATION_REPORT_VERSION = "self_observation_report.v1"

_SOURCE_FILES = {
    "transition_events": Path("data/state/transition_gate_events.jsonl"),
    "event_log": Path("data/state/event_log.jsonl"),
    "artifact_registry": Path("data/state/artifact_registry.jsonl"),
    "provider_events": Path("data/state/provider_events.jsonl"),
    "operator_runs": Path("data/operator/runs/operator_runs.jsonl"),
    "inference_cache_registry": Path("data/state/inference_cache_registry.jsonl"),
}
_PRIMARY_SOURCES = ("transition_events", "event_log")


@dataclass(frozen=True)
class JsonlReadResult:
    source_name: str
    path: Path
    exists: bool
    sha256: str | None
    total_line_count: int
    parsed_rows: tuple[dict[str, Any], ...]
    malformed_lines: tuple[dict[str, Any], ...]

    def metadata(self, *, rows_in_scope: int) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "exists": self.exists,
            "sha256": self.sha256,
            "total_line_count": self.total_line_count,
            "parsed_line_count": len(self.parsed_rows),
            "malformed_line_count": len(self.malformed_lines),
            "malformed_lines": list(self.malformed_lines),
            "rows_in_scope": int(rows_in_scope),
        }


def read_jsonl_with_metadata(path: Path | str, *, source_name: str = "jsonl") -> JsonlReadResult:
    resolved = Path(path)
    if not resolved.exists():
        return JsonlReadResult(
            source_name=source_name,
            path=resolved,
            exists=False,
            sha256=None,
            total_line_count=0,
            parsed_rows=(),
            malformed_lines=(),
        )

    raw_bytes = resolved.read_bytes()
    sha256 = hashlib.sha256(raw_bytes).hexdigest()
    text = raw_bytes.decode("utf-8", errors="replace")
    parsed_rows: list[dict[str, Any]] = []
    malformed_lines: list[dict[str, Any]] = []
    total_line_count = 0

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        total_line_count += 1
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            malformed_lines.append(
                {
                    "line_number": line_number,
                    "line_sha256": hashlib.sha256(raw_line.encode("utf-8")).hexdigest(),
                    "error": exc.msg,
                }
            )
            continue
        if isinstance(payload, dict):
            row = dict(payload)
            row["__self_observation_source"] = source_name
            row["__self_observation_line_number"] = line_number
            row["__self_observation_line_sha256"] = hashlib.sha256(
                raw_line.encode("utf-8")
            ).hexdigest()
            parsed_rows.append(row)
        else:
            malformed_lines.append(
                {
                    "line_number": line_number,
                    "line_sha256": hashlib.sha256(raw_line.encode("utf-8")).hexdigest(),
                    "error": "json_line_is_not_object",
                }
            )

    return JsonlReadResult(
        source_name=source_name,
        path=resolved,
        exists=True,
        sha256=sha256,
        total_line_count=total_line_count,
        parsed_rows=tuple(parsed_rows),
        malformed_lines=tuple(malformed_lines),
    )


def build_self_observation_report(
    repo_root: Path | str,
    *,
    last_n_events: int | None = None,
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    source_results = {
        name: read_jsonl_with_metadata(root / relative_path, source_name=name)
        for name, relative_path in _SOURCE_FILES.items()
    }
    rows_by_source = {
        name: _rows_in_scope(list(result.parsed_rows), last_n_events)
        for name, result in source_results.items()
    }
    source_files = {
        name: result.metadata(rows_in_scope=len(rows_by_source[name]))
        for name, result in source_results.items()
    }
    warnings = _build_warnings(source_results)
    primary_input_available = any(
        source_results[name].exists and len(source_results[name].parsed_rows) > 0
        for name in _PRIMARY_SOURCES
    )
    if not primary_input_available:
        warnings.append("primary_inputs_missing_or_empty")

    source_paths = {
        name: root / relative_path
        for name, relative_path in _SOURCE_FILES.items()
    }
    metrics = build_metrics(
        rows_by_source,
        repo_root=root,
        source_paths=source_paths,
        last_n_events=last_n_events,
    )
    repeated_patterns = {
        "repeated_workflow_patterns": metrics.get("repeated_workflow_patterns", []),
        "repeated_failure_patterns": metrics.get("repeated_failure_patterns", []),
        "high_friction_workflow_clusters": metrics.get("high_friction_workflow_clusters", []),
    }
    subsystem_candidates = detect_subsystem_candidates(rows_by_source)

    return {
        "schema_version": SELF_OBSERVATION_REPORT_VERSION,
        "repo_root": str(root),
        "filters": {
            "last_n_events": int(last_n_events) if last_n_events is not None else None,
        },
        "primary_input_available": primary_input_available,
        "source_files": source_files,
        "metrics": metrics,
        "repeated_patterns": repeated_patterns,
        "subsystem_candidates": subsystem_candidates,
        "recommendations": [],
        "warnings": warnings,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    report = build_self_observation_report(
        Path(args.repo_root),
        last_n_events=args.last_n_events,
    )

    if args.check:
        check_payload = {
            "schema_version": "self_observation_readiness.v1",
            "repo_root": report["repo_root"],
            "primary_input_available": report["primary_input_available"],
            "source_files": report["source_files"],
            "warnings": report["warnings"],
        }
        print(json.dumps(check_payload, sort_keys=True, indent=2))
        return 0 if report["primary_input_available"] else 2

    if not report["primary_input_available"]:
        print(
            "self-observation report not written: primary inputs are missing or empty",
            file=sys.stderr,
        )
        return 2

    if args.json_output:
        try:
            write_self_observation_report(
                report,
                args.json_output,
                markdown_output=args.markdown_output,
            )
        except ValueError as exc:
            print(f"self-observation report not written: {exc}", file=sys.stderr)
            return 2
        return 0

    if args.markdown_output:
        parser.error("--markdown-output requires --json-output")

    if args.json:
        print(json.dumps(report, sort_keys=True, indent=2))
    else:
        print(render_self_observation_markdown(report), end="")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a read-only self-observation report for governance telemetry.",
    )
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--last-n-events", type=int)
    parser.add_argument("--json-output")
    parser.add_argument("--markdown-output")
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the structured report as JSON when not writing outputs.",
    )
    return parser


def _rows_in_scope(rows: list[dict[str, Any]], last_n_events: int | None) -> list[dict[str, Any]]:
    if last_n_events is None:
        return rows
    return rows[-int(last_n_events):]


def _build_warnings(source_results: Mapping[str, JsonlReadResult]) -> list[str]:
    warnings: list[str] = []
    for name, result in sorted(source_results.items()):
        if not result.exists:
            warnings.append(f"source_missing:{name}")
        if result.malformed_lines:
            warnings.append(f"malformed_lines:{name}:{len(result.malformed_lines)}")
    return warnings


if __name__ == "__main__":
    raise SystemExit(main())
