from __future__ import annotations

import argparse
import json
from typing import Any

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


if __name__ == "__main__":
    raise SystemExit(main())
