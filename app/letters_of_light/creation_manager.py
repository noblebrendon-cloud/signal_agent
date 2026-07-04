"""
app/letters_of_light/creation_manager.py - persisted creation jobs.

The manager starts Letters of Light pipeline runs from an intentional request,
then observes progress from the pipeline in a single background worker.
"""
from __future__ import annotations

import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from app.letters_of_light.brand_registry import DEFAULT_BRAND_ID, get_brand
from app.letters_of_light.pipeline import run_pipeline
from app.letters_of_light.release import (
    _get_root,
    _letter_dir,
    _read_json,
    _write_json,
    check_release_eligibility,
)


JOB_STATES = {"queued", "running", "succeeded", "failed"}
_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="letters-of-light-create")
_LOCK = threading.RLock()
_FUTURES: Dict[str, Future] = {}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def creation_jobs_dir() -> Path:
    return _get_root() / "data" / "state" / "letters_of_light" / "creation_jobs"


def _job_path(job_id: str) -> Path:
    return creation_jobs_dir() / f"{job_id}.json"


def _new_job_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return f"create_{stamp}_{uuid.uuid4().hex[:8]}"


def _ensure_requested_letter_id_available(requested_letter_id: Optional[str]) -> None:
    if not requested_letter_id:
        return
    target = _letter_dir(str(requested_letter_id))
    if target.exists() and any(target.iterdir()):
        raise ValueError(f"requested_letter_id already has persisted artifacts: {requested_letter_id}")


def _read_job_file(job_id: str) -> Dict[str, Any]:
    data = _read_json(_job_path(job_id))
    if data.get("job_id") != job_id:
        return {}
    return data


def _write_job(job: Dict[str, Any]) -> None:
    _write_json(_job_path(str(job["job_id"])), job)


def _safe_progress_event(event: Dict[str, Any]) -> Dict[str, Any]:
    summary = event.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    return {
        "event_type": str(event.get("event_type") or ""),
        "lifecycle_state": str(event.get("lifecycle_state") or ""),
        "letter_id": str(event.get("letter_id") or ""),
        "timestamp": str(event.get("timestamp") or _utc_now()),
        "summary": summary,
    }


def _update_job(job_id: str, mutator: Callable[[Dict[str, Any]], None]) -> Dict[str, Any]:
    with _LOCK:
        job = _read_job_file(job_id)
        if not job:
            raise KeyError(f"creation job not found: {job_id}")
        mutator(job)
        job["updated_at"] = _utc_now()
        _write_job(job)
        return job


def _error_from_letter(letter: Any) -> Optional[str]:
    metadata = getattr(letter, "metadata", {}) or {}
    for key in (
        "text_error",
        "voice_error",
        "music_error",
        "visual_error",
        "compose_error",
        "evaluation_error",
        "interaction_error",
        "registration_error",
    ):
        if key in metadata:
            return f"{key}: {metadata[key]}"
    return None


def _attach_parent_metadata(letter_id: str, parent_letter_id: str) -> None:
    if not letter_id or not parent_letter_id:
        return

    for filename in ("letter.json", "manifest.json"):
        path = _letter_dir(letter_id) / filename
        data = _read_json(path)
        if not data:
            continue
        metadata = data.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["parent_letter_id"] = parent_letter_id
            metadata["revision_of"] = parent_letter_id
        data["parent_letter_id"] = parent_letter_id
        _write_json(path, data)


def _attach_project_metadata(
    letter_id: str,
    project_id: Optional[str],
    source_asset_ids: Optional[List[str]],
    source_passages: Optional[List[Dict[str, Any]]],
    brand_id: Optional[str],
    brand_version: Optional[str],
) -> None:
    if not letter_id:
        return

    clean_asset_ids = [str(item) for item in (source_asset_ids or []) if str(item).strip()]
    clean_passages = [
        {
            "asset_id": str(item.get("asset_id") or ""),
            "passage_id": str(item.get("passage_id") or ""),
            "page_number": item.get("page_number"),
            "text": str(item.get("text") or ""),
        }
        for item in (source_passages or [])
        if isinstance(item, dict)
    ]

    for filename in ("letter.json", "manifest.json"):
        path = _letter_dir(letter_id) / filename
        data = _read_json(path)
        if not data:
            continue
        metadata = data.setdefault("metadata", {})
        if isinstance(metadata, dict):
            if project_id:
                metadata["project_id"] = project_id
            metadata["source_asset_ids"] = clean_asset_ids
            metadata["selected_source_passages"] = clean_passages
            metadata["brand_id"] = brand_id or DEFAULT_BRAND_ID
            metadata["brand_version"] = brand_version or "1"
        _write_json(path, data)


def _finalize_release_fields(job: Dict[str, Any], letter_id: str, lifecycle_state: str) -> None:
    if not letter_id:
        job["release_eligible"] = False
        job["release_reasons"] = ["letter_id was not produced"]
        return

    letter = _read_json(_letter_dir(letter_id) / "letter.json")
    evaluation = letter.get("evaluation", {}) if isinstance(letter.get("evaluation"), dict) else {}
    job["final_score"] = evaluation.get("total")
    job["audio_score"] = evaluation.get("audio_alignment")

    if lifecycle_state == "registered" and not job.get("created_by_governed_production_promotion"):
        check = check_release_eligibility(letter_id)
        job["release_eligible"] = check.eligible
        job["release_reasons"] = check.reasons
    elif lifecycle_state == "registered":
        job["release_eligible"] = False
        job["release_reasons"] = [
            "governed production promotion does not grant release eligibility"
        ]
    else:
        job["release_eligible"] = False
        job["release_reasons"] = [f"lifecycle_state is {lifecycle_state or 'unknown'}"]


def _run_job(
    *,
    job_id: str,
    theme: str,
    seed: Optional[str],
    manual_text: Optional[str],
    parent_letter_id: Optional[str],
    project_id: Optional[str],
    source_asset_ids: Optional[List[str]],
    source_passages: Optional[List[Dict[str, Any]]],
    brand_id: Optional[str],
    brand_version: Optional[str],
    requested_letter_id: Optional[str],
    initial_letter_metadata: Optional[Dict[str, Any]],
    promotion_receipt: Optional[Dict[str, Any]],
    production_promotion_receipt: Optional[Dict[str, Any]],
) -> None:
    del promotion_receipt, production_promotion_receipt

    def mark_running(job: Dict[str, Any]) -> None:
        now = _utc_now()
        job["status"] = "running"
        job["started_at"] = now
        job["current_stage"] = "running"
        job.setdefault("events", []).append(
            {
                "event_type": "CreationJobRunning",
                "lifecycle_state": job.get("lifecycle_state", ""),
                "letter_id": job.get("letter_id", ""),
                "timestamp": now,
                "summary": {},
            }
        )

    _update_job(job_id, mark_running)

    def progress_callback(event: Dict[str, Any]) -> None:
        safe_event = _safe_progress_event(event)

        def apply_progress(job: Dict[str, Any]) -> None:
            if safe_event["letter_id"]:
                job["letter_id"] = safe_event["letter_id"]
            if safe_event["lifecycle_state"]:
                job["lifecycle_state"] = safe_event["lifecycle_state"]
                job["current_stage"] = safe_event["lifecycle_state"]
            summary = safe_event["summary"]
            if summary.get("score") is not None:
                job["final_score"] = summary.get("score")
            if summary.get("audio_alignment") is not None:
                job["audio_score"] = summary.get("audio_alignment")
            job.setdefault("events", []).append(safe_event)

        _update_job(job_id, apply_progress)

    try:
        letter = run_pipeline(
            theme=theme,
            seed=seed,
            manual_text=manual_text,
            requested_letter_id=requested_letter_id,
            initial_metadata=initial_letter_metadata,
            progress_callback=progress_callback,
        )
        letter_id = getattr(letter, "letter_id", "")
        lifecycle_state = getattr(letter, "lifecycle_state", "")
        if requested_letter_id and letter_id != requested_letter_id:
            raise RuntimeError(
                f"pipeline returned unexpected letter_id {letter_id!r}; expected {requested_letter_id!r}"
            )
        if parent_letter_id and letter_id:
            _attach_parent_metadata(letter_id, parent_letter_id)
        if letter_id:
            _attach_project_metadata(
                letter_id,
                project_id,
                source_asset_ids,
                source_passages,
                brand_id,
                brand_version,
            )

        def mark_complete(job: Dict[str, Any]) -> None:
            now = _utc_now()
            job["letter_id"] = letter_id
            job["lifecycle_state"] = lifecycle_state
            job["current_stage"] = lifecycle_state
            job["completed_at"] = now
            _finalize_release_fields(job, letter_id, lifecycle_state)
            if lifecycle_state == "failed":
                job["status"] = "failed"
                job["error"] = _error_from_letter(letter) or "pipeline returned failed state"
            else:
                job["status"] = "succeeded"
                job["error"] = None
            job.setdefault("events", []).append(
                {
                    "event_type": "CreationJobCompleted",
                    "lifecycle_state": lifecycle_state,
                    "letter_id": letter_id,
                    "timestamp": now,
                    "summary": {
                        "status": job["status"],
                        "release_eligible": job.get("release_eligible"),
                        "final_score": job.get("final_score"),
                    },
                }
            )

        _update_job(job_id, mark_complete)
    except Exception as exc:
        def mark_failed(job: Dict[str, Any]) -> None:
            now = _utc_now()
            job["status"] = "failed"
            job["current_stage"] = job.get("lifecycle_state") or "failed"
            job["completed_at"] = now
            job["error"] = str(exc)
            job["release_eligible"] = False
            job["release_reasons"] = [str(exc)]
            job.setdefault("events", []).append(
                {
                    "event_type": "CreationJobFailed",
                    "lifecycle_state": job.get("lifecycle_state") or "failed",
                    "letter_id": job.get("letter_id", ""),
                    "timestamp": now,
                    "summary": {"error": str(exc)},
                }
            )

        _update_job(job_id, mark_failed)


def start_creation_job(
    *,
    theme: str,
    seed: Optional[str] = None,
    manual_text: Optional[str] = None,
    parent_letter_id: Optional[str] = None,
    project_id: Optional[str] = None,
    source_asset_ids: Optional[List[str]] = None,
    source_passages: Optional[List[Dict[str, Any]]] = None,
    brand_id: Optional[str] = None,
    brand_version: Optional[str] = None,
    requested_letter_id: Optional[str] = None,
    initial_letter_metadata: Optional[Dict[str, Any]] = None,
    promotion_receipt: Optional[Dict[str, Any]] = None,
    production_promotion_receipt: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    theme = str(theme or "").strip()
    if not theme:
        raise ValueError("theme is required")
    _ensure_requested_letter_id_available(requested_letter_id)
    brand = get_brand(brand_id or DEFAULT_BRAND_ID)
    resolved_brand_id = str(brand.get("brand_id") or DEFAULT_BRAND_ID)
    resolved_brand_version = str(brand_version or brand.get("version") or "1")

    job_id = _new_job_id()
    now = _utc_now()
    clean_initial_metadata = dict(initial_letter_metadata or {})
    clean_promotion_receipt = dict(promotion_receipt or {})
    if clean_promotion_receipt:
        clean_promotion_receipt["creation_job_id"] = job_id
        clean_initial_metadata["production_derivative_promotion"] = clean_promotion_receipt
    clean_production_promotion_receipt = dict(production_promotion_receipt or {})
    if clean_production_promotion_receipt:
        clean_production_promotion_receipt["creation_job_id"] = job_id
        authority = dict(clean_production_promotion_receipt.get("authority") or {})
        authority["production_pipeline"] = True
        for key in (
            "release_eligibility",
            "approval",
            "export",
            "schedule",
            "publication",
            "platform_action",
            "oauth",
        ):
            authority[key] = False
        clean_production_promotion_receipt["authority"] = authority
        clean_initial_metadata["production_promotion"] = clean_production_promotion_receipt
    job: Dict[str, Any] = {
        "job_id": job_id,
        "status": "queued",
        "letter_id": None,
        "requested_letter_id": requested_letter_id,
        "theme": theme,
        "seed": seed,
        "manual_text_provided": bool(manual_text),
        "parent_letter_id": parent_letter_id,
        "project_id": project_id,
        "brand_id": resolved_brand_id,
        "brand_version": resolved_brand_version,
        "source_asset_ids": source_asset_ids or [],
        "source_passages": source_passages or [],
        "initial_letter_metadata": clean_initial_metadata,
        "promotion_receipt": clean_promotion_receipt or None,
        "production_promotion_receipt": clean_production_promotion_receipt or None,
        "created_by_governed_draft_promotion": bool(clean_promotion_receipt),
        "created_by_governed_production_promotion": bool(clean_production_promotion_receipt),
        "lifecycle_state": "",
        "current_stage": "queued",
        "created_at": now,
        "queued_at": now,
        "started_at": None,
        "updated_at": now,
        "completed_at": None,
        "error": None,
        "final_score": None,
        "audio_score": None,
        "release_eligible": None,
        "release_reasons": [],
        "events": [
            {
                "event_type": "CreationJobQueued",
                "lifecycle_state": "",
                "letter_id": "",
                "timestamp": now,
                "summary": {},
            }
        ],
    }

    with _LOCK:
        _write_job(job)
        future = _EXECUTOR.submit(
            _run_job,
            job_id=job_id,
            theme=theme,
            seed=seed,
            manual_text=manual_text,
            parent_letter_id=parent_letter_id,
            project_id=project_id,
            source_asset_ids=source_asset_ids or [],
            source_passages=source_passages or [],
            brand_id=resolved_brand_id,
            brand_version=resolved_brand_version,
            requested_letter_id=requested_letter_id,
            initial_letter_metadata=clean_initial_metadata,
            promotion_receipt=clean_promotion_receipt or None,
            production_promotion_receipt=clean_production_promotion_receipt or None,
        )
        _FUTURES[job_id] = future

    return job


def get_creation_job(job_id: str) -> Optional[Dict[str, Any]]:
    with _LOCK:
        job = _read_job_file(job_id)
        return job or None


def list_creation_jobs() -> List[Dict[str, Any]]:
    root = creation_jobs_dir()
    if not root.exists():
        return []

    jobs: List[Dict[str, Any]] = []
    for path in root.glob("*.json"):
        data = _read_json(path)
        if data.get("job_id") and data.get("status") in JOB_STATES:
            jobs.append(data)

    jobs.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return jobs


def wait_for_creation_job(job_id: str, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
    future = _FUTURES.get(job_id)
    if future is not None:
        future.result(timeout=timeout)
    return get_creation_job(job_id)


def shutdown_creation_jobs(wait: bool = True) -> None:
    _EXECUTOR.shutdown(wait=wait, cancel_futures=False)
