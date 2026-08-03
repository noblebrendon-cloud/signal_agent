from __future__ import annotations

import os
from pathlib import Path

from .errors import ExtractionCollisionError, ReceiptWriteError
from .hashing import canonical_json


EXTRACTION_RECEIPT_SCHEMA_VERSION = "chatgpt_export_extraction_receipt.v1"


def write_extraction_receipt_exclusive(path: Path, receipt: dict) -> Path:
    """Write a sealed extraction receipt without replacing an existing path."""

    path = Path(path)
    created = False
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            created = True
            payload = canonical_json(receipt) + "\n"
            written = handle.write(payload)
            if written != len(payload):
                raise OSError(
                    f"Short receipt write: wrote {written} of {len(payload)} characters"
                )
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise ExtractionCollisionError(
            f"Refusing to overwrite extraction receipt: {path}"
        ) from exc
    except OSError as exc:
        if created:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        raise ReceiptWriteError(f"Unable to write extraction receipt '{path}': {exc}") from exc
    return path
