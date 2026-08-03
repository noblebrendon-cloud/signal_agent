from __future__ import annotations

from pathlib import Path

from app.bookgen.render import render_from_spec
from app.bookgen.typeset import build_layout_metadata


def test_render_from_spec_smoke(tmp_path: Path) -> None:
    spec = {
        "meta": {
            "title": "Hybrid Chapter",
            "subtitle": "Smoke Test",
            "author": "Signal Agent",
            "year": "2026",
            "copyright_holder": "Signal Agent",
        },
        "front_matter": {
            "cover_blurb": "Back-cover only.",
            "preface": "Render smoke test.",
        },
        "chapters": [
            {
                "title": "Hybrid Chapter",
                "body": (
                    "## Scene\n\n"
                    "The room stayed quiet while the lights kept blinking.\n\n"
                    "## Break\n\n"
                    "Then the screen went dark.\n\n"
                    "## Extraction\n\n"
                    "Governing principle: Keep the handoff explicit.\n\n"
                    "## Carry Forward\n\n"
                    "Carry this forward by preserving the signal before abstracting the system."
                ),
            }
        ],
        "end_matter": {
            "endnote": "Smoke complete.",
        },
        "letter": {
            "one_sentence": "Render smoke test.",
        },
    }

    outputs = render_from_spec(
        spec=spec,
        templates_dir=Path("app/bookgen/templates"),
        out_dir=tmp_path,
    )

    rendered = outputs.book_md.read_text(encoding="utf-8")

    assert outputs.book_md.exists()
    assert outputs.cover_front_txt.exists()
    assert outputs.letter_one_sentence_txt.exists()
    assert "Cover Blurb" not in rendered
    assert "Back-cover only." not in rendered
    assert "# Hybrid Chapter {#chapter-1}" in rendered
    assert "## Scene" in rendered
    assert "## Carry Forward" in rendered


def test_typeset_metadata_does_not_trigger_pandoc_title_page() -> None:
    spec = {
        "meta": {
            "title": "The Architecture of Influence",
            "author": "Brendon R Coleman",
            "year": "2026",
        }
    }

    metadata = build_layout_metadata(spec, profile={})

    assert metadata["title-meta"] == "The Architecture of Influence"
    assert metadata["author-meta"] == "Brendon R Coleman"
    assert metadata["date-meta"] == "2026"
    assert "title" not in metadata
    assert "author" not in metadata
    assert "date" not in metadata
