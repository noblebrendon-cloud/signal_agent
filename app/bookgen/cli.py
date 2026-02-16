from __future__ import annotations

import argparse
from pathlib import Path

from .render import load_spec, render_from_spec


def main() -> int:
    p = argparse.ArgumentParser(prog="bookgen", description="Generate a mini-series book from a YAML spec.")
    p.add_argument("--spec", required=True, help="Path to YAML spec file.")
    p.add_argument("--out", required=True, help="Output directory for generated files.")
    p.add_argument("--templates", default=None, help="Templates directory (defaults to app/bookgen/templates).")

    args = p.parse_args()

    spec_path = Path(args.spec).resolve()
    out_dir = Path(args.out).resolve()
    templates_dir = Path(args.templates).resolve() if args.templates else (Path(__file__).parent / "templates").resolve()

    spec = load_spec(spec_path)
    outputs = render_from_spec(spec, templates_dir, out_dir)

    print(f"[OK] Wrote:\n- {outputs.book_md}\n- {outputs.cover_front_txt}\n- {outputs.letter_one_sentence_txt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
