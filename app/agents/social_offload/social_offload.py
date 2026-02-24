import argparse
import hashlib
import logging
import sys
import time
import uuid
from pathlib import Path
from typing import Any

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from jinja2 import Environment, FileSystemLoader
import yaml

from app.governor import enforce as governor_enforce, governor_review
from app.utils.reprojection import reproject_checkpoint, extract_artifact_state
from app.utils.exceptions import ConstraintViolation
from app.utils.io_contract import atomic_write_text, append_jsonl_atomic

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "data" / "social_offload" / "outputs"
DEFAULT_LOG_PATH = REPO_ROOT / "data" / "social_offload" / "logs" / "social_offload_runs.jsonl"
TEMPLATE_VERSION = "1.0.0"
GOVERNOR_SCOPE = "social_offload.run"
GOVERNOR_BOOTSTRAP_SCOPES = ["capture.*", "governor.*", GOVERNOR_SCOPE]

def sha256_hash(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _load_pack_version(pack_path: Path) -> str:
    try:
        with open(pack_path, "r", encoding="utf-8") as f:
            pack = yaml.safe_load(f) or {}
        value = pack.get("pack_version")
        if value is not None:
            return str(value)
    except Exception:
        pass
    return "unknown"


def _build_ids(artifact_path: Path, content: str | None, pack_version: str, template_version: str) -> tuple[str, str]:
    artifact_basis = content if content is not None else str(artifact_path)
    artifact_id = sha256_hash(artifact_basis)[:12]
    render_id = sha256_hash(f"{artifact_id}_{pack_version}_{template_version}")[:12]
    return artifact_id, render_id


def _append_run_log(log_path: Path, log_entry: dict[str, Any]) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    append_jsonl_atomic(jsonl_path=log_path, record=log_entry)


def _enforce_social_offload_governor() -> dict[str, Any]:
    decision = governor_enforce(scope=GOVERNOR_SCOPE)
    if decision.get("decision") != "BLOCK":
        return decision

    if decision.get("reason") != "state_missing_or_invalid":
        return decision

    try:
        governor_review(init=True, authorized_scopes=GOVERNOR_BOOTSTRAP_SCOPES)
    except Exception as exc:
        logger.error("Activation Governor bootstrap failed: %s", exc)
        return decision

    return governor_enforce(scope=GOVERNOR_SCOPE)


def render_linkedin_output(state, template_dir: Path) -> str:
    env = Environment(loader=FileSystemLoader(str(template_dir)), trim_blocks=True, lstrip_blocks=True)
    template = env.get_template("linkedin_post.jinja")
    rendered = template.render(sections=state.sections, claims=state.claims, word_count=state.word_count)
    return rendered.strip()

def run_social_offload(
    artifact_path: Path,
    channel: str,
    out_dir: Path,
    pack_path: Path,
    log_path: Path,
    dry_run: bool,
    enforce_governor: bool = True,
) -> int:
    artifact_path = artifact_path.resolve()
    pack_path = pack_path.resolve()
    out_dir = out_dir.resolve()
    log_path = log_path.resolve()

    pack_version = _load_pack_version(pack_path)
    template_version = TEMPLATE_VERSION
    run_id = uuid.uuid4().hex
    artifact_id, render_id = _build_ids(artifact_path, content=None, pack_version=pack_version, template_version=template_version)

    if enforce_governor:
        decision = _enforce_social_offload_governor()
        if decision.get("decision") == "BLOCK":
            logger.error(
                "Activation Governor blocked social_offload.run reason=%s lock_id=%s drift_status=%s",
                decision.get("reason"),
                decision.get("lock_id"),
                decision.get("drift_status"),
            )
            hint = decision.get("remediation_hint")
            if hint:
                logger.error("Remediation: %s", hint)
            write_fault_report(
                log_path=log_path,
                artifact_path=artifact_path,
                artifact_id=artifact_id,
                channel=channel,
                pack_version=pack_version,
                template_version=template_version,
                render_id=render_id,
                run_id=run_id,
                dry_run=dry_run,
                fault_details=[f"governor_blocked:{decision.get('reason', 'unknown')}"],
            )
            return 2

    logger.info(f"Starting {channel} social offload for artifact {artifact_path} (Run ID: {run_id})")

    try:
        with open(artifact_path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        logger.error(f"Artifact not found: {artifact_path}")
        write_fault_report(
            log_path=log_path,
            artifact_path=artifact_path,
            artifact_id=artifact_id,
            channel=channel,
            pack_version=pack_version,
            template_version=template_version,
            render_id=render_id,
            run_id=run_id,
            dry_run=dry_run,
            fault_details=["artifact_not_found"],
        )
        return 1

    state = extract_artifact_state(content)
    artifact_id, render_id = _build_ids(artifact_path, content=content, pack_version=pack_version, template_version=template_version)
    logger.info(f"Artifact ID: {artifact_id} | Render ID: {render_id}")

    # 1. Reproject constraint check
    try:
        reproject_checkpoint(
            artifact=content,
            pack_path=str(pack_path),
            execution_context_id=render_id,
            log_dir=log_path.parent / "reprojection",
        )
    except ConstraintViolation as e:
        logger.error(f"Failing closed due to constraint violation: {e}")
        write_fault_report(
            log_path=log_path,
            artifact_path=artifact_path,
            artifact_id=artifact_id,
            channel=channel,
            pack_version=pack_version,
            template_version=template_version,
            render_id=render_id,
            run_id=run_id,
            dry_run=dry_run,
            fault_details=[str(e)],
        )
        return 1

    # 2. Render Template
    template_dir = Path(__file__).resolve().parent / "templates"
    try:
        rendered_text = render_linkedin_output(state, template_dir)
    except Exception as e:
        logger.error(f"Template rendering failed: {e}")
        write_fault_report(
            log_path=log_path,
            artifact_path=artifact_path,
            artifact_id=artifact_id,
            channel=channel,
            pack_version=pack_version,
            template_version=template_version,
            render_id=render_id,
            run_id=run_id,
            dry_run=dry_run,
            fault_details=[f"Template Error: {e}"],
        )
        return 1

    # 3. Write Output
    if not dry_run:
        channel_out_dir = out_dir / channel / artifact_id
        channel_out_dir.mkdir(parents=True, exist_ok=True)
        out_file = channel_out_dir / f"{render_id}.txt"
        atomic_write_text(out_file, rendered_text)
        logger.info(f"Successfully atomic-wrote output to {out_file}")
        
        # Verify output exists and is not empty before claiming ok
        if not out_file.exists() or out_file.stat().st_size == 0:
            logger.error("Output file validation failed after write.")
            write_fault_report(
                log_path=log_path,
                artifact_path=artifact_path,
                artifact_id=artifact_id,
                channel=channel,
                pack_version=pack_version,
                template_version=template_version,
                render_id=render_id,
                run_id=run_id,
                dry_run=dry_run,
                fault_details=["empty_or_missing_output"],
            )
            return 1

    # 4. Write Audit Log
    log_entry = {
        "timestamp": time.time(),
        "run_id": run_id,
        "artifact_path": str(artifact_path),
        "artifact_id": artifact_id,
        "render_id": render_id,
        "channel": channel,
        "pack_version": pack_version,
        "template_version": template_version,
        "status": "ok",
        "dry_run": dry_run,
        "word_count": state.word_count,
        "claim_count": len(state.claims),
    }
    _append_run_log(log_path, log_entry)

    logger.info("Pipeline completed successfully.")
    return 0

def write_fault_report(
    log_path: Path,
    artifact_path: Path,
    artifact_id: str,
    channel: str,
    pack_version: str,
    template_version: str,
    render_id: str,
    run_id: str,
    dry_run: bool,
    fault_details: Any,
) -> None:
    if fault_details is None:
        fault_codes: list[str] = []
    elif isinstance(fault_details, list):
        fault_codes = [str(item) for item in fault_details if item is not None]
    elif isinstance(fault_details, tuple):
        fault_codes = [str(item) for item in fault_details if item is not None]
    elif isinstance(fault_details, str):
        fault_codes = [fault_details]
    else:
        fault_codes = [str(fault_details)]

    log_entry = {
        "timestamp": time.time(),
        "run_id": run_id,
        "artifact_path": str(artifact_path),
        "artifact_id": artifact_id,
        "render_id": render_id,
        "channel": channel,
        "pack_version": pack_version,
        "template_version": template_version,
        "status": "fault",
        "dry_run": dry_run,
        "fault_codes": fault_codes,
    }
    _append_run_log(log_path, log_entry)

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic Social Offload")
    parser.add_argument("--artifact", required=True, type=Path, help="Core artifact path")
    parser.add_argument("--channel", required=True, choices=["linkedin"], help="Target channel")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT_ROOT, help="Output root directory")
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG_PATH, help="Canonical JSONL log path")
    parser.add_argument("--pack", type=Path, required=True, help="Constraint pack path")
    parser.add_argument("--dry-run", action="store_true", help="Do not write file")
    parser.add_argument("--no-governor", action="store_true", help="Disable Activation Governor enforcement")

    args = parser.parse_args(argv)
    return run_social_offload(
        args.artifact,
        args.channel,
        args.out,
        args.pack,
        args.log,
        args.dry_run,
        enforce_governor=not args.no_governor,
    )


if __name__ == "__main__":
    raise SystemExit(main())
