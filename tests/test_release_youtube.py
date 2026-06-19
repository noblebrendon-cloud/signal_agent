from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from pathlib import Path

import pytest

from app.letters_of_light import release_server
from app.letters_of_light.publishers.base import (
    MissingCredentialsError,
    MissingReleaseError,
    PublisherError,
    ReleaseNotApprovedError,
    VideoMissingError,
)
from app.letters_of_light.publishers.youtube import publish_youtube
from app.letters_of_light.release_server import ReleaseRequestHandler, ReleaseServer, _render_page


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _make_release(
    root: Path,
    *,
    letter_id: str = "abc123",
    approved: bool = True,
    video: bool = True,
    public_log: bool = False,
) -> Path:
    letter_dir = root / "data" / "state" / "letters_of_light" / letter_id
    export_dir = letter_dir / "release_export"
    export_dir.mkdir(parents=True, exist_ok=True)
    video_path = export_dir / "final.mp4"
    if video:
        video_path.write_bytes(b"fake mp4")

    _write_json(
        letter_dir / "release.json",
        {
            "letter_id": letter_id,
            "campaign_id": "lol-release-abc123",
            "release_state": "published",
            "approved": approved,
            "canonical_url": "https://example.test/letters/abc123/",
            "title": "The Letter of Release",
            "theme": "release",
            "assets": {
                "video_path": str(video_path),
                "visual_path": "",
            },
            "targets": {
                "youtube": {
                    "enabled": True,
                    "status": "pending",
                    "platform_id": None,
                    "url": None,
                    "payload": {
                        "title": "Release from release",
                        "description": "Release description",
                        "tags": ["Letters of Light", "release"],
                        "video_path": str(video_path),
                    },
                }
            },
            "events": [],
        },
    )
    _write_json(
        letter_dir / "routing.json",
        {
            "youtube": {
                "title": "Release from routing",
                "description": "Routing description",
                "tags": ["Letters of Light", "release", "faith"],
                "video_path": str(video_path),
            }
        },
    )
    (export_dir / "youtube_title.txt").write_text("Release from export", encoding="utf-8")
    (export_dir / "youtube_description.txt").write_text("Export description", encoding="utf-8")
    _write_json(export_dir / "asset_manifest.json", {"video_path": str(video_path)})

    if public_log:
        _write_json(
            letter_dir / "public_release_log.json",
            {
                "letter_id": letter_id,
                "release_phase": "site_live_social_published",
                "social_urls": {"youtube": None},
                "updated_at": "2026-06-18T00:00:00+00:00",
            },
        )

    return letter_dir


class FakeUploader:
    def __init__(self, *, video_id: str = "yt123", fail: bool = False) -> None:
        self.video_id = video_id
        self.fail = fail
        self.calls: list[dict] = []

    def upload(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("upload exploded")
        return {
            "video_id": self.video_id,
            "url": f"https://www.youtube.com/watch?v={self.video_id}",
        }


@pytest.fixture()
def tmp_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("SIGNAL_AGENT_ROOT", str(tmp_path))
    monkeypatch.delenv("LETTERS_OF_LIGHT_YOUTUBE_CLIENT_SECRETS", raising=False)
    monkeypatch.delenv("LETTERS_OF_LIGHT_YOUTUBE_TOKEN_FILE", raising=False)
    return tmp_path


def test_publish_youtube_requires_release_json(tmp_state: Path) -> None:
    with pytest.raises(MissingReleaseError, match="release.json"):
        publish_youtube("missing")


def test_publish_youtube_requires_approved_release(tmp_state: Path) -> None:
    _make_release(tmp_state, approved=False)

    with pytest.raises(ReleaseNotApprovedError, match="approved"):
        publish_youtube("abc123", uploader=FakeUploader())


def test_publish_youtube_requires_video(tmp_state: Path) -> None:
    _make_release(tmp_state, video=False)

    with pytest.raises(VideoMissingError, match="final.mp4"):
        publish_youtube("abc123", uploader=FakeUploader())


def test_publish_youtube_reports_missing_credentials(tmp_state: Path) -> None:
    letter_dir = _make_release(tmp_state)

    with pytest.raises(MissingCredentialsError, match="LETTERS_OF_LIGHT_YOUTUBE_CLIENT_SECRETS"):
        publish_youtube("abc123")

    release = json.loads((letter_dir / "release.json").read_text(encoding="utf-8"))
    assert release["targets"]["youtube"]["status"] == "failed"
    assert release["events"][-1]["event_type"] == "ReleaseYouTubePublishFailed"


def test_publish_youtube_mocked_upload_updates_release_and_public_log(tmp_state: Path) -> None:
    letter_dir = _make_release(tmp_state, public_log=True)
    uploader = FakeUploader(video_id="yt456")

    result = publish_youtube("abc123", privacy_status="unlisted", uploader=uploader)

    assert result["video_id"] == "yt456"
    assert result["url"] == "https://www.youtube.com/watch?v=yt456"
    assert result["privacy_status"] == "unlisted"
    assert uploader.calls[0]["privacy_status"] == "unlisted"
    assert uploader.calls[0]["video_path"] == letter_dir / "release_export" / "final.mp4"
    assert uploader.calls[0]["title"] == "Release from release"
    assert "https://example.test/letters/abc123/" in uploader.calls[0]["description"]
    assert uploader.calls[0]["tags"] == ["Letters of Light", "release"]

    release = json.loads((letter_dir / "release.json").read_text(encoding="utf-8"))
    youtube = release["targets"]["youtube"]
    assert youtube["status"] == "published"
    assert youtube["platform_id"] == "yt456"
    assert youtube["url"] == "https://www.youtube.com/watch?v=yt456"
    assert release["events"][-1]["event_type"] == "ReleaseYouTubePublished"

    public_log = json.loads((letter_dir / "public_release_log.json").read_text(encoding="utf-8"))
    assert public_log["social_urls"]["youtube"] == "https://www.youtube.com/watch?v=yt456"


def test_publish_youtube_repeated_publish_does_not_upload_again(tmp_state: Path) -> None:
    letter_dir = _make_release(tmp_state)
    first = FakeUploader(video_id="yt789")
    publish_youtube("abc123", uploader=first)

    second = FakeUploader(video_id="yt999")
    result = publish_youtube("abc123", uploader=second)

    assert result["skipped"] is True
    assert result["video_id"] == "yt789"
    assert second.calls == []
    release = json.loads((letter_dir / "release.json").read_text(encoding="utf-8"))
    assert [event["event_type"] for event in release["events"]].count("ReleaseYouTubePublished") == 1


def test_publish_youtube_failure_writes_error_status(tmp_state: Path) -> None:
    letter_dir = _make_release(tmp_state)

    with pytest.raises(PublisherError, match="upload exploded"):
        publish_youtube("abc123", uploader=FakeUploader(fail=True))

    release = json.loads((letter_dir / "release.json").read_text(encoding="utf-8"))
    youtube = release["targets"]["youtube"]
    assert youtube["status"] == "failed"
    assert youtube["error"]["message"] == "YouTube publish failed: upload exploded"
    assert release["events"][-1]["event_type"] == "ReleaseYouTubePublishFailed"
    assert release["events"][-1]["error"]["message"] == "YouTube publish failed: upload exploded"


def test_release_server_renders_youtube_action() -> None:
    html = _render_page()

    assert "/api/publish/youtube" in html
    assert "Publish YouTube" in html
    assert "Unlisted" in html


def test_release_server_youtube_api_route(monkeypatch: pytest.MonkeyPatch, tmp_state: Path) -> None:
    calls = []

    def fake_publish(letter_id: str, *, privacy_status: str, force: bool):
        calls.append(
            {
                "letter_id": letter_id,
                "privacy_status": privacy_status,
                "force": force,
            }
        )
        return {
            "letter_id": letter_id,
            "platform": "youtube",
            "platform_id": "yt123",
            "url": "https://www.youtube.com/watch?v=yt123",
        }

    monkeypatch.setattr(release_server, "publish_youtube", fake_publish)
    server = ReleaseServer(("127.0.0.1", 0), ReleaseRequestHandler)
    server.quiet = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    conn = None

    try:
        conn = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        body = json.dumps(
            {
                "letter_id": "abc123",
                "privacy_status": "private",
                "force": True,
            }
        )
        conn.request(
            "POST",
            "/api/publish/youtube",
            body=body,
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
    finally:
        if conn is not None:
            conn.close()
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert response.status == 200
    assert payload["ok"] is True
    assert calls == [
        {
            "letter_id": "abc123",
            "privacy_status": "private",
            "force": True,
        }
    ]
