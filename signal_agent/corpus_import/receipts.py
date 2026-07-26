from __future__ import annotations

import os
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from .errors import ReceiptWriteError, RunCollisionError
from .hashing import canonical_json, sha256_canonical_json


SCHEMA_VERSION = "chatgpt_export_validation_receipt.v1"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def compute_receipt_hash(receipt: dict) -> str:
    material = deepcopy(receipt)
    material.pop("receipt_hash", None)
    return f"sha256:{sha256_canonical_json(material)}"


def seal_receipt(receipt: dict) -> dict:
    payload = deepcopy(receipt)
    payload["receipt_hash"] = "sha256:" + ("0" * 64)
    payload["receipt_hash"] = compute_receipt_hash(payload)
    return payload


def verify_receipt_hash(receipt: dict) -> bool:
    receipt_hash = receipt.get("receipt_hash")
    return isinstance(receipt_hash, str) and receipt_hash == compute_receipt_hash(receipt)


def write_receipt_exclusive(path: Path, receipt: dict) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json(receipt) + "\n"
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise RunCollisionError(f"Refusing to overwrite validation receipt: {path}") from exc
    except OSError as exc:
        raise ReceiptWriteError(f"Unable to write validation receipt '{path}': {exc}") from exc
    return path
