from __future__ import annotations

from pathlib import Path


def extract_pdf_text(path: Path) -> str:
    try:
        from pdfminer.high_level import extract_text
    except ModuleNotFoundError as e:
        raise RuntimeError(
            "PDF extraction requires pdfminer.six. Install with: pip install pdfminer.six"
        ) from e

    return extract_text(str(path)) or ""
