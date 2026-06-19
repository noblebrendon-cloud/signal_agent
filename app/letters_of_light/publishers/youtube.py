"""
YouTube publisher for Letters of Light releases.

Credentials are loaded from local environment/config only. Token material is
stored outside the repository by default.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Protocol

from app.letters_of_light.publishers.base import (
    DependencyMissingError,
    MissingCredentialsError,
    MissingReleaseError,
    PublishResult,
    PublisherError,
    ReleaseNotApprovedError,
    VideoMissingError,
    validate_privacy_status,
)
from app.letters_of_light.release import (
    _get_root,
    _letter_dir,
    _read_json,
    _resolve_artifact_path,
    _utc_now,
    _write_json,
)


YOUTUBE_CLIENT_SECRETS_ENV = "LETTERS_OF_LIGHT_YOUTUBE_CLIENT_SECRETS"
YOUTUBE_TOKEN_FILE_ENV = "LETTERS_OF_LIGHT_YOUTUBE_TOKEN_FILE"
YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"
YOUTUBE_CATEGORY_ID = "22"


class YouTubeUploader(Protocol):
    def upload(
        self,
        *,
        video_path: Path,
        title: str,
        description: str,
        tags: List[str],
        privacy_status: str,
    ) -> PublishResult | Dict[str, Any]:
        ...


class GoogleYouTubeUploader:
    def __init__(self, *, client_secrets_path: Path, token_path: Path) -> None:
        self.client_secrets_path = client_secrets_path
        self.token_path = token_path

    @classmethod
    def from_environment(cls) -> "GoogleYouTubeUploader":
        client_secrets = os.environ.get(YOUTUBE_CLIENT_SECRETS_ENV, "").strip()
        if not client_secrets:
            raise MissingCredentialsError(
                f"{YOUTUBE_CLIENT_SECRETS_ENV} must point to a Google OAuth client secrets JSON file"
            )

        client_secrets_path = Path(client_secrets).expanduser()
        if not client_secrets_path.exists() or not client_secrets_path.is_file():
            raise MissingCredentialsError(
                f"{YOUTUBE_CLIENT_SECRETS_ENV} does not point to an existing file: {client_secrets_path}"
            )

        token_path = Path(
            os.environ.get(YOUTUBE_TOKEN_FILE_ENV, "").strip() or _default_token_path()
        ).expanduser()
        _ensure_token_path_allowed(token_path)
        return cls(client_secrets_path=client_secrets_path, token_path=token_path)

    def upload(
        self,
        *,
        video_path: Path,
        title: str,
        description: str,
        tags: List[str],
        privacy_status: str,
    ) -> PublishResult:
        youtube = self._build_service()
        media_body = _media_file_upload(video_path)
        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": YOUTUBE_CATEGORY_ID,
            },
            "status": {
                "privacyStatus": privacy_status,
            },
        }
        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media_body,
        )
        response = request.execute()
        video_id = str(response.get("id") or "").strip()
        if not video_id:
            raise PublisherError("YouTube upload completed without returning a video id")
        return PublishResult(
            platform="youtube",
            platform_id=video_id,
            url=_watch_url(video_id),
            metadata={"privacy_status": privacy_status},
        )

    def _build_service(self) -> Any:
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise DependencyMissingError(
                "YouTube upload requires google-api-python-client, google-auth-oauthlib, "
                "and google-auth-httplib2"
            ) from exc

        credentials = None
        if self.token_path.exists():
            credentials = Credentials.from_authorized_user_file(
                str(self.token_path),
                [YOUTUBE_UPLOAD_SCOPE],
            )

        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())

        if not credentials or not credentials.valid:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(self.client_secrets_path),
                [YOUTUBE_UPLOAD_SCOPE],
            )
            credentials = flow.run_local_server(port=0)

        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_path.write_text(credentials.to_json(), encoding="utf-8")
        return build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION, credentials=credentials)


def publish_youtube(
    letter_id: str,
    *,
    privacy_status: str = "unlisted",
    force: bool = False,
    uploader: Optional[YouTubeUploader] = None,
) -> Dict[str, Any]:
    privacy_status = validate_privacy_status(privacy_status)
    letter_dir = _letter_dir(letter_id)
    release_path = letter_dir / "release.json"
    release = _read_json(release_path)
    if not release:
        raise MissingReleaseError(f"release.json not found for letter: {letter_id}")

    if not release.get("approved"):
        _record_youtube_failure(
            release_path,
            release,
            privacy_status=privacy_status,
            error=ReleaseNotApprovedError("Release must be approved before YouTube publish"),
        )
        raise ReleaseNotApprovedError("Release must be approved before YouTube publish")

    existing = _existing_youtube_result(release)
    if existing and not force:
        return {
            "letter_id": letter_id,
            "status": "published",
            "platform": "youtube",
            "platform_id": existing["platform_id"],
            "video_id": existing["platform_id"],
            "url": existing["url"],
            "privacy_status": existing.get("privacy_status"),
            "skipped": True,
            "reason": "already_published",
        }

    payload = _youtube_payload(letter_dir, release)
    video_path = _select_video_path(letter_dir, release, payload)
    if not video_path or not video_path.exists() or not video_path.is_file() or video_path.stat().st_size <= 0:
        error = VideoMissingError(f"final.mp4 or configured YouTube video_path is missing or empty: {video_path}")
        _record_youtube_failure(release_path, release, privacy_status=privacy_status, error=error)
        raise error

    title = _publish_title(letter_dir, release, payload)
    description = _publish_description(letter_dir, release, payload)
    tags = _publish_tags(payload)

    try:
        active_uploader = uploader or GoogleYouTubeUploader.from_environment()
        raw_result = active_uploader.upload(
            video_path=video_path,
            title=title,
            description=description,
            tags=tags,
            privacy_status=privacy_status,
        )
        result = _normalize_upload_result(raw_result)
    except PublisherError as exc:
        _record_youtube_failure(release_path, release, privacy_status=privacy_status, error=exc)
        raise
    except Exception as exc:
        wrapped = PublisherError(f"YouTube publish failed: {exc}")
        _record_youtube_failure(release_path, release, privacy_status=privacy_status, error=wrapped)
        raise wrapped from exc

    now = _utc_now()
    _record_youtube_success(
        release_path,
        release,
        video_id=result.platform_id,
        url=result.url,
        title=title,
        description=description,
        tags=tags,
        privacy_status=privacy_status,
        video_path=video_path,
        now=now,
        forced=force,
    )
    _write_public_release_log(letter_dir, result.url, now)

    return {
        "letter_id": letter_id,
        "status": "published",
        "platform": "youtube",
        "platform_id": result.platform_id,
        "video_id": result.platform_id,
        "url": result.url,
        "privacy_status": privacy_status,
        "skipped": False,
    }


def _default_token_path() -> Path:
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "SignalAgent" / "letters_of_light" / "youtube_token.json"
    return Path.home() / ".config" / "signal_agent" / "letters_of_light" / "youtube_token.json"


def _path_is_inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _ensure_token_path_allowed(token_path: Path) -> None:
    root = _get_root()
    if _path_is_inside(token_path, root):
        raise MissingCredentialsError(
            f"{YOUTUBE_TOKEN_FILE_ENV} must be outside the repository and data/state runtime tree: {token_path}"
        )


def _media_file_upload(video_path: Path) -> Any:
    try:
        from googleapiclient.http import MediaFileUpload
    except ImportError as exc:
        raise DependencyMissingError("YouTube upload requires google-api-python-client") from exc
    return MediaFileUpload(str(video_path), chunksize=-1, resumable=True)


def _watch_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def _youtube_payload(letter_dir: Path, release: Dict[str, Any]) -> Dict[str, Any]:
    release_target = release.get("targets", {}).get("youtube", {})
    payload: Dict[str, Any] = {}
    if isinstance(release_target, dict) and isinstance(release_target.get("payload"), dict):
        payload.update(release_target["payload"])

    routing = _read_json(letter_dir / "routing.json")
    routing_youtube = routing.get("youtube", {})
    if isinstance(routing_youtube, dict):
        payload = {**routing_youtube, **payload}
    return payload


def _read_export_text(letter_dir: Path, filename: str) -> str:
    path = letter_dir / "release_export" / filename
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _publish_title(letter_dir: Path, release: Dict[str, Any], payload: Dict[str, Any]) -> str:
    return (
        str(payload.get("title") or "").strip()
        or _read_export_text(letter_dir, "youtube_title.txt")
        or str(release.get("title") or "").strip()
        or "Letter of Light"
    )


def _publish_description(letter_dir: Path, release: Dict[str, Any], payload: Dict[str, Any]) -> str:
    description = (
        str(payload.get("description") or "").strip()
        or _read_export_text(letter_dir, "youtube_description.txt")
    )
    canonical_url = str(release.get("canonical_url") or "").strip()
    if canonical_url and canonical_url not in description:
        description = (description + "\n\n" + canonical_url).strip()
    return description


def _publish_tags(payload: Dict[str, Any]) -> List[str]:
    raw = payload.get("tags") or payload.get("keywords") or []
    if isinstance(raw, str):
        items: Iterable[Any] = raw.split(",")
    elif isinstance(raw, list):
        items = raw
    else:
        items = []

    tags: List[str] = []
    seen = set()
    for item in items:
        tag = str(item).strip().lstrip("#")
        if not tag or tag in seen:
            continue
        seen.add(tag)
        tags.append(tag)
    return tags


def _select_video_path(letter_dir: Path, release: Dict[str, Any], payload: Dict[str, Any]) -> Optional[Path]:
    candidates: List[Any] = [
        letter_dir / "release_export" / "final.mp4",
        payload.get("video_path"),
        release.get("assets", {}).get("video_path"),
    ]
    manifest = _read_json(letter_dir / "release_export" / "asset_manifest.json")
    if manifest.get("video_path"):
        candidates.append(manifest.get("video_path"))

    for candidate in candidates:
        if not candidate:
            continue
        path = candidate if isinstance(candidate, Path) else _resolve_artifact_path(str(candidate))
        if path.exists() and path.is_file() and path.stat().st_size > 0:
            return path

    first = candidates[0]
    return first if isinstance(first, Path) else None


def _normalize_upload_result(raw_result: PublishResult | Dict[str, Any]) -> PublishResult:
    if isinstance(raw_result, PublishResult):
        if not raw_result.platform_id:
            raise PublisherError("YouTube upload returned an empty video id")
        return raw_result

    video_id = str(
        raw_result.get("video_id")
        or raw_result.get("platform_id")
        or raw_result.get("id")
        or ""
    ).strip()
    if not video_id:
        raise PublisherError("YouTube upload returned an empty video id")
    return PublishResult(
        platform="youtube",
        platform_id=video_id,
        url=str(raw_result.get("url") or _watch_url(video_id)),
        metadata=dict(raw_result.get("metadata") or {}),
    )


def _existing_youtube_result(release: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    target = release.get("targets", {}).get("youtube", {})
    if not isinstance(target, dict) or target.get("status") != "published":
        return None

    platform_id = str(target.get("platform_id") or target.get("video_id") or "").strip()
    url = str(target.get("url") or "").strip()
    if not url and platform_id:
        url = _watch_url(platform_id)
    if not platform_id or not url:
        return None
    return {
        "platform_id": platform_id,
        "url": url,
        "privacy_status": target.get("privacy_status"),
    }


def _record_youtube_success(
    release_path: Path,
    release: Dict[str, Any],
    *,
    video_id: str,
    url: str,
    title: str,
    description: str,
    tags: List[str],
    privacy_status: str,
    video_path: Path,
    now: str,
    forced: bool,
) -> None:
    target = release.setdefault("targets", {}).setdefault("youtube", {})
    target.update(
        {
            "enabled": True,
            "status": "published",
            "platform_id": video_id,
            "video_id": video_id,
            "url": url,
            "privacy_status": privacy_status,
            "title": title,
            "description": description,
            "tags": tags,
            "video_path": str(video_path),
            "published_at": now,
            "error": None,
        }
    )
    release["updated_at"] = now
    release.setdefault("events", []).append(
        {
            "event_type": "ReleaseYouTubePublished",
            "created_at": now,
            "status": "published",
            "platform_id": video_id,
            "url": url,
            "privacy_status": privacy_status,
            "forced": forced,
        }
    )
    _write_json(release_path, release)


def _record_youtube_failure(
    release_path: Path,
    release: Dict[str, Any],
    *,
    privacy_status: str,
    error: BaseException,
) -> None:
    now = _utc_now()
    error_payload = {
        "type": error.__class__.__name__,
        "message": str(error),
    }
    target = release.setdefault("targets", {}).setdefault("youtube", {})
    target.update(
        {
            "enabled": True,
            "status": "failed",
            "privacy_status": privacy_status,
            "error": error_payload,
            "failed_at": now,
        }
    )
    release["updated_at"] = now
    release.setdefault("events", []).append(
        {
            "event_type": "ReleaseYouTubePublishFailed",
            "created_at": now,
            "status": "failed",
            "privacy_status": privacy_status,
            "error": error_payload,
        }
    )
    _write_json(release_path, release)


def _write_public_release_log(letter_dir: Path, url: str, now: str) -> None:
    log_path = letter_dir / "public_release_log.json"
    if not log_path.exists():
        return

    try:
        payload = json.loads(log_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    if not isinstance(payload, dict):
        return

    social_urls = payload.setdefault("social_urls", {})
    if isinstance(social_urls, dict):
        social_urls["youtube"] = url
    payload["updated_at"] = now
    _write_json(log_path, payload)
