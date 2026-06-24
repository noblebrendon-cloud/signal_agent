from __future__ import annotations

import argparse
import json
from typing import Any

from app.spine_observability.laviathon import (
    ALLOWED_OBSERVATION_TYPES,
    ALLOWED_REVIEW_STATUSES,
    ALLOWED_SPINE_TARGETS,
)
from app.spine_observability.laviathon_store import (
    append_laviathon_observation,
    list_laviathon_observations,
    list_review_candidates,
)
from app.spine_observability.models import ALLOWED_PLATFORMS
from app.spine_observability.store import (
    add_metric_snapshot,
    add_platform_account,
    add_platform_account_by_spine_name,
    add_spine,
    list_platform_accounts,
    list_spines,
)
from app.spine_observability.summary import (
    build_spine_summary,
    build_under_tracked_report,
    render_summary_text,
    render_under_tracked_text,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.spine_observability.cli",
        description="Local-only append-only spine observability CLI.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_spine_parser = subparsers.add_parser(
        "spine-add",
        aliases=["add-spine"],
        help="Append a local spine definition",
    )
    add_spine_parser.add_argument("--name", required=True)
    add_spine_parser.add_argument("--description", default="")
    add_spine_parser.add_argument("--created-at")
    add_spine_parser.add_argument("--inactive", action="store_true")
    add_spine_parser.set_defaults(func=run_spine_add)

    list_spines_parser = subparsers.add_parser(
        "spine-list",
        aliases=["list-spines"],
        help="List local spine definitions",
    )
    list_spines_parser.set_defaults(func=run_spine_list)

    add_platform_parser = subparsers.add_parser(
        "spine-add-platform",
        aliases=["add-platform"],
        help="Append a platform account under an existing spine",
    )
    spine_ref = add_platform_parser.add_mutually_exclusive_group(required=True)
    spine_ref.add_argument("--spine-id")
    spine_ref.add_argument("--spine-name")
    add_platform_parser.add_argument("--platform", required=True, choices=ALLOWED_PLATFORMS)
    add_platform_parser.add_argument("--account-label", required=True)
    add_platform_parser.add_argument("--content-lane", required=True)
    add_platform_parser.add_argument("--created-at")
    add_platform_parser.add_argument("--inactive", action="store_true")
    add_platform_parser.set_defaults(func=run_spine_add_platform)

    list_platforms_parser = subparsers.add_parser(
        "spine-list-platforms",
        aliases=["list-platforms"],
        help="List local platform accounts",
    )
    list_platforms_parser.set_defaults(func=run_spine_list_platforms)

    add_metric_parser = subparsers.add_parser(
        "spine-add-metric-snapshot",
        aliases=["add-metric"],
        help="Append a manual metric snapshot under an existing platform account",
    )
    add_metric_parser.add_argument("--platform-account-id", required=True)
    add_metric_parser.add_argument("--captured-at", required=True)
    add_metric_parser.add_argument("--metric-window-start", required=True)
    add_metric_parser.add_argument("--metric-window-end", required=True)
    add_metric_parser.add_argument(
        "--metrics-json",
        help="JSON object of flat numeric metric values",
    )
    add_metric_parser.add_argument(
        "--metric",
        action="append",
        default=[],
        help="Single KEY=VALUE metric. Repeat for multiple metrics.",
    )
    add_metric_parser.add_argument("--notes", default="")
    add_metric_parser.set_defaults(func=run_spine_add_metric_snapshot)

    summary_parser = subparsers.add_parser(
        "spine-summary",
        help="Read-only grouped summary of spines, platforms, and latest metrics",
    )
    summary_parser.add_argument("--format", choices=("json", "text"), default="json")
    summary_parser.add_argument("--under-tracked-days", type=_non_negative_int, default=7)
    summary_parser.add_argument("--as-of")
    summary_parser.set_defaults(func=run_spine_summary)

    under_tracked_parser = subparsers.add_parser(
        "spine-under-tracked",
        aliases=["under-tracked"],
        help="Read-only report of platforms missing recent metric snapshots",
    )
    under_tracked_parser.add_argument("--format", choices=("json", "text"), default="json")
    under_tracked_parser.add_argument("--days", type=_non_negative_int, default=7)
    under_tracked_parser.add_argument("--as-of")
    under_tracked_parser.set_defaults(func=run_spine_under_tracked)

    laviathon_add_parser = subparsers.add_parser(
        "laviathon-add-observation",
        help="Append a validated local-only Laviathon observation",
    )
    laviathon_add_parser.add_argument("--entity-id", required=True)
    laviathon_add_parser.add_argument("--source-artifact-id")
    laviathon_add_parser.add_argument("--created-at", required=True)
    laviathon_add_parser.add_argument("--source-context", required=True)
    laviathon_add_parser.add_argument("--spine-target", required=True, choices=ALLOWED_SPINE_TARGETS)
    laviathon_add_parser.add_argument("--observation-type", required=True, choices=ALLOWED_OBSERVATION_TYPES)
    laviathon_add_parser.add_argument("--claim", required=True)
    laviathon_add_parser.add_argument("--evidence", required=True)
    laviathon_add_parser.add_argument("--recommendation", required=True)
    laviathon_add_parser.add_argument("--public-safe", required=True, type=_parse_bool)
    laviathon_add_parser.add_argument("--requires-human-review", type=_parse_bool)
    laviathon_add_parser.add_argument("--review-status", choices=ALLOWED_REVIEW_STATUSES)
    laviathon_add_parser.add_argument("--external-action-allowed", type=_parse_bool, default=False)
    laviathon_add_parser.set_defaults(func=run_laviathon_add_observation)

    laviathon_list_parser = subparsers.add_parser(
        "laviathon-list-observations",
        help="List locally stored Laviathon observations",
    )
    laviathon_list_parser.set_defaults(func=run_laviathon_list_observations)

    laviathon_review_parser = subparsers.add_parser(
        "laviathon-review-candidates",
        help="List local Laviathon observations requiring human review",
    )
    laviathon_review_parser.add_argument("--include-all-statuses", action="store_true")
    laviathon_review_parser.add_argument("--observation-type", choices=ALLOWED_OBSERVATION_TYPES)
    laviathon_review_parser.set_defaults(func=run_laviathon_review_candidates)

    return parser


def run_spine_add(args: argparse.Namespace) -> int:
    record = add_spine(
        name=args.name,
        description=args.description,
        created_at=args.created_at,
        active=not args.inactive,
    )
    _print_json(record)
    return 0


def run_spine_list(args: argparse.Namespace) -> int:
    del args
    _print_json({"spines": list_spines()})
    return 0


def run_spine_add_platform(args: argparse.Namespace) -> int:
    if args.spine_name:
        record = add_platform_account_by_spine_name(
            spine_name=args.spine_name,
            platform=args.platform,
            account_label=args.account_label,
            content_lane=args.content_lane,
            created_at=args.created_at,
            active=not args.inactive,
        )
    else:
        record = add_platform_account(
            spine_id=args.spine_id,
            platform=args.platform,
            account_label=args.account_label,
            content_lane=args.content_lane,
            created_at=args.created_at,
            active=not args.inactive,
        )
    _print_json(record)
    return 0


def run_spine_list_platforms(args: argparse.Namespace) -> int:
    del args
    _print_json({"platform_accounts": list_platform_accounts()})
    return 0


def run_spine_add_metric_snapshot(args: argparse.Namespace) -> int:
    record = add_metric_snapshot(
        platform_account_id=args.platform_account_id,
        captured_at=args.captured_at,
        metric_window_start=args.metric_window_start,
        metric_window_end=args.metric_window_end,
        metrics=_parse_metrics(args.metrics_json, args.metric),
        notes=args.notes,
    )
    _print_json(record)
    return 0


def run_spine_summary(args: argparse.Namespace) -> int:
    summary = build_spine_summary(
        under_tracked_days=args.under_tracked_days,
        as_of=args.as_of,
    )
    if args.format == "text":
        print(render_summary_text(summary), end="")
    else:
        _print_json(summary)
    return 0


def run_spine_under_tracked(args: argparse.Namespace) -> int:
    report = build_under_tracked_report(days=args.days, as_of=args.as_of)
    if args.format == "text":
        print(render_under_tracked_text(report), end="")
    else:
        _print_json(report)
    return 0


def run_laviathon_add_observation(args: argparse.Namespace) -> int:
    observation = {
        "entity_id": args.entity_id,
        "created_at": args.created_at,
        "source_context": args.source_context,
        "spine_target": args.spine_target,
        "observation_type": args.observation_type,
        "claim": args.claim,
        "evidence": args.evidence,
        "recommendation": args.recommendation,
        "public_safe": args.public_safe,
        "external_action_allowed": args.external_action_allowed,
    }
    if args.source_artifact_id is not None:
        observation["source_artifact_id"] = args.source_artifact_id
    if args.requires_human_review is not None:
        observation["requires_human_review"] = args.requires_human_review
    if args.review_status is not None:
        observation["review_status"] = args.review_status
    _print_json(append_laviathon_observation(observation))
    return 0


def run_laviathon_list_observations(args: argparse.Namespace) -> int:
    del args
    _print_json({"observations": list_laviathon_observations()})
    return 0


def run_laviathon_review_candidates(args: argparse.Namespace) -> int:
    _print_json(
        {
            "review_candidates": list_review_candidates(
                include_all_statuses=args.include_all_statuses,
                observation_type=args.observation_type,
            )
        }
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _parse_metrics(metrics_json: str | None, metric_args: list[str]) -> dict[str, int | float]:
    metrics: dict[str, int | float] = {}
    if metrics_json:
        parsed = json.loads(metrics_json)
        if not isinstance(parsed, dict):
            raise ValueError("metrics_json_must_be_object")
        metrics.update(_coerce_metric_values(parsed))
    for item in metric_args:
        if "=" not in item:
            raise ValueError(f"invalid_metric_arg:{item}")
        key, raw_value = item.split("=", 1)
        metrics[key] = _coerce_metric_value(raw_value)
    if not metrics:
        raise ValueError("missing_metrics")
    return metrics


def _coerce_metric_values(payload: dict) -> dict[str, int | float]:
    return {str(key): _coerce_metric_value(value) for key, value in payload.items()}


def _coerce_metric_value(value: object) -> int | float:
    if isinstance(value, bool):
        raise ValueError("invalid_metric_value")
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        raw = value.strip()
        try:
            if "." in raw:
                return float(raw)
            return int(raw)
        except ValueError as exc:
            raise ValueError(f"invalid_metric_value:{value}") from exc
    raise ValueError(f"invalid_metric_value:{value}")


def _non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value_must_be_non_negative")
    return parsed


def _parse_bool(value: str) -> bool:
    normalized = str(value or "").strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise argparse.ArgumentTypeError("value_must_be_boolean")


if __name__ == "__main__":
    raise SystemExit(main())
