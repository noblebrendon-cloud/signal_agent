from __future__ import annotations

from pathlib import Path

import pytest

from app.letters_of_light.weekly_models import WeeklyExternalActionError, load_weekly_letter
from app.letters_of_light.weekly_render import (
    render_email_preview,
    render_human_approval_checklist,
    render_jail_packet,
    render_print_packet,
    write_weekly_artifacts,
)


CANONICAL_LETTER = Path("docs/letters_of_light/letters/2026-05-17.md")


def test_email_preview_rendering() -> None:
    letter = load_weekly_letter(CANONICAL_LETTER)
    rendered = render_email_preview(letter)

    assert "Subject: Letters of Light - Peace For The Next Step (2026-05-17)" in rendered
    assert "External action allowed: false" in rendered
    assert "Send externally: false" in rendered
    assert "Recipient selection: manual, human-approved contacts only." in rendered


def test_printable_packet_rendering() -> None:
    letter = load_weekly_letter(CANONICAL_LETTER)
    rendered = render_print_packet(letter)

    assert "# Peace For The Next Step" in rendered
    assert "## Scripture" in rendered
    assert "## Reflection Questions" in rendered
    assert "Printing note: print only after human approval" in rendered


def test_jail_packet_rendering() -> None:
    letter = load_weekly_letter(CANONICAL_LETTER)
    rendered = render_jail_packet(letter)

    assert "jail/in-person packet" in rendered
    assert "Facility permission confirmed" in rendered
    assert "Song Sharing Note" in rendered
    assert "Do not play, print lyrics, or distribute media" in rendered


def test_human_approval_checklist_rendering() -> None:
    letter = load_weekly_letter(CANONICAL_LETTER)
    rendered = render_human_approval_checklist(letter)

    assert "Letters of Light Human Approval Checklist" in rendered
    assert "No automated external send configured" in rendered
    assert "Facility permission obtained before jail use" in rendered
    assert "External action allowed: false" in rendered


def test_no_external_action_allowed_by_default(tmp_path: Path) -> None:
    letter = load_weekly_letter(CANONICAL_LETTER)
    paths = write_weekly_artifacts(letter, out_dir=tmp_path)

    assert sorted(paths) == [
        "email_preview",
        "human_approval_checklist",
        "jail_packet",
        "print_packet",
    ]
    assert (tmp_path / "email_preview.md").exists()
    assert (tmp_path / "print_packet.md").exists()
    assert (tmp_path / "jail_packet.md").exists()
    assert (tmp_path / "human_approval_checklist.md").exists()


def test_attempt_to_send_externally_fails_closed() -> None:
    letter = load_weekly_letter(CANONICAL_LETTER)

    with pytest.raises(WeeklyExternalActionError, match="external_action_blocked"):
        render_email_preview(letter, send_externally=True)
