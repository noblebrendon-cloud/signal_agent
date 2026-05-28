from __future__ import annotations

import yaml
from pathlib import Path

from app.bookgen.project_compile import compile_project, compile_project_to_file
from app.bookgen.render import render_from_spec


def test_communication_architecture_project_compiles_to_render_spec(tmp_path: Path) -> None:
    project_path = Path("books/projects/communication_architecture/book_project.yaml")

    spec = compile_project(project_path)

    assert spec["meta"]["title"] == "The Architecture of Influence"
    assert len(spec["chapters"]) == 16
    assert spec["chapters"][11]["title"] == "AI and the Industrialization of Persuasion"
    assert spec["chapters"][11]["part"] == "III - The Collapse of Modern Discourse"
    assert "# AI and the Industrialization of Persuasion" in spec["chapters"][11]["body"]
    assert "communication is not merely informational" in spec["chapters"][0]["body"].lower()
    assert "the invisible structure behind persuasion" in spec["chapters"][1]["body"].lower()
    assert "language creates terrain" in spec["chapters"][2]["body"].lower()
    assert "attention architecture" in spec["chapters"][3]["body"].lower()
    assert "coercion narrows agency" in spec["chapters"][4]["body"].lower()
    assert "resistance is agency responding to pressure" in spec["chapters"][5]["body"].lower()
    assert "narrative gravity is not the same as truth" in spec["chapters"][6]["body"].lower()
    assert "clarification versus capture" in spec["chapters"][7]["body"].lower()
    assert "emotional velocity" in spec["chapters"][8]["body"].lower()
    assert "procedural trust is not obedience" in spec["chapters"][9]["body"].lower()
    assert "identity is not the enemy" in spec["chapters"][10]["body"].lower()
    assert "ai does not invent the discourse problem" in spec["chapters"][11]["body"].lower()
    assert "the failure is not only bad messages" in spec["chapters"][12]["body"].lower()
    assert "coherence is continuity under pressure" in spec["chapters"][13]["body"].lower()
    assert "governed communication is the attempt to make the structure match the claim" in spec["chapters"][14]["body"].lower()
    assert "legitimate systems are not systems that never fail" in spec["chapters"][15]["body"].lower()
    assert "DRAFT CHAPTER PLACEHOLDER" not in "\n".join(
        chapter["body"] for chapter in spec["chapters"]
    )
    assert spec["project"]["slug"] == "communication_architecture"

    outputs = render_from_spec(
        spec=spec,
        templates_dir=Path("app/bookgen/templates"),
        out_dir=tmp_path,
    )
    rendered = outputs.book_md.read_text(encoding="utf-8")

    assert outputs.book_md.exists()
    assert outputs.cover_front_txt.exists()
    assert outputs.letter_one_sentence_txt.exists()
    assert rendered.count("{#chapter-") == 16
    assert "DRAFT CHAPTER PLACEHOLDER" not in rendered


def test_project_compile_writes_yaml_spec_with_markdown_body(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    chapters_dir = project_dir / "chapters"
    chapters_dir.mkdir(parents=True)
    chapter_path = chapters_dir / "01_demo.md"
    chapter_path.write_text(
        "# Exact Demo Title\n\n"
        "Part: I - Demo Part\n"
        "Status: Draft placeholder\n\n"
        "## Draft Body\n\n"
        "DRAFT CHAPTER PLACEHOLDER. Markdown body included.",
        encoding="utf-8",
    )
    project_path = project_dir / "book_project.yaml"
    project_path.write_text(
        "\n".join(
            [
                "slug: demo_project",
                "title: Exact Demo Book",
                "subtitle: Test Subtitle",
                "author: Test Author",
                "year: '2026'",
                "copyright_holder: Test Author",
                "front_matter:",
                "  preface: Demo preface.",
                "chapters:",
                "- number: 1",
                "  title: Exact Demo Title",
                "  part: I - Demo Part",
                "  source: chapters/01_demo.md",
                "end_matter:",
                "  endnote: Demo endnote.",
                "letter:",
                "  one_sentence: Demo letter.",
            ]
        ),
        encoding="utf-8",
    )
    out_path = tmp_path / "demo_project.yaml"

    compile_project_to_file(project_path, out_path)

    emitted = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    assert emitted["meta"]["title"] == "Exact Demo Book"
    assert emitted["chapters"][0]["title"] == "Exact Demo Title"
    assert emitted["chapters"][0]["part"] == "I - Demo Part"
    assert "# Exact Demo Title" in emitted["chapters"][0]["body"]
    assert "Markdown body included." in emitted["chapters"][0]["body"]
