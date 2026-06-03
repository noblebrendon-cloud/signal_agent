from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict

import yaml

from .spec import find_unresolved_placeholders, load_spec


def main() -> int:
    parser = argparse.ArgumentParser(prog="bookgen-typeset", description="Typeset a rendered book markdown file into PDF.")
    parser.add_argument("--spec", required=True, help="Path to YAML spec file.")
    parser.add_argument("--input", required=True, help="Rendered markdown input path.")
    parser.add_argument("--output", required=True, help="Output PDF path.")
    parser.add_argument("--profile", default="paperback_6x9", help="Layout profile name or YAML path.")

    args = parser.parse_args()

    spec_path = Path(args.spec).resolve()
    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()

    spec = load_spec(spec_path)
    profile = load_layout_profile(args.profile)

    if not input_path.exists():
        raise SystemExit(f"Input markdown not found: {input_path}")

    markdown = input_path.read_text(encoding="utf-8")
    validate_markdown(markdown, spec, input_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    run_pandoc(input_path, output_path, spec, profile)
    validate_output_pdf(output_path)

    print(f"[OK] Wrote {output_path}")
    return 0


def load_layout_profile(profile_name: str) -> Dict[str, Any]:
    candidate = Path(profile_name)
    if candidate.exists():
        profile_path = candidate.resolve()
    else:
        profile_path = (Path(__file__).parent / "layout_profiles" / f"{profile_name}.yaml").resolve()
    if not profile_path.exists():
        raise SystemExit(f"Layout profile not found: {profile_name}")

    with profile_path.open("r", encoding="utf-8") as handle:
        profile = yaml.safe_load(handle) or {}
    if not isinstance(profile, dict):
        raise SystemExit(f"Layout profile must be a YAML mapping: {profile_path}")
    return profile


def validate_markdown(markdown: str, spec: Dict[str, Any], input_path: Path) -> None:
    unresolved = find_unresolved_placeholders(markdown)
    if unresolved:
        placeholder_list = ", ".join(unresolved)
        raise SystemExit(f"Unresolved placeholders remain in {input_path}: {placeholder_list}")

    title = str(spec.get("meta", {}).get("title", "")).strip()
    if not title or title not in markdown:
        raise SystemExit(f"Book title is missing from rendered markdown: {input_path}")

    expected_chapter_count = len(spec.get("chapters", []))
    actual_chapter_count = markdown.count("{#chapter-")
    if expected_chapter_count != actual_chapter_count:
        raise SystemExit(
            "Rendered chapter count does not match spec: "
            f"expected {expected_chapter_count}, found {actual_chapter_count}"
        )


def validate_output_pdf(output_path: Path) -> None:
    if not output_path.exists():
        raise SystemExit(f"Expected PDF was not created: {output_path}")
    if output_path.stat().st_size <= 0:
        raise SystemExit(f"PDF is empty: {output_path}")


def run_pandoc(input_path: Path, output_path: Path, spec: Dict[str, Any], profile: Dict[str, Any]) -> None:
    metadata = build_layout_metadata(spec, profile)
    with tempfile.TemporaryDirectory(prefix="bookgen-typeset-") as temp_dir:
        metadata_path = Path(temp_dir) / "layout.yaml"
        metadata_path.write_text(yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True), encoding="utf-8")

        cmd = [
            "pandoc",
            str(input_path),
            "--standalone",
            "--from=markdown+raw_tex+hard_line_breaks",
            "--top-level-division=chapter",
            "--metadata-file",
            str(metadata_path),
            "--pdf-engine",
            str(profile.get("pdf_engine", "xelatex")),
            "--output",
            str(output_path),
        ]

        try:
            subprocess.run(cmd, check=True, text=True, capture_output=True)
        except FileNotFoundError as exc:
            raise SystemExit(f"Pandoc executable not found: {exc}") from exc
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            detail = f" Pandoc stderr: {stderr}" if stderr else ""
            raise SystemExit(f"Pandoc typesetting failed with exit code {exc.returncode}.{detail}") from exc


def build_layout_metadata(spec: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    meta = spec.get("meta", {})
    latex = profile.get("latex") or {}
    paragraphs = profile.get("paragraphs") or {}
    classoptions = list(profile.get("classoptions") or [])
    chapter_page_behavior = profile.get("chapter_page_behavior")
    if chapter_page_behavior and chapter_page_behavior not in classoptions:
        classoptions.append(chapter_page_behavior)

    metadata: Dict[str, Any] = {
        # Pandoc's default LaTeX template emits \maketitle when `title` is set.
        # Use metadata-only keys so the PDF keeps title/author metadata while
        # the rendered Markdown owns the visible title page.
        "title-meta": meta.get("title", ""),
        "author-meta": meta.get("author", ""),
        "date-meta": meta.get("year", ""),
        "rights": meta.get("copyright_line", ""),
        "documentclass": profile.get("documentclass", "book"),
        "classoption": classoptions,
        "fontsize": profile.get("fontsize", "11pt"),
        "linestretch": profile.get("linestretch", 1.0),
        "geometry": list(profile.get("geometry") or []),
        "header-includes": build_header_includes(paragraphs, latex),
    }

    if profile.get("mainfont"):
        metadata["mainfont"] = profile["mainfont"]

    return metadata


def build_header_includes(paragraphs: Dict[str, Any], latex: Dict[str, Any]) -> list[str]:
    indent = paragraphs.get("indent", "1.2em")
    skip = paragraphs.get("skip", "0pt")
    toc_depth = latex.get("toc_depth", 0)
    widow_penalty = latex.get("widow_penalty", 10000)
    club_penalty = latex.get("club_penalty", 10000)
    display_widow_penalty = latex.get("display_widow_penalty", 10000)

    return [
        r"\raggedbottom",
        r"\frenchspacing",
        r"\setlength{\emergencystretch}{2em}",
        rf"\setlength{{\parindent}}{{{indent}}}",
        rf"\setlength{{\parskip}}{{{skip}}}",
        rf"\setcounter{{tocdepth}}{{{toc_depth}}}",
        rf"\widowpenalty={widow_penalty}",
        rf"\clubpenalty={club_penalty}",
        rf"\displaywidowpenalty={display_widow_penalty}",
    ]


if __name__ == "__main__":
    raise SystemExit(main())
