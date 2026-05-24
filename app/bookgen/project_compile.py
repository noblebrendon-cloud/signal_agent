from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict

import yaml


class _LiteralSafeDumper(yaml.SafeDumper):
    pass


def _represent_str(dumper: yaml.SafeDumper, value: str) -> yaml.ScalarNode:
    if "\n" in value:
        return dumper.represent_scalar("tag:yaml.org,2002:str", value, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", value)


_LiteralSafeDumper.add_representer(str, _represent_str)


def load_project_manifest(project_path: Path) -> Dict[str, Any]:
    with project_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError("Project manifest must be a YAML mapping/object at the top level.")
    return data


def compile_project(project_path: Path) -> Dict[str, Any]:
    project_path = project_path.resolve()
    manifest = load_project_manifest(project_path)
    project_dir = project_path.parent

    slug = _required_str(manifest, "slug")
    title = _required_str(manifest, "title")
    chapters_manifest = manifest.get("chapters")
    if not isinstance(chapters_manifest, list) or not chapters_manifest:
        raise ValueError("Project manifest must include a non-empty chapters list.")

    meta = {
        "title": title,
        "subtitle": _clean(manifest.get("subtitle")),
        "author": _clean(manifest.get("author")),
        "year": _clean(manifest.get("year")),
        "copyright_holder": _clean(manifest.get("copyright_holder") or manifest.get("author")),
    }

    spec_chapters = []
    for index, chapter in enumerate(chapters_manifest, start=1):
        if not isinstance(chapter, dict):
            raise ValueError(f"Chapter entry {index} must be a YAML mapping/object.")

        chapter_title = _required_str(chapter, "title", context=f"chapter {index}")
        source = _required_str(chapter, "source", context=f"chapter {index}")
        source_path = _resolve_source_path(project_dir, source)
        if not source_path.exists():
            raise FileNotFoundError(f"Chapter source not found for chapter {index}: {source_path}")

        body = source_path.read_text(encoding="utf-8").strip()
        if not body:
            raise ValueError(f"Chapter source is empty for chapter {index}: {source_path}")

        compiled_chapter: Dict[str, Any] = {
            "title": chapter_title,
            "body": body,
        }
        if chapter.get("number") is not None:
            compiled_chapter["number"] = chapter["number"]
        if chapter.get("part"):
            compiled_chapter["part"] = chapter["part"]
        spec_chapters.append(compiled_chapter)

    return {
        "meta": meta,
        "front_matter": dict(manifest.get("front_matter") or {}),
        "chapters": spec_chapters,
        "end_matter": dict(manifest.get("end_matter") or {}),
        "letter": dict(manifest.get("letter") or {}),
        "project": {
            "slug": slug,
            "description": _clean(manifest.get("description")),
            "purpose": _clean(manifest.get("purpose")),
            "source_manifest": str(project_path),
        },
    }


def write_compiled_spec(spec: Dict[str, Any], out_path: Path) -> Path:
    out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        yaml.dump(spec, Dumper=_LiteralSafeDumper, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return out_path


def compile_project_to_file(project_path: Path, out_path: Path) -> Path:
    return write_compiled_spec(compile_project(project_path), out_path)


def _resolve_source_path(project_dir: Path, source: str) -> Path:
    source_path = Path(source)
    if not source_path.is_absolute():
        source_path = project_dir / source_path
    return source_path.resolve()


def _required_str(mapping: Dict[str, Any], key: str, *, context: str = "manifest") -> str:
    value = _clean(mapping.get(key))
    if not value:
        raise ValueError(f"Missing required {key!r} in {context}.")
    return value


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.bookgen.project_compile",
        description="Compile a book project manifest and chapter markdown files into a bookgen render spec.",
    )
    parser.add_argument("--project", required=True, help="Path to books/projects/<slug>/book_project.yaml.")
    parser.add_argument("--out", required=True, help="Path to write the compiled YAML render spec.")
    args = parser.parse_args(argv)

    try:
        out_path = compile_project_to_file(Path(args.project), Path(args.out))
    except Exception as exc:
        print(f"ERROR: Project compile failed: {exc}", file=sys.stderr)
        return 1

    print(f"[OK] Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
