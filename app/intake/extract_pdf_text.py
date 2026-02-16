from __future__ import annotations

from pathlib import Path
from pdfminer.high_level import extract_text


def extract_pdf_text(path: Path) -> str:
    return extract_text(str(path)) or ""
