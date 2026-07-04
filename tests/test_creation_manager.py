from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from http.client import HTTPConnection
from pathlib import Path

import pytest

from app.letters_of_light import creation_manager, release_server
from app.letters_of_light.contract import LetterOfLight
from app.letters_of_light.creation_manager import (
    creation_jobs_dir,
    start_creation_job,
    wait_for_creation_job,
)
from app.letters_of_light.release_server import ReleaseRequestHandler, ReleaseServer, _render_page


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fake_success_pipeline(letter_id: str = "letter123"):
    def fake_pipeline(
        *,
        theme: str,
        seed: str | None = None,
        manual_text: str | None = None,
        progress_callback=None,
        **_: object,
    ) -> LetterOfLight:
        root = Path(__import__("os").environ["SIGNAL_AGENT_ROOT"])
        letter_dir = root / "data" / "state" / "letters_of_light" / letter_id
        letter_dir.mkdir(parents=True, exist_ok=True)
        video = letter_dir / "final.mp4"
        audio = letter_dir / "voice.wav"
        music = letter_dir / "music.wav"
        visual = letter_dir / "visual.png"
        for path in (video, audio, music, visual):
            path.write_bytes(b"fake")

        now = _now()
        letter = LetterOfLight(
            letter_id=letter_id,
            theme=theme,
            title=f"The Letter of {theme.title()}",
            text=manual_text or "A test Letter body.",
            scripture_ref="Psalm 46:10",
            audio_path=str(audio),
            music_path=str(music),
            visual_path=str(visual),
            video_path=str(video),
            interaction_schema={"question_count": 1, "questions": ["What changed?"]},
            routing_payloads={"youtube": {"title": "YT title"}},
            evaluation={"decision": "accept", "total": 27, "audio_alignment": 4},
            lifecycle_state="registered",
            created_at=now,
            updated_at=now,
        )

        states = [
            ("draft", "LetterDraftCreated", {}),
            ("text_generated", "LetterTextGenerated", {"title": letter.title}),
            ("voice_generated", "LetterVoiceGenerated", {"audio_path": str(audio)}),
            ("music_generated", "LetterMusicGenerated", {"music_path": str(music)}),
            ("visual_generated", "LetterVisualGenerated", {"visual_path": str(visual)}),
            ("composed", "LetterComposed", {"video_path": str(video)}),
            ("evaluated", "LetterEvaluated", {"score": 27, "audio_alignment": 4}),
            ("interaction_added", "LetterInteractionAdded", {"question_count": 1}),
            ("registered", "LETTER_CREATED", {"letter_id": letter_id, "video_path": str(video)}),
        ]
        if progress_callback:
            for state, event_type, summary in states:
                progress_callback(
                    {
                        "letter_id": letter_id,
                        "lifecycle_state": state,
                        "event_type": event_type,
                        "timestamp": _now(),
                        "summary": summary,
                    }
                )

        payload = letter.to_dict()
        _write_json(letter_dir / "letter.json", payload)
        _write_json(letter_dir / "manifest.json", payload)
        _write_json(letter_dir / "routing.json", {"youtube": {"title": "YT title"}})
        _write_json(letter_dir / "interaction.json", letter.interaction_schema)
        return letter

    return fake_pipeline


def _fake_failed_pipeline(
    *,
    theme: str,
    seed: str | None = None,
    manual_text: str | None = None,
    progress_callback=None,
    **_: object,
) -> LetterOfLight:
    root = Path(__import__("os").environ["SIGNAL_AGENT_ROOT"])
    letter_id = "failed123"
    letter_dir = root / "data" / "state" / "letters_of_light" / letter_id
    now = _now()
    letter = LetterOfLight(
        letter_id=letter_id,
        theme=theme,
        lifecycle_state="failed",
        created_at=now,
        updated_at=now,
        metadata={"voice_error": "voice exploded"},
    )
    if progress_callback:
        progress_callback(
            {
                "letter_id": letter_id,
                "lifecycle_state": "failed",
                "event_type": "LetterFailed",
                "timestamp": now,
                "summary": {"stage": "voice", "error": "voice exploded"},
            }
        )
    _write_json(letter_dir / "letter.json", letter.to_dict())
    return letter


@pytest.fixture()
def tmp_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("SIGNAL_AGENT_ROOT", str(tmp_path))
    return tmp_path


def test_create_endpoint_returns_202_without_waiting_for_pipeline_completion(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = threading.Event()
    release = threading.Event()

    def slow_pipeline(*, theme: str, progress_callback=None, **kwargs: object) -> LetterOfLight:
        started.set()
        release.wait(timeout=5)
        return LetterOfLight(
            letter_id="slow123",
            theme=theme,
            lifecycle_state="registered",
            created_at=_now(),
            updated_at=_now(),
        )

    monkeypatch.setattr(creation_manager, "run_pipeline", slow_pipeline)
    server = ReleaseServer(("127.0.0.1", 0), ReleaseRequestHandler)
    server.quiet = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    conn = None

    try:
        conn = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        started_at = time.perf_counter()
        conn.request(
            "POST",
            "/api/create",
            body=json.dumps({"theme": "fear", "seed": "x", "manual_text": None}),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        elapsed = time.perf_counter() - started_at
    finally:
        release.set()
        if conn is not None:
            conn.close()
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert response.status == 202
    assert payload["job_id"]
    assert elapsed < 1.0
    wait_for_creation_job(payload["job_id"], timeout=5)


def test_job_state_persists_and_progress_updates_lifecycle(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(creation_manager, "run_pipeline", _fake_success_pipeline("letter-progress"))

    job = start_creation_job(theme="purpose", seed="seed")
    finished = wait_for_creation_job(job["job_id"], timeout=5)

    assert finished is not None
    assert finished["status"] == "succeeded"
    assert finished["letter_id"] == "letter-progress"
    assert finished["lifecycle_state"] == "registered"
    assert finished["final_score"] == 27

    persisted = json.loads((creation_jobs_dir() / f"{job['job_id']}.json").read_text(encoding="utf-8"))
    states = [event["lifecycle_state"] for event in persisted["events"]]
    assert "composed" in states
    assert "evaluated" in states
    assert "registered" in states


def test_successful_creation_appears_in_letter_library(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(creation_manager, "run_pipeline", _fake_success_pipeline("letter-library"))

    job = start_creation_job(theme="gratitude")
    wait_for_creation_job(job["job_id"], timeout=5)

    rows = release_server._letters_payload()
    row = next(item for item in rows if item["letter_id"] == "letter-library")
    assert row["title"] == "The Letter of Gratitude"
    assert row["eligible"] is True
    assert row["evaluation_total"] == 27


def test_failed_pipeline_produces_failed_job_with_error_state(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(creation_manager, "run_pipeline", _fake_failed_pipeline)

    job = start_creation_job(theme="fear")
    finished = wait_for_creation_job(job["job_id"], timeout=5)

    assert finished is not None
    assert finished["status"] == "failed"
    assert finished["letter_id"] == "failed123"
    assert "voice_error" in finished["error"]


def test_revision_creates_new_letter_and_preserves_parent_id(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_dir = tmp_state / "data" / "state" / "letters_of_light" / "parent123"
    _write_json(
        parent_dir / "letter.json",
        {
            "letter_id": "parent123",
            "theme": "release",
            "title": "Original",
            "text": "Original text",
            "lifecycle_state": "registered",
            "evaluation": {"decision": "accept", "total": 27, "audio_alignment": 4},
            "metadata": {},
        },
    )
    monkeypatch.setattr(creation_manager, "run_pipeline", _fake_success_pipeline("child456"))

    job = start_creation_job(
        theme="release",
        manual_text="Revised full text.",
        parent_letter_id="parent123",
    )
    finished = wait_for_creation_job(job["job_id"], timeout=5)

    assert finished is not None
    assert finished["status"] == "succeeded"
    child = json.loads(
        (tmp_state / "data" / "state" / "letters_of_light" / "child456" / "letter.json")
        .read_text(encoding="utf-8")
    )
    assert child["letter_id"] == "child456"
    assert child["metadata"]["parent_letter_id"] == "parent123"
    assert child["text"] == "Revised full text."


def test_promotion_creation_job_passes_requested_identity_and_receipt(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []

    def fake_pipeline(
        *,
        theme: str,
        seed: str | None = None,
        manual_text: str | None = None,
        requested_letter_id: str | None = None,
        initial_metadata: dict | None = None,
        progress_callback=None,
        **_: object,
    ) -> LetterOfLight:
        del seed, progress_callback
        calls.append(
            {
                "theme": theme,
                "manual_text": manual_text,
                "requested_letter_id": requested_letter_id,
                "initial_metadata": initial_metadata,
            }
        )
        letter_id = requested_letter_id or "unexpected"
        letter_dir = tmp_state / "data" / "state" / "letters_of_light" / letter_id
        letter_dir.mkdir(parents=True, exist_ok=True)
        letter = LetterOfLight(
            letter_id=letter_id,
            theme=theme,
            text=manual_text or "",
            lifecycle_state="draft",
            created_at=_now(),
            updated_at=_now(),
            metadata=dict(initial_metadata or {}),
        )
        payload = letter.to_dict()
        _write_json(letter_dir / "letter.json", payload)
        _write_json(letter_dir / "manifest.json", payload)
        return letter

    monkeypatch.setattr(creation_manager, "run_pipeline", fake_pipeline)

    job = start_creation_job(
        theme="production derivative",
        manual_text="Exact governed body.",
        parent_letter_id="governed_source_001",
        project_id="project_001",
        brand_id="brendon_r_coleman",
        requested_letter_id="production_target_001",
        initial_letter_metadata={
            "parent_letter_id": "governed_source_001",
            "revision_of": "governed_source_001",
        },
        promotion_receipt={
            "promotion_id": "production_derivative_promotion.test",
            "source_letter_id": "governed_source_001",
            "target_letter_id": "production_target_001",
        },
    )
    finished = wait_for_creation_job(job["job_id"], timeout=5)

    assert finished is not None
    assert finished["status"] == "succeeded"
    assert finished["letter_id"] == "production_target_001"
    assert finished["requested_letter_id"] == "production_target_001"
    assert finished["created_by_governed_draft_promotion"] is True
    assert finished["promotion_receipt"]["creation_job_id"] == job["job_id"]
    assert calls[0]["manual_text"] == "Exact governed body."
    assert calls[0]["requested_letter_id"] == "production_target_001"
    assert (
        calls[0]["initial_metadata"]["production_derivative_promotion"]["creation_job_id"]
        == job["job_id"]
    )

    target = json.loads(
        (
            tmp_state
            / "data"
            / "state"
            / "letters_of_light"
            / "production_target_001"
            / "letter.json"
        ).read_text(encoding="utf-8")
    )
    assert target["text"] == "Exact governed body."
    assert target["parent_letter_id"] == "governed_source_001"
    assert target["metadata"]["revision_of"] == "governed_source_001"
    assert (
        target["metadata"]["production_derivative_promotion"]["promotion_id"]
        == "production_derivative_promotion.test"
    )
    assert "production_promotion" not in target["metadata"]


def test_governed_production_promotion_receipt_uses_distinct_metadata_key(
    tmp_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []

    def fake_pipeline(
        *,
        theme: str,
        seed: str | None = None,
        manual_text: str | None = None,
        requested_letter_id: str | None = None,
        initial_metadata: dict | None = None,
        progress_callback=None,
        **_: object,
    ) -> LetterOfLight:
        del seed, progress_callback
        calls.append(
            {
                "theme": theme,
                "manual_text": manual_text,
                "requested_letter_id": requested_letter_id,
                "initial_metadata": initial_metadata,
            }
        )
        letter_id = requested_letter_id or "unexpected"
        letter_dir = tmp_state / "data" / "state" / "letters_of_light" / letter_id
        letter_dir.mkdir(parents=True, exist_ok=True)
        letter = LetterOfLight(
            letter_id=letter_id,
            theme=theme,
            text=manual_text or "",
            lifecycle_state="draft",
            created_at=_now(),
            updated_at=_now(),
            metadata=dict(initial_metadata or {}),
        )
        payload = letter.to_dict()
        _write_json(letter_dir / "letter.json", payload)
        _write_json(letter_dir / "manifest.json", payload)
        return letter

    monkeypatch.setattr(creation_manager, "run_pipeline", fake_pipeline)

    job = start_creation_job(
        theme="governed production derivative",
        manual_text="Exact governed body.",
        parent_letter_id="governed_source_001",
        project_id="project_001",
        brand_id="brendon_r_coleman",
        requested_letter_id="governed_target_001",
        initial_letter_metadata={
            "parent_letter_id": "governed_source_001",
            "revision_of": "governed_source_001",
        },
        production_promotion_receipt={
            "schema_version": "letters_of_light.production_promotion.v1",
            "promotion_id": "governed_production_promotion.test",
            "source_letter_id": "governed_source_001",
            "target_letter_id": "governed_target_001",
            "authority": {
                "production_pipeline": False,
                "release_eligibility": False,
                "approval": False,
                "export": False,
                "schedule": False,
                "publication": False,
                "platform_action": False,
                "oauth": False,
            },
        },
    )
    finished = wait_for_creation_job(job["job_id"], timeout=5)

    assert finished is not None
    assert finished["status"] == "succeeded"
    assert finished["letter_id"] == "governed_target_001"
    assert finished["requested_letter_id"] == "governed_target_001"
    assert finished["created_by_governed_draft_promotion"] is False
    assert finished["created_by_governed_production_promotion"] is True
    assert finished["production_promotion_receipt"]["creation_job_id"] == job["job_id"]
    assert finished["production_promotion_receipt"]["authority"]["production_pipeline"] is True
    assert finished["production_promotion_receipt"]["authority"]["release_eligibility"] is False
    assert calls[0]["manual_text"] == "Exact governed body."
    assert calls[0]["requested_letter_id"] == "governed_target_001"
    assert "production_promotion" in calls[0]["initial_metadata"]
    assert "production_derivative_promotion" not in calls[0]["initial_metadata"]

    target = json.loads(
        (
            tmp_state
            / "data"
            / "state"
            / "letters_of_light"
            / "governed_target_001"
            / "letter.json"
        ).read_text(encoding="utf-8")
    )
    assert target["text"] == "Exact governed body."
    assert target["parent_letter_id"] == "governed_source_001"
    assert target["metadata"]["revision_of"] == "governed_source_001"
    assert (
        target["metadata"]["production_promotion"]["promotion_id"]
        == "governed_production_promotion.test"
    )
    assert "production_derivative_promotion" not in target["metadata"]


def test_requested_letter_id_conflict_is_rejected_before_job_start(tmp_state: Path) -> None:
    target_dir = tmp_state / "data" / "state" / "letters_of_light" / "taken_target"
    _write_json(target_dir / "letter.json", {"letter_id": "taken_target"})

    with pytest.raises(ValueError, match="requested_letter_id already has persisted artifacts"):
        start_creation_job(
            theme="release",
            manual_text="Body",
            requested_letter_id="taken_target",
        )


def test_ui_html_contains_creation_jobs_and_revision_controls() -> None:
    html = _render_page()

    assert "Create Letter" in html
    assert "Active Jobs" in html
    assert "Create Revision" in html
    assert "/api/create" in html
    assert "/api/revise" in html
    assert "/api/jobs" in html
    assert "/api/publish/youtube" in html
    assert "Unlisted" in html
