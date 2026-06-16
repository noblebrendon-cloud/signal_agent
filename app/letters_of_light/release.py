"""
app/letters_of_light/release.py - Public release gate for Letters of Light.

This module does not generate content.
This module does not post directly to social APIs in V1.

It scans registered Letter folders, validates release eligibility,
creates release.json, and exports platform-ready campaign files.

Boundary:
    pipeline.py      -> artifact generation + registration
    routing.py       -> platform payload preparation only
    release.py       -> public transformation gate
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


PUBLIC_SCORE_THRESHOLD = 24
PUBLIC_AUDIO_THRESHOLD = 4

RELEASE_STATES = {
    "candidate",
    "draft",
    "approved",
    "scheduled",
    "exported",
    "publishing",
    "published",
    "partial_failure",
    "failed",
    "manual_required",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_root() -> Path:
    override = os.environ.get("SIGNAL_AGENT_ROOT")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent.parent


def _letters_root() -> Path:
    return _get_root() / "data" / "state" / "letters_of_light"


def _letter_dir(letter_id: str) -> Path:
    return _letters_root() / letter_id


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _coerce_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _resolve_artifact_path(path_str: str) -> Path:
    path = Path(path_str)
    if path.is_absolute():
        return path
    return _get_root() / path


def _file_ok(path_str: str) -> bool:
    if not path_str:
        return False
    p = _resolve_artifact_path(path_str)
    return p.exists() and p.is_file() and p.stat().st_size > 0


@dataclass
class ReleaseCheck:
    eligible: bool
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "eligible": self.eligible,
            "reasons": self.reasons,
        }


def check_release_eligibility(letter_id: str) -> ReleaseCheck:
    d = _letter_dir(letter_id)

    letter_path = d / "letter.json"
    routing_path = d / "routing.json"
    interaction_path = d / "interaction.json"

    letter = _read_json(letter_path)
    routing = _read_json(routing_path)
    interaction = _read_json(interaction_path)

    reasons: List[str] = []

    if not letter:
        reasons.append("letter.json missing or unreadable")
        return ReleaseCheck(False, reasons)

    if letter.get("lifecycle_state") != "registered":
        reasons.append(f"lifecycle_state is not registered: {letter.get('lifecycle_state')}")

    evaluation = letter.get("evaluation", {})
    if evaluation.get("decision") != "accept":
        reasons.append(f"evaluation decision is not accept: {evaluation.get('decision')}")

    total = _coerce_int(evaluation.get("total"))
    if total < PUBLIC_SCORE_THRESHOLD:
        reasons.append(f"evaluation total below public threshold: {total} < {PUBLIC_SCORE_THRESHOLD}")

    audio_alignment = _coerce_int(evaluation.get("audio_alignment"))
    if audio_alignment < PUBLIC_AUDIO_THRESHOLD:
        reasons.append(
            f"audio_alignment below public threshold: {audio_alignment} < {PUBLIC_AUDIO_THRESHOLD}"
        )

    video_path = letter.get("video_path", "")
    if not _file_ok(video_path):
        reasons.append(f"final video missing or empty: {video_path}")

    visual_path = letter.get("visual_path", "")
    if not _file_ok(visual_path):
        reasons.append(f"visual missing or empty: {visual_path}")

    if not routing:
        reasons.append("routing.json missing or unreadable")

    if not interaction:
        reasons.append("interaction.json missing or unreadable")

    return ReleaseCheck(len(reasons) == 0, reasons)


def create_release_candidate(letter_id: str, campaign_id: Optional[str] = None) -> Dict[str, Any]:
    d = _letter_dir(letter_id)
    letter = _read_json(d / "letter.json")
    routing = _read_json(d / "routing.json")
    interaction = _read_json(d / "interaction.json")
    existing = _read_json(d / "release.json")

    if not letter:
        raise RuntimeError(f"Letter not found: {letter_id}")

    check = check_release_eligibility(letter_id)

    if campaign_id is None:
        safe_theme = (letter.get("theme") or "letter").strip().lower().replace(" ", "-")
        campaign_id = existing.get("campaign_id") or f"lol-{safe_theme}-{letter_id[:8]}"

    created_at = existing.get("created_at") or _utc_now()
    now = _utc_now()
    previous_state = existing.get("release_state")
    protected_states = {"approved", "scheduled", "exported", "publishing", "published"}
    if not check.eligible:
        release_state = "manual_required"
        approved = False
    elif previous_state in protected_states:
        release_state = previous_state
        approved = bool(existing.get("approved", False))
    else:
        release_state = "candidate"
        approved = False

    release = {
        "letter_id": letter_id,
        "campaign_id": campaign_id,
        "release_state": release_state,
        "approved": approved,
        "scheduled_at": existing.get("scheduled_at"),
        "canonical_url": existing.get("canonical_url"),
        "eligibility": check.to_dict(),
        "title": letter.get("title", ""),
        "theme": letter.get("theme", ""),
        "scripture_ref": letter.get("scripture_ref", ""),
        "evaluation": letter.get("evaluation", {}),
        "assets": {
            "video_path": letter.get("video_path", ""),
            "visual_path": letter.get("visual_path", ""),
            "audio_path": letter.get("audio_path", ""),
            "music_path": letter.get("music_path", ""),
        },
        "targets": {
            "site": {
                "enabled": True,
                "status": "pending",
                "url": None,
            },
            "youtube": {
                "enabled": True,
                "status": "pending",
                "platform_id": None,
                "url": None,
                "payload": routing.get("youtube", {}),
            },
            "facebook": {
                "enabled": True,
                "status": "pending",
                "platform_id": None,
                "url": None,
                "payload": routing.get("facebook", {}),
            },
            "instagram": {
                "enabled": True,
                "status": "pending",
                "platform_id": None,
                "url": None,
                "payload": {
                    "type": "reel",
                    "caption": routing.get("facebook", {}).get("message", ""),
                    "video_path": letter.get("video_path", ""),
                    "hashtags": routing.get("facebook", {}).get("hashtags", []),
                },
            },
            "x": {
                "enabled": True,
                "status": "pending",
                "platform_id": None,
                "url": None,
                "payload": routing.get("x", {}),
            },
            "substack": {
                "enabled": False,
                "status": "pending",
                "platform_id": None,
                "url": None,
                "payload": routing.get("substack", {}),
            },
        },
        "interaction_schema": interaction,
        "events": existing.get("events", []) + [
            {
                "event_type": "ReleaseCandidateCreated",
                "created_at": now,
                "eligible": check.eligible,
                "reasons": check.reasons,
            }
        ],
        "created_at": created_at,
        "updated_at": now,
    }

    if existing.get("approved_at"):
        release["approved_at"] = existing["approved_at"]

    _write_json(d / "release.json", release)
    return release


def approve_release(letter_id: str) -> Dict[str, Any]:
    d = _letter_dir(letter_id)
    path = d / "release.json"
    release = _read_json(path)

    if not release:
        release = create_release_candidate(letter_id)

    check = check_release_eligibility(letter_id)
    release["eligibility"] = check.to_dict()

    if not check.eligible:
        release["release_state"] = "manual_required"
        release["approved"] = False
        release["updated_at"] = _utc_now()
        release.setdefault("events", []).append(
            {
                "event_type": "ReleaseApprovalBlocked",
                "created_at": _utc_now(),
                "reasons": check.reasons,
            }
        )
        _write_json(path, release)
        return release

    previous_state = release.get("release_state")
    if previous_state in {"scheduled", "exported", "publishing", "published"}:
        release["release_state"] = previous_state
    else:
        release["release_state"] = "approved"
    release["approved"] = True
    release["approved_at"] = _utc_now()
    release["updated_at"] = _utc_now()
    release.setdefault("events", []).append(
        {
            "event_type": "ReleaseApproved",
            "created_at": _utc_now(),
        }
    )

    _write_json(path, release)
    return release


def export_campaign(letter_id: str) -> Dict[str, Any]:
    d = _letter_dir(letter_id)
    release_path = d / "release.json"
    release = _read_json(release_path)

    if not release:
        release = create_release_candidate(letter_id)

    if not release.get("approved"):
        raise RuntimeError("Release must be approved before export")

    check = check_release_eligibility(letter_id)
    if not check.eligible:
        release["release_state"] = "manual_required"
        release["approved"] = False
        release["eligibility"] = check.to_dict()
        release["updated_at"] = _utc_now()
        release.setdefault("events", []).append(
            {
                "event_type": "ReleaseExportBlocked",
                "created_at": _utc_now(),
                "reasons": check.reasons,
            }
        )
        _write_json(release_path, release)
        raise RuntimeError("Release is no longer eligible for export")

    letter = _read_json(d / "letter.json")
    routing = _read_json(d / "routing.json")
    interaction = _read_json(d / "interaction.json")

    export_dir = d / "release_export"
    export_dir.mkdir(parents=True, exist_ok=True)

    title = letter.get("title", "")
    body = letter.get("text", "")
    scripture = letter.get("scripture_ref", "")
    questions = interaction.get("questions", [])

    canonical_slug = letter_id
    canonical_url = release.get("canonical_url") or f"https://brendonrcoleman.com/letters/{canonical_slug}"

    reflect_items = "\n".join([f"{i + 1}. {q}" for i, q in enumerate(questions)])
    site_md = (
        f"# {title}\n\n"
        f"{body}\n\n"
        f"---\n\n"
        f"*{scripture}*\n\n"
        f"## Reflect\n\n"
        f"{reflect_items}\n"
    )

    facebook = routing.get("facebook", {})
    youtube = routing.get("youtube", {})
    x_payload = routing.get("x", {})
    substack = routing.get("substack", {})

    instagram_caption = (
        facebook.get("message", "")
        + "\n\n"
        + " ".join(facebook.get("hashtags", []))
        + "\n\n"
        + canonical_url
    )

    x_thread = "\n\n---\n\n".join(x_payload.get("tweets", []))
    if canonical_url not in x_thread:
        x_thread += f"\n\n{canonical_url}"

    _write_text(export_dir / "site.md", site_md)
    _write_text(export_dir / "facebook.txt", facebook.get("message", "") + f"\n\n{canonical_url}")
    _write_text(export_dir / "instagram.txt", instagram_caption)
    _write_text(export_dir / "x_thread.txt", x_thread)
    _write_text(export_dir / "youtube_title.txt", youtube.get("title", title))
    _write_text(export_dir / "youtube_description.txt", youtube.get("description", "") + f"\n\n{canonical_url}")
    _write_text(export_dir / "substack.md", substack.get("body_markdown", site_md))

    asset_manifest = {
        "letter_id": letter_id,
        "campaign_id": release.get("campaign_id"),
        "canonical_url": canonical_url,
        "video_path": letter.get("video_path", ""),
        "visual_path": letter.get("visual_path", ""),
        "files": {
            "site": str(export_dir / "site.md"),
            "facebook": str(export_dir / "facebook.txt"),
            "instagram": str(export_dir / "instagram.txt"),
            "x": str(export_dir / "x_thread.txt"),
            "youtube_title": str(export_dir / "youtube_title.txt"),
            "youtube_description": str(export_dir / "youtube_description.txt"),
            "substack": str(export_dir / "substack.md"),
        },
        "created_at": _utc_now(),
    }
    _write_json(export_dir / "asset_manifest.json", asset_manifest)

    video_path = _resolve_artifact_path(letter.get("video_path", ""))
    visual_path = _resolve_artifact_path(letter.get("visual_path", ""))

    if video_path.exists():
        shutil.copy2(video_path, export_dir / "final.mp4")
    if visual_path.exists():
        shutil.copy2(visual_path, export_dir / "visual.png")

    release["release_state"] = "exported"
    release["canonical_url"] = canonical_url
    release["eligibility"] = check.to_dict()
    release["updated_at"] = _utc_now()
    release.setdefault("events", []).append(
        {
            "event_type": "ReleaseExported",
            "created_at": _utc_now(),
            "export_dir": str(export_dir),
            "canonical_url": canonical_url,
        }
    )
    _write_json(release_path, release)

    return asset_manifest


def scan_letters() -> List[Dict[str, Any]]:
    root = _letters_root()
    results: List[Dict[str, Any]] = []

    if not root.exists():
        return results

    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue

        letter_path = d / "letter.json"
        if not letter_path.exists():
            continue

        letter = _read_json(letter_path)
        if not letter:
            continue

        letter_id = letter.get("letter_id") or d.name
        check = check_release_eligibility(letter_id)
        release = _read_json(d / "release.json")

        results.append(
            {
                "letter_id": letter_id,
                "title": letter.get("title", ""),
                "theme": letter.get("theme", ""),
                "lifecycle_state": letter.get("lifecycle_state", ""),
                "evaluation_total": letter.get("evaluation", {}).get("total"),
                "audio_alignment": letter.get("evaluation", {}).get("audio_alignment"),
                "eligible": check.eligible,
                "reasons": check.reasons,
                "release_state": release.get("release_state") if release else "unseen",
                "video_path": letter.get("video_path", ""),
            }
        )

    return results


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.letters_of_light.release",
        description="Letters of Light public release gate",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("scan", help="Scan registered letters and show release eligibility")

    candidate = sub.add_parser("candidate", help="Create release.json for a letter")
    candidate.add_argument("--letter-id", required=True)

    approve = sub.add_parser("approve", help="Approve a release candidate")
    approve.add_argument("--letter-id", required=True)

    export = sub.add_parser("export", help="Export platform-ready campaign package")
    export.add_argument("--letter-id", required=True)

    args = parser.parse_args(argv)

    if args.cmd == "scan":
        rows = scan_letters()
        print(json.dumps(rows, indent=2))
        return 0

    if args.cmd == "candidate":
        release = create_release_candidate(args.letter_id)
        print(json.dumps(release, indent=2))
        return 0

    if args.cmd == "approve":
        release = approve_release(args.letter_id)
        print(json.dumps(release, indent=2))
        return 0

    if args.cmd == "export":
        manifest = export_campaign(args.letter_id)
        print(json.dumps(manifest, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
