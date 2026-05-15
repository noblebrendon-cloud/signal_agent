from __future__ import annotations

import os
from pathlib import Path

from app.letters_of_light.weekly_models import (
    WeeklyLetter,
    assert_no_external_action,
)
from app.utils.io_contract import atomic_write_text


ARTIFACT_FILENAMES = {
    "email_preview": "email_preview.md",
    "print_packet": "print_packet.md",
    "jail_packet": "jail_packet.md",
    "human_approval_checklist": "human_approval_checklist.md",
}


def render_email_preview(
    letter: WeeklyLetter,
    *,
    external_action_allowed: bool = False,
    send_externally: bool = False,
) -> str:
    assert_no_external_action(
        external_action_allowed=external_action_allowed,
        send_externally=send_externally,
    )
    subject = f"Letters of Light - {letter.title} ({letter.week_date})"
    preview = _preview_text(letter.body)
    return "\n".join(
        [
            "# Letters of Light Email Preview",
            "",
            "Status: dry-run preview only",
            "External action allowed: false",
            "Send externally: false",
            "",
            f"Subject: {subject}",
            f"Preview: {preview}",
            "",
            "Recipient selection: manual, human-approved contacts only.",
            "",
            "## Body",
            "",
            f"# {letter.title}",
            "",
            f"Week of {letter.week_date}",
            "",
            _scripture_block(letter),
            "",
            letter.body,
            "",
            "## Reflect",
            "",
            _numbered(letter.reflection_questions),
            "",
            "## Closing Prayer",
            "",
            letter.closing_prayer,
            "",
            "## Song Reference",
            "",
            _song_line(letter),
            "",
        ]
    )


def render_print_packet(
    letter: WeeklyLetter,
    *,
    external_action_allowed: bool = False,
) -> str:
    assert_no_external_action(external_action_allowed=external_action_allowed)
    return "\n".join(
        [
            f"# {letter.title}",
            "",
            f"Letters of Light - Week of {letter.week_date}",
            "",
            "## Scripture",
            "",
            _bullets(letter.scripture_refs),
            "",
            "## Letter",
            "",
            letter.body,
            "",
            "## Reflection Questions",
            "",
            _numbered(letter.reflection_questions),
            "",
            "## Closing Prayer",
            "",
            letter.closing_prayer,
            "",
            "## Song For The Week",
            "",
            _song_line(letter),
            "",
            "Printing note: print only after human approval and local material review.",
            "",
        ]
    )


def render_jail_packet(
    letter: WeeklyLetter,
    *,
    external_action_allowed: bool = False,
) -> str:
    assert_no_external_action(external_action_allowed=external_action_allowed)
    return "\n".join(
        [
            f"# {letter.title}",
            "",
            f"Letters of Light jail/in-person packet - Week of {letter.week_date}",
            "",
            "## Opening Framing",
            "",
            "This reading is offered as a peace-centered reflection packet. Participation should be voluntary, respectful, and aligned with facility rules.",
            "",
            "## Scripture",
            "",
            _bullets(letter.scripture_refs),
            "",
            "## Simplified Reading",
            "",
            letter.body,
            "",
            "## Group Discussion Prompts",
            "",
            _numbered(letter.reflection_questions),
            "",
            "## Closing Prayer Or Reflection",
            "",
            letter.closing_prayer,
            "",
            "## Song Sharing Note",
            "",
            f"{_song_line(letter)} Do not play, print lyrics, or distribute media unless the facility and rights/permission rules allow it.",
            "",
            "## Required Human Approval Checklist",
            "",
            "- [ ] Facility permission confirmed",
            "- [ ] Chaplain/coordinator contact confirmed",
            "- [ ] Printed material rules checked",
            "- [ ] Allowed media rules checked",
            "- [ ] Safety/content boundaries reviewed",
            "- [ ] Song/media permission checked before sharing",
            "",
        ]
    )


def render_human_approval_checklist(
    letter: WeeklyLetter,
    *,
    external_action_allowed: bool = False,
) -> str:
    assert_no_external_action(external_action_allowed=external_action_allowed)
    return "\n".join(
        [
            "# Letters of Light Human Approval Checklist",
            "",
            f"Letter ID: {letter.letter_id}",
            f"Title: {letter.title}",
            f"Week: {letter.week_date}",
            f"Current status: {letter.status}",
            "",
            "## Publication",
            "",
            "- [ ] Letter content reviewed",
            "- [ ] Scripture references reviewed",
            "- [ ] Song reference reviewed",
            "- [ ] Audience notes reviewed",
            "- [ ] Status transition approved by human operator",
            "",
            "## Email",
            "",
            "- [ ] Email preview reviewed",
            "- [ ] Recipient/contact selection approved",
            "- [ ] No automated external send configured",
            "- [ ] Any real send will be performed manually or through a later governed sender boundary",
            "",
            "## Print And In-Person",
            "",
            "- [ ] Printable packet reviewed",
            "- [ ] Jail/in-person packet reviewed",
            "- [ ] Facility permission obtained before jail use",
            "- [ ] Chaplain/coordinator contact confirmed",
            "- [ ] Printed material rules followed",
            "- [ ] Song/media permission checked before sharing in facility",
            "",
            "External action allowed: false",
            "Network allowed: false",
            "Irreversible action allowed: false",
            "",
        ]
    )


def write_weekly_artifacts(
    letter: WeeklyLetter,
    *,
    out_dir: str | Path | None = None,
    external_action_allowed: bool = False,
    send_externally: bool = False,
) -> dict[str, str]:
    assert_no_external_action(
        external_action_allowed=external_action_allowed,
        send_externally=send_externally,
    )
    output_dir = Path(out_dir) if out_dir is not None else _default_output_dir(letter)
    output_dir.mkdir(parents=True, exist_ok=True)

    renderers = {
        "email_preview": render_email_preview(letter),
        "print_packet": render_print_packet(letter),
        "jail_packet": render_jail_packet(letter),
        "human_approval_checklist": render_human_approval_checklist(letter),
    }
    written: dict[str, str] = {}
    for key, text in renderers.items():
        path = output_dir / ARTIFACT_FILENAMES[key]
        atomic_write_text(path, text if text.endswith("\n") else f"{text}\n")
        written[key] = str(path)
    return written


def _default_output_dir(letter: WeeklyLetter) -> Path:
    override = os.environ.get("SIGNAL_AGENT_ROOT")
    root = Path(override) if override else Path(__file__).resolve().parents[2]
    return root / "data" / "outputs" / "letters_of_light" / letter.week_date


def _preview_text(text: str) -> str:
    compact = " ".join(text.split())
    if len(compact) <= 160:
        return compact
    return compact[:157].rstrip() + "..."


def _scripture_block(letter: WeeklyLetter) -> str:
    return "\n".join(f"- {ref}" for ref in letter.scripture_refs)


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def _numbered(items: list[str]) -> str:
    return "\n".join(f"{index}. {item}" for index, item in enumerate(items, start=1))


def _song_line(letter: WeeklyLetter) -> str:
    title = letter.song.get("title", "")
    artist = letter.song.get("artist", "")
    reference = letter.song.get("reference") or letter.song.get("link") or letter.song.get("url") or letter.song.get("notes", "")
    byline = f" by {artist}" if artist else ""
    return f"{title}{byline}. Reference: {reference}"
