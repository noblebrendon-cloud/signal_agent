from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.letters_of_light.release_site import publish_release_site


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _make_exported_release(root: Path, letter_id: str = "abc123") -> Path:
    letter_dir = root / "data" / "state" / "letters_of_light" / letter_id
    export_dir = letter_dir / "release_export"
    export_dir.mkdir(parents=True, exist_ok=True)

    _write_json(
        letter_dir / "release.json",
        {
            "letter_id": letter_id,
            "campaign_id": "lol-release-abc123",
            "release_state": "exported",
            "approved": True,
            "title": "The Letter of Release",
            "theme": "release",
            "scripture_ref": "Psalm 46:10",
            "assets": {
                "video_path": "",
                "visual_path": "",
            },
            "targets": {
                "site": {
                    "enabled": True,
                    "status": "pending",
                    "url": None,
                }
            },
            "events": [],
        },
    )
    _write_json(
        letter_dir / "routing.json",
        {
            "facebook": {
                "message": "A release reflection.",
                "hashtags": ["#LettersOfLight"],
            },
            "youtube": {
                "description": "A short release reflection.",
            },
            "x": {
                "tweets": ["Release what is no longer yours to carry."],
            },
        },
    )
    _write_json(
        letter_dir / "letter.json",
        {
            "letter_id": letter_id,
            "video_path": "",
            "visual_path": "",
        },
    )
    (export_dir / "site.md").write_text(
        "# The Letter of Release\n\n"
        "Release what has been holding your breath hostage.\n\n"
        "---\n\n"
        "*Psalm 46:10*\n\n"
        "## Reflect\n\n"
        "1. What are you ready to release?\n"
        "2. What becomes possible after that?\n",
        encoding="utf-8",
    )
    (export_dir / "final.mp4").write_bytes(b"fake mp4")
    (export_dir / "visual.png").write_bytes(b"fake png")
    _write_json(export_dir / "asset_manifest.json", {"canonical_url": "old"})

    return letter_dir


@pytest.fixture()
def tmp_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("SIGNAL_AGENT_ROOT", str(tmp_path))
    return tmp_path


def test_publish_release_site_creates_static_page_and_updates_release(
    tmp_state: Path,
    tmp_path: Path,
) -> None:
    letter_id = "abc123"
    letter_dir = _make_exported_release(tmp_state, letter_id)
    site_root = tmp_path / "site"
    site_root.mkdir()
    (site_root / "index.html").write_text("<html></html>", encoding="utf-8")

    result = publish_release_site(
        letter_id,
        site_root=str(site_root),
        base_url="https://example.test",
    )

    canonical_url = "https://example.test/letters/abc123/"
    page_path = site_root / "letters" / "abc123" / "index.html"
    assert result["canonical_url"] == canonical_url
    assert page_path.exists()
    assert "The Letter of Release" in page_path.read_text(encoding="utf-8")
    assert (site_root / "assets" / "letters" / "abc123" / "final.mp4").read_bytes() == b"fake mp4"

    release = json.loads((letter_dir / "release.json").read_text(encoding="utf-8"))
    assert release["release_state"] == "published"
    assert release["canonical_url"] == canonical_url
    assert release["targets"]["site"]["status"] == "published"
    assert release["events"][-1]["event_type"] == "ReleaseSitePublished"


def test_publish_release_site_refreshes_social_exports_with_canonical_url(
    tmp_state: Path,
    tmp_path: Path,
) -> None:
    letter_id = "abc123"
    letter_dir = _make_exported_release(tmp_state, letter_id)
    site_root = tmp_path / "site"
    site_root.mkdir()
    (site_root / "index.html").write_text("<html></html>", encoding="utf-8")

    publish_release_site(letter_id, site_root=str(site_root), base_url="https://example.test")

    export_dir = letter_dir / "release_export"
    assert "https://example.test/letters/abc123/" in (export_dir / "facebook.txt").read_text(encoding="utf-8")
    assert "https://example.test/letters/abc123/" in (export_dir / "instagram.txt").read_text(encoding="utf-8")
    assert "https://example.test/letters/abc123/" in (export_dir / "x_thread.txt").read_text(encoding="utf-8")
    manifest = json.loads((export_dir / "asset_manifest.json").read_text(encoding="utf-8"))
    assert manifest["canonical_url"] == "https://example.test/letters/abc123/"


def test_publish_release_site_requires_exported_release(tmp_state: Path, tmp_path: Path) -> None:
    letter_id = "abc123"
    letter_dir = _make_exported_release(tmp_state, letter_id)
    release_path = letter_dir / "release.json"
    release = json.loads(release_path.read_text(encoding="utf-8"))
    release["release_state"] = "approved"
    release_path.write_text(json.dumps(release, indent=2), encoding="utf-8")

    site_root = tmp_path / "site"
    site_root.mkdir()
    (site_root / "index.html").write_text("<html></html>", encoding="utf-8")

    with pytest.raises(RuntimeError, match="exported"):
        publish_release_site(letter_id, site_root=str(site_root))
