from __future__ import annotations

import base64
import os
from email.message import Message
from email.utils import parseaddr
from pathlib import Path
from typing import Any, Protocol

from signal_agent.media_opportunities.ledgers import repo_root
from signal_agent.media_opportunities.service import MediaOpportunityError


GMAIL_CLIENT_SECRETS_ENV = "MEDIA_OPPORTUNITIES_GMAIL_CLIENT_SECRETS"
GMAIL_TOKEN_FILE_ENV = "MEDIA_OPPORTUNITIES_GMAIL_TOKEN_FILE"
GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_API_SERVICE_NAME = "gmail"
GMAIL_API_VERSION = "v1"


class GmailReadonlySource(Protocol):
    def messages_for_label(self, label: str, *, limit: int | None = None) -> list[dict[str, Any]]:
        ...


class GoogleGmailReadonlySource:
    def __init__(self, *, client_secrets_path: Path, token_path: Path) -> None:
        self.client_secrets_path = client_secrets_path
        self.token_path = token_path

    @classmethod
    def from_environment(cls) -> "GoogleGmailReadonlySource":
        client_secrets = os.environ.get(GMAIL_CLIENT_SECRETS_ENV, "").strip()
        if not client_secrets:
            raise MediaOpportunityError(f"{GMAIL_CLIENT_SECRETS_ENV} must point to a Google OAuth client secrets JSON file")
        client_secrets_path = Path(client_secrets).expanduser()
        if not client_secrets_path.exists() or not client_secrets_path.is_file():
            raise MediaOpportunityError(f"{GMAIL_CLIENT_SECRETS_ENV} does not point to an existing file: {client_secrets_path}")
        token_path = Path(
            os.environ.get(GMAIL_TOKEN_FILE_ENV, "").strip() or _default_token_path()
        ).expanduser()
        _ensure_token_path_allowed(token_path)
        return cls(client_secrets_path=client_secrets_path, token_path=token_path)

    def messages_for_label(self, label: str, *, limit: int | None = None) -> list[dict[str, Any]]:
        service = self._build_service()
        label_id = _find_label_id(service, label)
        messages: list[dict[str, Any]] = []
        page_token = None
        while True:
            remaining = None if limit is None else max(limit - len(messages), 0)
            if remaining == 0:
                break
            request = service.users().messages().list(
                userId="me",
                labelIds=[label_id],
                maxResults=min(remaining or 100, 100),
                pageToken=page_token,
            )
            response = request.execute()
            for item in response.get("messages") or []:
                message_id = str(item.get("id") or "").strip()
                if not message_id:
                    continue
                messages.append(_load_message(service, message_id))
                if limit is not None and len(messages) >= limit:
                    break
            page_token = response.get("nextPageToken")
            if not page_token or (limit is not None and len(messages) >= limit):
                break
        return messages

    def _build_service(self) -> Any:
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise MediaOpportunityError(
                "Gmail intake requires google-api-python-client, google-auth-oauthlib, and google-auth-httplib2"
            ) from exc

        credentials = None
        if self.token_path.exists():
            credentials = Credentials.from_authorized_user_file(str(self.token_path), [GMAIL_READONLY_SCOPE])
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        if not credentials or not credentials.valid:
            flow = InstalledAppFlow.from_client_secrets_file(str(self.client_secrets_path), [GMAIL_READONLY_SCOPE])
            credentials = flow.run_local_server(port=0)

        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_path.write_text(credentials.to_json(), encoding="utf-8")
        return build(GMAIL_API_SERVICE_NAME, GMAIL_API_VERSION, credentials=credentials)


def _find_label_id(service: Any, label_name: str) -> str:
    response = service.users().labels().list(userId="me").execute()
    target = str(label_name or "").strip().lower()
    for label in response.get("labels") or []:
        if str(label.get("name") or "").strip().lower() == target:
            label_id = str(label.get("id") or "").strip()
            if label_id:
                return label_id
    raise MediaOpportunityError(f"gmail_label_not_found:{label_name}")


def _load_message(service: Any, message_id: str) -> dict[str, Any]:
    payload = service.users().messages().get(userId="me", id=message_id, format="full").execute()
    headers = _headers(payload)
    thread_id = str(payload.get("threadId") or "")
    text = _body_text(payload.get("payload") or {}) or str(payload.get("snippet") or "")
    if thread_id:
        thread_text = _thread_text(service, thread_id)
        if thread_text:
            text = thread_text
    sender = headers.get("from", "")
    sender_name, _sender_email = parseaddr(sender)
    return {
        "id": str(payload.get("id") or message_id),
        "message_id": str(payload.get("id") or message_id),
        "thread_id": thread_id,
        "label_ids": list(payload.get("labelIds") or ()),
        "subject": headers.get("subject"),
        "from": sender,
        "sender_name": sender_name or None,
        "date": headers.get("date"),
        "snippet": payload.get("snippet"),
        "text": text,
    }


def _thread_text(service: Any, thread_id: str) -> str:
    response = service.users().threads().get(userId="me", id=thread_id, format="full").execute()
    parts: list[str] = []
    for message in response.get("messages") or ():
        if not isinstance(message, dict):
            continue
        text = _body_text(message.get("payload") or {}) or str(message.get("snippet") or "")
        if text.strip():
            parts.append(text.strip())
    return "\n\n--- Gmail thread message ---\n\n".join(parts)


def _headers(payload: dict[str, Any]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for item in (payload.get("payload") or {}).get("headers") or ():
        name = str(item.get("name") or "").lower()
        value = str(item.get("value") or "")
        if name:
            headers[name] = value
    return headers


def _body_text(part: dict[str, Any]) -> str:
    mime_type = str(part.get("mimeType") or "")
    body = part.get("body") if isinstance(part.get("body"), dict) else {}
    data = str(body.get("data") or "")
    if data and mime_type == "text/plain":
        return _decode_base64url(data)
    for child in part.get("parts") or ():
        if isinstance(child, dict):
            text = _body_text(child)
            if text:
                return text
    if data and mime_type == "text/html":
        return _html_to_text(_decode_base64url(data))
    return ""


def _decode_base64url(data: str) -> str:
    padded = data + ("=" * (-len(data) % 4))
    return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8", errors="replace").strip()


def _html_to_text(value: str) -> str:
    import re

    text = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(text.split())


def _default_token_path() -> Path:
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "SignalAgent" / "media_opportunities_gmail_token.json"
    return Path.home() / ".config" / "signal_agent" / "media_opportunities_gmail_token.json"


def _ensure_token_path_allowed(token_path: Path) -> None:
    root = repo_root().resolve()
    try:
        token_path.resolve().relative_to(root)
    except ValueError:
        return
    raise MediaOpportunityError(f"{GMAIL_TOKEN_FILE_ENV} must be outside the repository: {token_path}")
