from __future__ import annotations

import os
import tempfile
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
_LOCAL_TEMP = _REPO_ROOT / ".tmp" / "temp"
_LOCAL_TEMP.mkdir(parents=True, exist_ok=True)

_TEMP_PATH = str(_LOCAL_TEMP)
for _key in ("TMP", "TEMP", "TMPDIR"):
    os.environ[_key] = _TEMP_PATH

tempfile.tempdir = _TEMP_PATH
