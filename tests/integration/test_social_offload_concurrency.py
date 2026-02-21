import json
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SOCIAL_OFFLOAD_SCRIPT = REPO_ROOT / "app" / "agents" / "social_offload" / "social_offload.py"
PACK_PATH = REPO_ROOT / "constraints" / "packs" / "domain" / "linkedin_pack.yaml"
PASSING_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "social_offload" / "core_artifact.md"


def run_worker(out_dir: Path, log_path: Path) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable,
        str(SOCIAL_OFFLOAD_SCRIPT),
        "--artifact", str(PASSING_FIXTURE),
        "--channel", "linkedin",
        "--out", str(out_dir),
        "--log", str(log_path),
        "--pack", str(PACK_PATH),
    ]
    return subprocess.run(cmd, cwd=str(REPO_ROOT), text=True, capture_output=True, check=False)


def run_concurrency_test() -> None:
    # Use a real temp directory wrapper
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        out_dir = tmp_path / "outputs"
        log_jsonl = tmp_path / "logs" / "shared_social_offload_runs.jsonl"
    
        num_workers = 12

    # Spawn 12 concurrent workers
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(run_worker, out_dir, log_jsonl) for _ in range(num_workers)]
        results = [future.result() for future in as_completed(futures)]

    # 1. Assert all workers succeeded
    for res in results:
        assert res.returncode == 0, f"Worker failed: {res.stderr}"

    # 2. Assert log file exists and contains exactly 12 lines
    assert log_jsonl.exists()
    lines = log_jsonl.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == num_workers

    # 3. Assert all lines are valid JSON, contain a unique run_id, and have status "ok"
    run_ids = set()
    for line in lines:
        try:
            record = json.loads(line)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Invalid JSON line written: {e}\nLine: {line}")
        
        assert "run_id" in record
        assert record["status"] == "ok"
        run_ids.add(record["run_id"])

    assert len(run_ids) == num_workers, "Duplicate run_ids found, implies overlapping execution states."
    print(f"SUCCESS: {num_workers} runs written atomically to a single JSONL. No interleaving.")


if __name__ == "__main__":
    run_concurrency_test()
