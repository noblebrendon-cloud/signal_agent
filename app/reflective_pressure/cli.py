from __future__ import annotations

import argparse
import json
from typing import Any

from app.reflective_pressure.classify import classify_input
from app.reflective_pressure.export import export_prompt_pack
from app.reflective_pressure.generate import SUPPORTED_TEMPLATE_OUTPUTS, generate_draft
from app.reflective_pressure.importer import import_inputs_from_jsonl
from app.reflective_pressure.models import build_correction_record, build_golden_example_record, build_input_record
from app.reflective_pressure.observe import record_observation
from app.reflective_pressure.reconcile import reconcile_reflective_pressure_state
from app.reflective_pressure.review import build_review_packet
from app.reflective_pressure.store import (
    append_classification,
    append_correction,
    append_draft,
    append_golden_example,
    append_input,
    get_classification_by_id,
    get_input_by_id,
)
from app.reflective_pressure.summary import (
    summarize_classification_vs_correction_drift,
    summarize_corrections_by_pressure_type,
    summarize_golden_examples,
    summarize_operational_next_actions,
    summarize_by_platform,
    summarize_by_pressure_type,
    summarize_by_spine,
    summarize_recent_activity,
    summarize_ready_for_prompt_export,
    summarize_recognition_signals,
    summarize_risk_signals,
)
from app.reflective_pressure.taxonomy import OUTPUT_TYPES, PRESSURE_TYPES, SOURCE_PLATFORMS, SOURCE_TYPES, SPINES


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.reflective_pressure.cli",
        description="Local-only Reflective Pressure Spine operator CLI.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_input = subparsers.add_parser("rp-add-input", help="Append a local social/content pressure input")
    add_input.add_argument("--source-platform", required=True, choices=SOURCE_PLATFORMS)
    add_input.add_argument("--source-type", required=True, choices=SOURCE_TYPES)
    add_input.add_argument("--raw-text", required=True)
    add_input.add_argument("--source-context", default="")
    add_input.add_argument("--group-or-channel", default="")
    add_input.add_argument("--intended-spine", default="unknown", choices=SPINES)
    add_input.add_argument("--tags", default="")
    add_input.add_argument("--notes", default="")
    add_input.set_defaults(func=run_add_input)

    import_inputs = subparsers.add_parser("rp-import-inputs", help="Import pressure inputs from a JSONL seed file")
    import_inputs.add_argument("--path", required=True)
    import_inputs.add_argument("--classify", action="store_true")
    import_inputs.add_argument("--generate-draft", action="store_true")
    import_inputs.add_argument("--output-type", choices=tuple(sorted(SUPPORTED_TEMPLATE_OUTPUTS)))
    import_inputs.set_defaults(func=run_import_inputs)

    classify = subparsers.add_parser("rp-classify", help="Classify an existing pressure input")
    classify.add_argument("--input-id", required=True)
    classify.set_defaults(func=run_classify)

    review = subparsers.add_parser("rp-review", help="Build a connected review packet for one input")
    review.add_argument("--input-id", required=True)
    review.set_defaults(func=run_review)

    draft = subparsers.add_parser("rp-generate-draft", help="Generate a deterministic reflective draft")
    draft.add_argument("--input-id", required=True)
    draft.add_argument("--classification-id", required=True)
    draft.add_argument("--output-type", required=True, choices=tuple(sorted(SUPPORTED_TEMPLATE_OUTPUTS)))
    draft.add_argument("--target-platform", choices=SOURCE_PLATFORMS)
    draft.set_defaults(func=run_generate_draft)

    correction = subparsers.add_parser("rp-correct-classification", help="Append a human correction for a classification")
    correction.add_argument("--classification-id", required=True)
    correction.add_argument("--input-id", required=True)
    correction.add_argument("--pressure-type", required=True, choices=PRESSURE_TYPES)
    correction.add_argument("--surface-claim")
    correction.add_argument("--hidden-pressure")
    correction.add_argument("--moral-temperature", type=_score_arg)
    correction.add_argument("--ambiguity-level", type=_score_arg)
    correction.add_argument("--audience-self-insertion-potential", type=_score_arg)
    correction.add_argument("--risk-of-tribal-escalation", type=_score_arg)
    correction.add_argument("--recognition-potential", type=_score_arg)
    correction.add_argument("--recommended-output-type", choices=OUTPUT_TYPES)
    correction.add_argument("--correction-reason", required=True)
    correction.add_argument("--corrected-by", default="human_operator")
    correction.set_defaults(func=run_correct_classification)

    golden = subparsers.add_parser("rp-mark-golden", help="Append a reusable golden pressure example")
    golden.add_argument("--input-id", required=True)
    golden.add_argument("--classification-id", required=True)
    golden.add_argument("--correction-id")
    golden.add_argument("--draft-id")
    golden.add_argument("--pressure-type", required=True, choices=PRESSURE_TYPES)
    golden.add_argument("--title", required=True)
    golden.add_argument("--why-it-matters", required=True)
    golden.add_argument("--reusable-pattern", required=True)
    golden.add_argument("--voice-notes", default="")
    golden.add_argument("--risk-notes", default="")
    golden.add_argument("--approved-for-prompt-export", type=_bool_arg, default=False)
    golden.set_defaults(func=run_mark_golden)

    observation = subparsers.add_parser("rp-record-observation", help="Append manual response metrics")
    observation.add_argument("--input-id", required=True)
    observation.add_argument("--draft-id", required=True)
    observation.add_argument("--observation-window", default="manual")
    observation.add_argument("--views", type=_non_negative_number, default=0)
    observation.add_argument("--reactions", type=_non_negative_number, default=0)
    observation.add_argument("--comments", type=_non_negative_number, default=0)
    observation.add_argument("--shares", type=_non_negative_number, default=0)
    observation.add_argument("--saves", type=_non_negative_number, default=0)
    observation.add_argument("--profile-clicks", type=_non_negative_number, default=0)
    observation.add_argument("--recognition-events", type=_non_negative_number, default=0)
    observation.add_argument("--constructive-reply-ratio", type=_non_negative_number, default=0)
    observation.add_argument("--self-insertion-density", type=_non_negative_number, default=0)
    observation.add_argument("--delayed-recirculation", type=_non_negative_number, default=0)
    observation.add_argument("--contradiction-heat", type=_non_negative_number, default=0)
    observation.add_argument("--notes", default="")
    observation.set_defaults(func=run_record_observation)

    summary = subparsers.add_parser("rp-summary", help="Read deterministic summary reports")
    summary.add_argument(
        "--by",
        required=True,
        choices=(
            "pressure_type",
            "platform",
            "spine",
            "recognition",
            "risk",
            "recent",
            "corrections",
            "golden",
            "drift",
            "prompt_export",
            "next_actions",
        ),
    )
    summary.add_argument("--limit", type=_non_negative_int, default=20)
    summary.set_defaults(func=run_summary)

    export = subparsers.add_parser("rp-export-prompt-pack", help="Export approved golden examples to a local markdown pack")
    export.add_argument("--path", required=True)
    export.add_argument("--pressure-type", choices=PRESSURE_TYPES)
    export.add_argument("--approved-only", type=_bool_arg, default=True)
    export.set_defaults(func=run_export_prompt_pack)

    reconcile = subparsers.add_parser("rp-reconcile", help="Reconcile reflective pressure ledgers")
    reconcile.set_defaults(func=run_reconcile)

    return parser


def run_add_input(args: argparse.Namespace) -> int:
    record = build_input_record(
        source_platform=args.source_platform,
        source_type=args.source_type,
        raw_text=args.raw_text,
        source_context=args.source_context,
        group_or_channel=args.group_or_channel,
        intended_spine=args.intended_spine,
        tags=_parse_tags(args.tags),
        notes=args.notes,
    )
    _print_json(append_input(record))
    return 0


def run_import_inputs(args: argparse.Namespace) -> int:
    _print_json(
        import_inputs_from_jsonl(
            args.path,
            classify=args.classify,
            generate_draft=args.generate_draft,
            output_type=args.output_type,
        )
    )
    return 0


def run_classify(args: argparse.Namespace) -> int:
    input_record = get_input_by_id(args.input_id)
    if input_record is None:
        raise ValueError(f"unknown_input:{args.input_id}")
    classification = classify_input(input_record)
    _print_json(append_classification(classification))
    return 0


def run_review(args: argparse.Namespace) -> int:
    _print_json(build_review_packet(args.input_id))
    return 0


def run_generate_draft(args: argparse.Namespace) -> int:
    input_record = get_input_by_id(args.input_id)
    if input_record is None:
        raise ValueError(f"unknown_input:{args.input_id}")
    classification = get_classification_by_id(args.classification_id)
    if classification is None:
        raise ValueError(f"unknown_classification:{args.classification_id}")
    draft = generate_draft(
        input_record,
        classification,
        output_type=args.output_type,
        target_platform=args.target_platform,
    )
    _print_json(append_draft(draft))
    return 0


def run_correct_classification(args: argparse.Namespace) -> int:
    classification = get_classification_by_id(args.classification_id)
    if classification is None:
        raise ValueError(f"unknown_classification:{args.classification_id}")
    if classification["input_id"] != args.input_id:
        raise ValueError("classification_input_mismatch")
    correction = build_correction_record(
        target_record_type="classification",
        target_record_id=classification["classification_id"],
        input_id=args.input_id,
        corrected_pressure_type=args.pressure_type,
        corrected_surface_claim=args.surface_claim or classification["surface_claim"],
        corrected_hidden_pressure=args.hidden_pressure or classification["hidden_pressure"],
        corrected_moral_temperature=(
            args.moral_temperature
            if args.moral_temperature is not None
            else int(classification["moral_temperature"])
        ),
        corrected_ambiguity_level=(
            args.ambiguity_level
            if args.ambiguity_level is not None
            else int(classification["ambiguity_level"])
        ),
        corrected_audience_self_insertion_potential=(
            args.audience_self_insertion_potential
            if args.audience_self_insertion_potential is not None
            else int(classification["audience_self_insertion_potential"])
        ),
        corrected_risk_of_tribal_escalation=(
            args.risk_of_tribal_escalation
            if args.risk_of_tribal_escalation is not None
            else int(classification["risk_of_tribal_escalation"])
        ),
        corrected_recognition_potential=(
            args.recognition_potential
            if args.recognition_potential is not None
            else int(classification["recognition_potential"])
        ),
        corrected_recommended_output_type=args.recommended_output_type or classification["recommended_output_type"],
        correction_reason=args.correction_reason,
        corrected_by=args.corrected_by,
    )
    _print_json(append_correction(correction))
    return 0


def run_mark_golden(args: argparse.Namespace) -> int:
    golden = build_golden_example_record(
        input_id=args.input_id,
        classification_id=args.classification_id,
        correction_id=args.correction_id,
        draft_id=args.draft_id,
        pressure_type=args.pressure_type,
        title=args.title,
        why_it_matters=args.why_it_matters,
        reusable_pattern=args.reusable_pattern,
        voice_notes=args.voice_notes,
        risk_notes=args.risk_notes,
        approved_for_prompt_export=args.approved_for_prompt_export,
    )
    _print_json(append_golden_example(golden))
    return 0


def run_record_observation(args: argparse.Namespace) -> int:
    observation = record_observation(
        input_id=args.input_id,
        draft_id=args.draft_id,
        observation_window=args.observation_window,
        views=args.views,
        reactions=args.reactions,
        comments=args.comments,
        shares=args.shares,
        saves=args.saves,
        profile_clicks=args.profile_clicks,
        recognition_events=args.recognition_events,
        constructive_reply_ratio=args.constructive_reply_ratio,
        self_insertion_density=args.self_insertion_density,
        delayed_recirculation=args.delayed_recirculation,
        contradiction_heat=args.contradiction_heat,
        notes=args.notes,
    )
    _print_json(observation)
    return 0


def run_summary(args: argparse.Namespace) -> int:
    if args.by == "pressure_type":
        payload = summarize_by_pressure_type()
    elif args.by == "platform":
        payload = summarize_by_platform()
    elif args.by == "spine":
        payload = summarize_by_spine()
    elif args.by == "recognition":
        payload = summarize_recognition_signals()
    elif args.by == "risk":
        payload = summarize_risk_signals()
    elif args.by == "recent":
        payload = summarize_recent_activity(limit=args.limit)
    elif args.by == "corrections":
        payload = summarize_corrections_by_pressure_type()
    elif args.by == "golden":
        payload = summarize_golden_examples()
    elif args.by == "drift":
        payload = summarize_classification_vs_correction_drift()
    elif args.by == "prompt_export":
        payload = summarize_ready_for_prompt_export()
    elif args.by == "next_actions":
        payload = summarize_operational_next_actions()
    else:
        raise ValueError(f"unsupported_summary:{args.by}")
    _print_json(payload)
    return 0


def run_export_prompt_pack(args: argparse.Namespace) -> int:
    _print_json(
        export_prompt_pack(
            args.path,
            pressure_type=args.pressure_type,
            approved_only=args.approved_only,
        )
    )
    return 0


def run_reconcile(args: argparse.Namespace) -> int:
    del args
    report = reconcile_reflective_pressure_state()
    _print_json(report)
    return 0 if report["clean"] else 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (OSError, TypeError, ValueError) as exc:
        _print_json(
            {
                "clean": False,
                "error_type": exc.__class__.__name__,
                "error": str(exc),
            }
        )
        return 1


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _parse_tags(value: str) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _non_negative_number(value: str) -> int | float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value_must_be_numeric") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("value_must_be_non_negative")
    if parsed.is_integer():
        return int(parsed)
    return parsed


def _non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value_must_be_non_negative")
    return parsed


def _score_arg(value: str) -> int:
    parsed = int(value)
    if parsed < 0 or parsed > 5:
        raise argparse.ArgumentTypeError("score_must_be_0_to_5")
    return parsed


def _bool_arg(value: str) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError("value_must_be_boolean")


if __name__ == "__main__":
    raise SystemExit(main())
