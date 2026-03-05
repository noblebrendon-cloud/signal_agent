import json
import logging
import subprocess
import sys
from collections import deque
from pathlib import Path
from pydantic import BaseModel
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DASHBOARD_DIR = Path(__file__).resolve().parent
REPO_ROOT = DASHBOARD_DIR.parents[2]

SOCIAL_OFFLOAD_SCRIPT = REPO_ROOT / "app" / "agents" / "social_offload" / "social_offload.py"
LOGS_JSONL = REPO_ROOT / "data" / "social_offload" / "logs" / "social_offload_runs.jsonl"
OUTPUTS_ROOT = REPO_ROOT / "data" / "social_offload" / "outputs"
OUTPUTS_DIR = OUTPUTS_ROOT / "linkedin"

app = FastAPI(title="HQ Social Offload Dashboard")

class RunRequest(BaseModel):
    artifact_path: str
    pack_path: str
    dry_run: bool = False

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    index_path = DASHBOARD_DIR / "index.html"
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "<h1>Error: index.html not found</h1>"

@app.post("/api/run/social_offload")
async def run_social_offload(req: RunRequest):
    # Resolve against REPO_ROOT if relative
    if Path(req.artifact_path).is_absolute():
        abs_artifact = Path(req.artifact_path)
    else:
        abs_artifact = (REPO_ROOT / req.artifact_path).resolve()
        
    if Path(req.pack_path).is_absolute():
        abs_pack = Path(req.pack_path)
    else:
        abs_pack = (REPO_ROOT / req.pack_path).resolve()
    
    cmd = [
        sys.executable,
        str(SOCIAL_OFFLOAD_SCRIPT),
        "--artifact", str(abs_artifact),
        "--channel", "linkedin",
        "--out", str(OUTPUTS_ROOT),
        "--log", str(LOGS_JSONL),
        "--pack", str(abs_pack),
    ]
    if req.dry_run:
        cmd.append("--dry-run")
        
    logger.info(f"Executing: {' '.join(cmd)}")
    
    proc = subprocess.Popen(
        cmd,
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    stdout, stderr = proc.communicate()
    
    return {
        "returncode": proc.returncode,
        "stdout_tail": stdout[-2000:] if stdout else "",
        "stderr_tail": stderr[-2000:] if stderr else "",
    }

@app.get("/api/runs")
async def get_runs(limit: int = 50):
    if not LOGS_JSONL.exists():
        return []
    
    lines = deque(maxlen=limit)
    try:
        with open(LOGS_JSONL, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    lines.append(line)
    except Exception as e:
        logger.error(f"Error reading logs: {e}")
        return []
        
    results = []
    for line in reversed(list(lines)):
        try:
            results.append(json.loads(line))
        except json.JSONDecodeError:
            pass
            
    return results

@app.get("/api/outputs")
async def get_outputs():
    if not OUTPUTS_DIR.exists():
        return {"files": []}
    
    files = []
    try:
        for p in OUTPUTS_DIR.rglob("*.txt"):
            rel_path = p.relative_to(REPO_ROOT)
            files.append(str(rel_path).replace("\\", "/"))
    except Exception as e:
        logger.error(f"Error reading outputs: {e}")
        
    return {"files": sorted(files, reverse=True)}
