from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from app.public_surfaces.report import build_governance_report


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DOMAIN_PROFILES = REPO_ROOT / "config" / "public_surfaces" / "domain_profiles.example.yaml"
DEFAULT_PRIMITIVE_REGISTRY = REPO_ROOT / "config" / "public_surfaces" / "primitive_registry.example.jsonl"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.public_surfaces.cli",
        description="Read-only public-surface governance readiness report.",
    )
    parser.add_argument(
        "--domain-profiles",
        default=DEFAULT_DOMAIN_PROFILES,
        type=Path,
        help="Domain profile YAML path",
    )
    parser.add_argument(
        "--primitive-registry",
        default=DEFAULT_PRIMITIVE_REGISTRY,
        type=Path,
        help="Signal primitive JSONL registry path",
    )
    parser.add_argument("--format", choices=("json", "text"), default="json")
    return parser


def render_report_text(report: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "Public surface governance report",
            f"Domains: {report['total_domains']}",
            f"Routable: {_render_values(report['routable_domains'])}",
            f"Quarantined: {_render_values(report['quarantined_domains'])}",
            f"Invalid domains: {_render_invalid_domains(report['invalid_domains'])}",
            f"Primitives: {report['total_primitives']}",
            f"Domains without primitives: {_render_values(report['domains_without_primitives'])}",
            f"Recommended holds: {len(report['recommended_holds'])}",
            "",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        report = build_governance_report(
            domain_profiles_path=args.domain_profiles,
            primitive_registry_path=args.primitive_registry,
        )
    except (OSError, TypeError, ValueError) as exc:
        _print_json(
            {
                "clean": False,
                "error_type": exc.__class__.__name__,
                "error": str(exc),
            }
        )
        return 1

    if args.format == "text":
        print(render_report_text(report), end="")
    else:
        _print_json(report)
    return 0


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _render_values(values: Any) -> str:
    normalized = [str(value) for value in values]
    return ", ".join(normalized) if normalized else "none"


def _render_invalid_domains(invalid_domains: Any) -> str:
    domain_ids = [str(row["domain_id"]) for row in invalid_domains]
    return _render_values(domain_ids)


if __name__ == "__main__":
    raise SystemExit(main())
