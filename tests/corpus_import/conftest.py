from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest


@pytest.fixture
def valid_export_zip(tmp_path: Path) -> Path:
    source = tmp_path / "chatgpt-export.zip"
    with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("conversations.json", json.dumps([{"id": "c1", "title": "Fixture"}]))
        archive.writestr("user.json", json.dumps({"id": "u1"}))
    return source
