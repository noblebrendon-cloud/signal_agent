from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .hashing import canonical_json
from .milestone1 import run_milestone1
from .milestone2 import plan_milestone2, run_milestone2
from .models import ArchivePolicy


class CliUsageError(Exception):
    """Raised for operator-correctable argument errors."""


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CliUsageError(message)


def _print_json(payload: dict) -> None:
    sys.stdout.write(canonical_json(payload) + "\n")


def _handle_validate(args: argparse.Namespace) -> int:
    result = run_milestone1(Path(args.source), Path(args.run_root))
    _print_json(result.receipt)
    return result.exit_code


def _policy_from_args(args: argparse.Namespace) -> ArchivePolicy:
    baseline = ArchivePolicy()
    values = baseline.limits_dict()
    maximum_fields = (
        "max_archive_members",
        "max_declared_total_bytes",
        "max_actual_total_bytes",
        "max_member_bytes",
        "max_expansion_ratio",
        "max_path_length",
        "max_component_length",
    )
    for field_name in maximum_fields:
        configured = getattr(args, field_name, None)
        if configured is None:
            continue
        if configured <= 0:
            raise CliUsageError(f"--{field_name.replace('_', '-')} must be positive")
        if configured > getattr(baseline, field_name):
            raise CliUsageError(
                f"--{field_name.replace('_', '-')} may tighten policy v1 but may not weaken it"
            )
        values[field_name] = configured

    margin = getattr(args, "required_space_margin_bytes", None)
    if margin is not None:
        if margin < baseline.required_space_margin_bytes:
            raise CliUsageError(
                "--required-space-margin-bytes may increase policy v1's margin but may not reduce it"
            )
        values["required_space_margin_bytes"] = margin
    return ArchivePolicy(**values)


def _handle_plan_extraction(args: argparse.Namespace) -> int:
    result = plan_milestone2(Path(args.run_root), policy=_policy_from_args(args))
    _print_json(result.payload)
    return result.exit_code


def _handle_extract(args: argparse.Namespace) -> int:
    result = run_milestone2(Path(args.run_root), policy=_policy_from_args(args))
    _print_json(result.payload)
    return result.exit_code


def _handle_linkedin_relationship_slice(args: argparse.Namespace) -> int:
    # Kept lazy so the existing ChatGPT archive CLI remains independent of the
    # governed relationship-analysis package.
    from signal_agent.corpus_import.errors import CorpusImportError
    from signal_agent.relationship_signals.pipeline import run_linkedin_relationship_slice

    try:
        result = run_linkedin_relationship_slice(
            source=Path(args.source),
            run_root=Path(args.run_root),
            hmac_key_file=Path(args.hmac_key_file),
            hmac_key_id=args.hmac_key_id,
            repo_root=Path(args.repo_root),
            content_library_root=(
                Path(args.content_library_root) if args.content_library_root else None
            ),
            taxonomy_path=(Path(args.taxonomy_path) if args.taxonomy_path else None),
        )
    except (CorpusImportError, RuntimeError) as exc:
        _print_json(
            {
                "success": False,
                "status": "error",
                "reason_code": str(exc),
                "campaign_authorization": "none",
                "external_actions_performed": False,
            }
        )
        return 1
    _print_json(
        {
            "success": result.success,
            "status": "completed",
            "run_id": result.run_id,
            "run_root": str(result.run_root),
            "relationship_record_count": result.record_count,
            "unresolved_candidate_group_count": result.candidate_group_count,
            "cluster_confidence_state": result.cluster_confidence_state,
            "campaign_authorization": "none",
            "external_actions_performed": False,
        }
    )
    return 0


def _add_policy_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--max-archive-members", type=int)
    parser.add_argument("--max-declared-total-bytes", type=int)
    parser.add_argument("--max-actual-total-bytes", type=int)
    parser.add_argument("--max-member-bytes", type=int)
    parser.add_argument("--max-expansion-ratio", type=float)
    parser.add_argument("--max-path-length", type=int)
    parser.add_argument("--max-component-length", type=int)
    parser.add_argument("--required-space-margin-bytes", type=int)


def _build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(prog="signal-agent corpus")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate-chatgpt-export")
    validate.add_argument("--source", required=True)
    validate.add_argument("--run-root", required=True)
    validate.set_defaults(handler=_handle_validate)

    plan_extraction = subparsers.add_parser("plan-chatgpt-extraction")
    plan_extraction.add_argument("--run-root", required=True)
    _add_policy_arguments(plan_extraction)
    plan_extraction.set_defaults(handler=_handle_plan_extraction)

    extract = subparsers.add_parser("extract-chatgpt-export")
    extract.add_argument("--run-root", required=True)
    _add_policy_arguments(extract)
    extract.set_defaults(handler=_handle_extract)

    linkedin = subparsers.add_parser("import-linkedin-relationships")
    linkedin.add_argument("--source", required=True)
    linkedin.add_argument("--run-root", required=True)
    linkedin.add_argument("--hmac-key-file", required=True)
    linkedin.add_argument("--hmac-key-id", required=True)
    linkedin.add_argument("--repo-root", default=str(Path.cwd()))
    linkedin.add_argument("--content-library-root")
    linkedin.add_argument("--taxonomy-path")
    linkedin.set_defaults(handler=_handle_linkedin_relationship_slice)

    return parser


def main(argv: list[str] | None = None) -> int:
    effective_argv = list(sys.argv[1:] if argv is None else argv)
    if effective_argv[:1] == ["corpus"]:
        effective_argv = effective_argv[1:]

    parser = _build_parser()
    try:
        args = parser.parse_args(effective_argv)
        return int(args.handler(args))
    except CliUsageError as exc:
        _print_json(
            {
                "clean": False,
                "status": "error",
                "reason_code": "usage_error",
                "issues": [str(exc)],
                "publication_authorization": "none",
            }
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
