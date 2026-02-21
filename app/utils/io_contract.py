import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict


def atomic_write_text(final_path: Path, text: str) -> Dict[str, Path]:
    """
    Writes text to a temporary sibling file, flushes/fsyncs, and atomically
    renames it to final_path.
    Returns the paths involved for tracking.
    """
    final_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Create temp file in the same directory to ensure it's on the same mount/filesystem
    # This guarantees os.replace is atomic.
    fd, tmp_path_str = tempfile.mkstemp(prefix=final_path.name + ".", suffix=".tmp", dir=str(final_path.parent))
    tmp_path = Path(tmp_path_str)
    
    try:
        # Write bytes
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
            
        # Atomically replace (with Windows AV/Concurrency retry)
        for attempt in range(10):
            try:
                os.replace(tmp_path, final_path)
                break
            except PermissionError:
                if attempt == 9:
                    raise
                time.sleep(0.02)
    except Exception as e:
        # Best effort cleanup if atomic rename fails
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise e
        
    return {"final_path": final_path, "tmp_path": tmp_path}


def append_jsonl_atomic(jsonl_path: Path, record: Dict[str, Any], lock_path: Path | None = None, retries: int = 30, base_sleep_s: float = 0.02) -> None:
    """
    Appends a JSON record to a JSONL file using a basic lockfile for concurrency.
    Supports Windows where fcntl is not available.
    """
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    if lock_path is None:
        lock_path = jsonl_path.with_suffix(jsonl_path.suffix + ".lock")
        
    for attempt in range(retries):
        try:
            # Atomic lock acquisition using open(..., x) - fails if exists
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            break
        except FileExistsError:
            if attempt == retries - 1:
                raise TimeoutError(f"Failed to acquire lock {lock_path} after {retries} attempts.")
            time.sleep(base_sleep_s)
            
    try:
        # Now we have the lock, append to file
        with open(jsonl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
            f.flush()
            os.fsync(f.fileno())
    finally:
        # Release lock
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass
