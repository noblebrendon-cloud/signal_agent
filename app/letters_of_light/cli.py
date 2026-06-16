"""
app/letters_of_light/cli.py — CLI entrypoint for Letters of Light.

Usage:
    python -m app.letters_of_light create --theme "release"
    python -m app.letters_of_light merch-candidate --letter-id <id>
    python -m app.letters_of_light merch-approve --candidate-id <id>
    python -m app.letters_of_light release-scan
"""
from __future__ import annotations

import argparse
import sys

from app.letters_of_light.pipeline import run_pipeline


# Shared facade ownership:
# - create -> letters_of_light_pipeline_core
# - merch-* -> letters_of_light_merch_bridge
# - weekly-diagnostic -> letters_of_light_diagnostic_loop
BRANCH_OWNERSHIP = {
    "create": "letters_of_light_pipeline_core",
    "merch-candidate": "letters_of_light_merch_bridge",
    "merch-approve": "letters_of_light_merch_bridge",
    "weekly-diagnostic": "letters_of_light_diagnostic_loop",
    "release-scan": "letters_of_light_release_gate",
    "release-candidate": "letters_of_light_release_gate",
    "release-approve": "letters_of_light_release_gate",
    "release-export": "letters_of_light_release_gate",
}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m app.letters_of_light",
        description="Letters of Light — Multimedia Artifact Pipeline",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # ── create ─────────────────────────────────────────────────────────────
    create = sub.add_parser("create", help="Generate a full Letter of Light artifact bundle")
    create.add_argument("--theme", required=True, metavar="THEME",
                        help="Theme keyword (e.g. release, discipline, fear, purpose, gratitude)")
    create.add_argument("--seed", metavar="TEXT", default=None,
                        help="Optional seed text to append to the letter body")
    create.add_argument("--text", metavar="TEXT", default=None, dest="manual_text",
                        help="Manual full-body text override")

    # ── merch-candidate ────────────────────────────────────────────────────
    mc = sub.add_parser("merch-candidate",
                        help="Create a merch candidate from a registered letter")
    mc.add_argument("--letter-id", required=True, metavar="ID",
                    help="Letter ID to extract focal phrase from")

    # ── merch-approve ──────────────────────────────────────────────────────
    ma = sub.add_parser("merch-approve",
                        help="Approve a merch candidate and generate merch spec")
    ma.add_argument("--candidate-id", required=True, metavar="ID",
                    help="Candidate ID to approve")

    # ── weekly-diagnostic ──────────────────────────────────────────────────
    wd = sub.add_parser("weekly-diagnostic",
                        help="Run weekly diagnostic layer to emit reports and hooks")
    wd.add_argument("--days", type=int, default=7, metavar="N",
                    help="Number of days to inspect in the ledger (default: 7)")
    wd.add_argument("--out-dir", default="data/state/diagnostics/weekly/", metavar="DIR",
                    help="Output directory (default: data/state/diagnostics/weekly/)")

    rs = sub.add_parser("release-scan", help="Scan letters for public release eligibility")

    rc = sub.add_parser("release-candidate", help="Create release candidate from registered letter")
    rc.add_argument("--letter-id", required=True, metavar="ID")

    ra = sub.add_parser("release-approve", help="Approve eligible release candidate")
    ra.add_argument("--letter-id", required=True, metavar="ID")

    re = sub.add_parser("release-export", help="Export platform-ready campaign package")
    re.add_argument("--letter-id", required=True, metavar="ID")

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.cmd == "create":
        # letters_of_light_pipeline_core
        return _cmd_create(args)
    elif args.cmd == "merch-candidate":
        # letters_of_light_merch_bridge
        return _cmd_merch_candidate(args)
    elif args.cmd == "merch-approve":
        # letters_of_light_merch_bridge
        return _cmd_merch_approve(args)
    elif args.cmd == "weekly-diagnostic":
        # letters_of_light_diagnostic_loop
        return _cmd_weekly_diagnostic(args)
    elif args.cmd == "release-scan":
        # letters_of_light_release_gate
        return _cmd_release_scan(args)
    elif args.cmd == "release-candidate":
        # letters_of_light_release_gate
        return _cmd_release_candidate(args)
    elif args.cmd == "release-approve":
        # letters_of_light_release_gate
        return _cmd_release_approve(args)
    elif args.cmd == "release-export":
        # letters_of_light_release_gate
        return _cmd_release_export(args)

    parser.print_help()
    return 1


def _cmd_create(args: argparse.Namespace) -> int:
    print("LETTERS OF LIGHT PIPELINE")
    print(f"  Theme: {args.theme}")
    print()

    try:
        letter = run_pipeline(
            theme=args.theme,
            seed=args.seed,
            manual_text=args.manual_text,
        )
    except Exception as exc:
        print(f"ERROR: Pipeline failed: {exc}", file=sys.stderr)
        return 1

    if letter.lifecycle_state == "failed":
        print(f"PIPELINE FAILED at stage:")
        for key in ("text_error", "voice_error", "music_error",
                     "visual_error", "compose_error", "interaction_error",
                     "registration_error"):
            if key in letter.metadata:
                print(f"  {key}: {letter.metadata[key]}")
        print(f"  Letter ID: {letter.letter_id}")
        return 1

    print("LETTER CREATED:")
    print(f"  ID:          {letter.letter_id}")
    print(f"  Title:       {letter.title}")
    print(f"  Theme:       {letter.theme}")
    print(f"  State:       {letter.lifecycle_state}")
    print(f"  Video:       {letter.video_path}")
    print(f"  Audio:       {letter.audio_path}")
    print(f"  Music:       {letter.music_path}")
    print(f"  Visual:      {letter.visual_path}")
    print(f"  Scripture:   {letter.scripture_ref}")
    print(f"  Questions:   {letter.interaction_schema.get('question_count', 0)}")
    print(f"  Platforms:   {', '.join(letter.routing_payloads.keys())}")
    return 0


def _cmd_merch_candidate(args: argparse.Namespace) -> int:
    from app.letters_of_light.merch_bridge import (
        create_merch_candidate, BridgeError, _load_candidate,
    )
    from app.letters_of_light.pipeline import _load_letter

    print("MERCH CANDIDATE BRIDGE")
    print(f"  Letter ID: {args.letter_id}")
    print()

    letter = _load_letter(args.letter_id)
    if letter is None:
        print(f"ERROR: Letter not found: {args.letter_id}", file=sys.stderr)
        return 1

    try:
        candidate = create_merch_candidate(letter)
    except BridgeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("MERCH CANDIDATE:")
    print(f"  Candidate ID:  {candidate.candidate_id}")
    print(f"  Focal Phrase:  \"{candidate.focal_phrase}\"")
    print(f"  Theme:         {candidate.theme}")
    print(f"  Source Letter:  {candidate.source_artifact_id}")
    print(f"  Phrase Hash:   {candidate.phrase_hash[:16]}...")
    print(f"  Status:        {candidate.status}")
    print(f"  Style:         {candidate.suggested_style}")
    return 0


def _cmd_merch_approve(args: argparse.Namespace) -> int:
    from pathlib import Path
    from app.letters_of_light.merch_bridge import (
        approve_candidate, generate_merch_spec,
        BridgeError, CandidateTransitionError, _load_candidate,
    )
    from app.letters_of_light.merch_design import generate_merch_design

    print("MERCH APPROVAL")
    print(f"  Candidate ID: {args.candidate_id}")
    print()

    candidate = _load_candidate(args.candidate_id)
    if candidate is None:
        print(f"ERROR: Candidate not found: {args.candidate_id}", file=sys.stderr)
        return 1

    # Step 1: Approve
    try:
        candidate = approve_candidate(args.candidate_id)
    except (BridgeError, CandidateTransitionError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"  Status:        {candidate.status}")

    # Step 2: Generate design
    design_dir = Path(f"data/state/merch_candidates/{args.candidate_id}")
    design_dir.mkdir(parents=True, exist_ok=True)

    print(f"  Generating design...")
    design_path = generate_merch_design(
        phrase=candidate.focal_phrase,
        theme=candidate.theme,
        output_dir=design_dir,
    )
    print(f"  Design:        {design_path}")

    # Step 3: Generate merch spec
    try:
        spec = generate_merch_spec(candidate, str(design_path))
    except BridgeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print()
    print("MERCH SPEC GENERATED:")
    print(f"  Title:         \"{spec['title']}\"")
    print(f"  Description:   {spec['description']}")
    print(f"  Template:      {spec['template_id']}")
    print(f"  Price:         ${spec['retail_price']}")
    print(f"  Design:        {spec['design_path']}")
    print(f"  Sizes:         {', '.join(spec['variant_config']['sizes'])}")
    print(f"  Colors:        {', '.join(spec['variant_config']['colors'])}")
    print()
    print("  → Ready for: run_merch_pipeline(spec)")
    return 0



def _cmd_weekly_diagnostic(args: argparse.Namespace) -> int:
    from pathlib import Path
    import json
    from datetime import datetime, timezone

    # Import the newly implemented functions
    from app.letters_of_light.weekly_diagnostic import generate_weekly_report
    from app.letters_of_light.reporting import generate_internal_memo
    from app.letters_of_light.memo_hooks import (
        generate_linkedin_hook, generate_youtube_hook_json, generate_youtube_script_seed
    )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"WEEKLY DIAGNOSTIC")
    print(f"  Days: {args.days}")
    print(f"  Out:  {out_dir}")
    print()

    # Generate data
    report_data = generate_weekly_report(days=args.days, out_dir=out_dir)
    period_start = report_data.get("period", {}).get("start", "date")

    # Generate Hooks
    generate_internal_memo(report_data, out_dir=out_dir)
    generate_linkedin_hook(report_data, out_dir=out_dir)
    generate_youtube_hook_json(report_data, out_dir=out_dir)
    generate_youtube_script_seed(report_data, out_dir=out_dir)

    print(f"  Report:  {out_dir / f'{period_start}_report.json'}")
    print(f"  Memo:    {out_dir / f'{period_start}_report.md'}")
    print(f"  LinkIn:  {out_dir / f'{period_start}_linkedin.md'}")
    print(f"  YT Hook: {out_dir / f'{period_start}_youtube_hook.json'}")
    print(f"  YT Seed: {out_dir / f'{period_start}_youtube_script_seed.md'}")

    return 0


def _cmd_release_scan(args: argparse.Namespace) -> int:
    import json
    from app.letters_of_light.release import scan_letters

    rows = scan_letters()
    print(json.dumps(rows, indent=2))
    return 0


def _cmd_release_candidate(args: argparse.Namespace) -> int:
    import json
    from app.letters_of_light.release import create_release_candidate

    release = create_release_candidate(args.letter_id)
    print(json.dumps(release, indent=2))
    return 0


def _cmd_release_approve(args: argparse.Namespace) -> int:
    import json
    from app.letters_of_light.release import approve_release

    release = approve_release(args.letter_id)
    print(json.dumps(release, indent=2))
    return 0


def _cmd_release_export(args: argparse.Namespace) -> int:
    import json
    from app.letters_of_light.release import export_campaign

    manifest = export_campaign(args.letter_id)
    print(json.dumps(manifest, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
