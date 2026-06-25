from __future__ import annotations

import hashlib
import os
import re
import secrets
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from app.retention.dispatch import plan_dispatch
from app.retention.identity import event_id_from_material
from app.retention.jsonl_store import append_record, ensure_required_state_files
from app.retention.models import PUBLIC_WEBSITE_SOURCE, build_contact_snapshot
from app.retention.transitions import evaluate_transition, load_latest_contact_snapshot


DATA_ROOT_ENV = "LETTERS_OF_LIGHT_DATA_ROOT"
SUBSCRIBER_DB_ENV = "LETTERS_OF_LIGHT_SUBSCRIBER_DB"
SCHEMA_VERSION = "1.0"
DEFAULT_CONFIRMATION_TTL = timedelta(hours=24)
PRIVATE_IDENTIFIER_KIND = "private_contact_ref"
PUBLIC_STATIC_PATH_PARTS = {
    "public",
    "static",
    "site",
    "sites",
    "site_laviathon",
    "site_refactor_working",
    "githubpage",
}
BLOCKED_ROOTS = (
    Path("E:/signal_agent"),
    Path("E:/githubpage"),
)
EMAIL_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$")


class SubscriberCoreError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class SubscriberConfig:
    data_root: Path
    subscriber_db: Path


@dataclass(frozen=True)
class SignupResult:
    status: str
    subscriber_id: str
    token: str | None = field(default=None, repr=False)
    token_expires_at: str | None = None
    duplicate: bool = False


@dataclass(frozen=True)
class ConfirmationResult:
    status: str
    subscriber_id: str
    contact_id: str
    retention_event_id: str
    unsubscribe_token: str = field(repr=False)


@dataclass(frozen=True)
class UnsubscribeResult:
    status: str
    subscriber_id: str
    contact_id: str
    retention_event_id: str
    dispatch_blocked: bool


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _resolve_path(value: str) -> Path:
    return Path(value).expanduser().resolve(strict=False)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _has_git_parent(path: Path) -> bool:
    current = path
    if current.suffix:
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return True
    return False


def _has_public_static_part(path: Path) -> bool:
    return any(part.lower() in PUBLIC_STATIC_PATH_PARTS for part in path.parts)


def _assert_private_path(path: Path, *, code: str) -> None:
    resolved = path.resolve(strict=False)
    blocked_roots = [root.resolve(strict=False) for root in BLOCKED_ROOTS]
    blocked_roots.append(_repo_root().resolve(strict=False))

    if any(resolved == root or _is_relative_to(resolved, root) for root in blocked_roots):
        raise SubscriberCoreError(code)
    if _has_git_parent(resolved):
        raise SubscriberCoreError(code)
    if _has_public_static_part(resolved):
        raise SubscriberCoreError(code)


def resolve_subscriber_config(env: Mapping[str, str] | None = None) -> SubscriberConfig:
    source = env or os.environ
    root_value = str(source.get(DATA_ROOT_ENV) or "").strip()
    db_value = str(source.get(SUBSCRIBER_DB_ENV) or "").strip()
    if not root_value:
        raise SubscriberCoreError("subscriber_data_root_required")
    if not db_value:
        raise SubscriberCoreError("subscriber_db_required")

    data_root = _resolve_path(root_value)
    subscriber_db = Path(db_value).expanduser()
    if not subscriber_db.is_absolute():
        subscriber_db = data_root / subscriber_db
    subscriber_db = subscriber_db.resolve(strict=False)

    _assert_private_path(data_root, code="subscriber_data_root_not_private")
    _assert_private_path(subscriber_db, code="subscriber_db_not_private")
    if not _is_relative_to(subscriber_db, data_root):
        raise SubscriberCoreError("subscriber_db_outside_data_root")
    if subscriber_db == data_root or subscriber_db.suffix.lower() not in {".db", ".sqlite", ".sqlite3"}:
        raise SubscriberCoreError("subscriber_db_invalid")

    return SubscriberConfig(data_root=data_root, subscriber_db=subscriber_db)


def normalize_email(email: str) -> str:
    normalized = str(email or "").strip().lower()
    if not normalized or len(normalized) > 254:
        raise SubscriberCoreError("invalid_email")
    if any(ord(char) < 33 or ord(char) > 126 for char in normalized):
        raise SubscriberCoreError("invalid_email")
    if normalized.count("@") != 1 or not EMAIL_RE.fullmatch(normalized):
        raise SubscriberCoreError("invalid_email")

    local, domain = normalized.rsplit("@", 1)
    if len(local) > 64 or local.startswith(".") or local.endswith(".") or ".." in local:
        raise SubscriberCoreError("invalid_email")
    labels = domain.split(".")
    if any(not label or label.startswith("-") or label.endswith("-") for label in labels):
        raise SubscriberCoreError("invalid_email")
    return normalized


def hash_token(token: str) -> str:
    value = str(token or "").strip()
    if not value:
        raise SubscriberCoreError("invalid_token")
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _new_token() -> str:
    return secrets.token_urlsafe(32)


def _new_subscriber_id() -> str:
    return f"lol_sub_{secrets.token_hex(12)}"


def _new_contact_id() -> str:
    return f"ctc_lol_{secrets.token_hex(16)}"


def _private_identifier_hash(contact_id: str) -> str:
    return f"private-random:v1:{_sha256_text(contact_id)}"


def _connect(config: SubscriberConfig | None = None) -> sqlite3.Connection:
    resolved = config or resolve_subscriber_config()
    try:
        resolved.data_root.mkdir(parents=True, exist_ok=True)
        resolved.subscriber_db.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(resolved.subscriber_db)
    except OSError as exc:
        raise SubscriberCoreError("subscriber_storage_unavailable") from exc
    except sqlite3.Error as exc:
        raise SubscriberCoreError("subscriber_db_open_failed") from exc

    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        _ensure_schema(conn)
    except sqlite3.Error as exc:
        conn.close()
        raise SubscriberCoreError("subscriber_db_schema_failed") from exc
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS subscribers (
            subscriber_id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            contact_id TEXT NOT NULL UNIQUE,
            contact_identifier_hash TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL CHECK (status IN ('pending', 'confirmed', 'unsubscribed')),
            consent_version INTEGER NOT NULL DEFAULT 0,
            pending_token_hash TEXT,
            pending_token_expires_at TEXT,
            pending_token_used_at TEXT,
            unsubscribe_token_hash TEXT,
            unsubscribe_token_used_at TEXT,
            delivery_provider TEXT,
            delivery_reference TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            confirmed_at TEXT,
            unsubscribed_at TEXT
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_subscribers_pending_token ON subscribers(pending_token_hash)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_subscribers_unsubscribe_token ON subscribers(unsubscribe_token_hash)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT OR REPLACE INTO schema_metadata(key, value) VALUES('schema_version', ?)",
        (SCHEMA_VERSION,),
    )
    conn.commit()


def _fetch_by_email(conn: sqlite3.Connection, email: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM subscribers WHERE email = ?", (email,)).fetchone()


def _fetch_by_token_hash(conn: sqlite3.Connection, column: str, token_hash: str) -> sqlite3.Row | None:
    if column not in {"pending_token_hash", "unsubscribe_token_hash"}:
        raise SubscriberCoreError("invalid_token_lookup")
    return conn.execute(f"SELECT * FROM subscribers WHERE {column} = ?", (token_hash,)).fetchone()


def request_signup(
    email: str,
    *,
    now: datetime | None = None,
    token_ttl: timedelta = DEFAULT_CONFIRMATION_TTL,
    config: SubscriberConfig | None = None,
) -> SignupResult:
    normalized_email = normalize_email(email)
    moment = now or _utc_now()
    expires_at = moment + token_ttl

    with _connect(config) as conn:
        row = _fetch_by_email(conn, normalized_email)
        if row is not None:
            return SignupResult(
                status=str(row["status"]),
                subscriber_id=str(row["subscriber_id"]),
                token=None,
                token_expires_at=row["pending_token_expires_at"],
                duplicate=True,
            )

        token = _new_token()
        token_hash = hash_token(token)
        subscriber_id = _new_subscriber_id()
        contact_id = _new_contact_id()
        conn.execute(
            """
            INSERT INTO subscribers(
                subscriber_id,
                email,
                contact_id,
                contact_identifier_hash,
                status,
                consent_version,
                pending_token_hash,
                pending_token_expires_at,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, 'pending', 0, ?, ?, ?, ?)
            """,
            (
                subscriber_id,
                normalized_email,
                contact_id,
                _private_identifier_hash(contact_id),
                token_hash,
                _iso(expires_at),
                _iso(moment),
                _iso(moment),
            ),
        )
        return SignupResult(
            status="pending",
            subscriber_id=subscriber_id,
            token=token,
            token_expires_at=_iso(expires_at),
            duplicate=False,
        )


def _build_retention_event(
    row: sqlite3.Row,
    *,
    event_type: str,
    consent_status: str,
    consent_version: int,
) -> dict[str, Any]:
    identifier_hash = str(row["contact_identifier_hash"])
    contact_id = str(row["contact_id"])
    event_id = event_id_from_material(
        event_type=event_type,
        source=PUBLIC_WEBSITE_SOURCE,
        identifier_hash_value=identifier_hash,
        consent_status=consent_status,
        event_key=f"{row['subscriber_id']}:{consent_version}",
    )
    return {
        "record_type": "canonical_event",
        "schema_version": "1.0",
        "event_id": event_id,
        "event_type": event_type,
        "source": PUBLIC_WEBSITE_SOURCE,
        "source_mode": "confirmed_private_subscriber",
        "scope": "contact",
        "contact_id": contact_id,
        "identifier_kind": PRIVATE_IDENTIFIER_KIND,
        "identifier_hash": identifier_hash,
        "actor": {
            "contact_id": contact_id,
            "identifier_kind": PRIVATE_IDENTIFIER_KIND,
            "identifier_hash": identifier_hash,
            "linkage_status": "private_mapping",
        },
        "consent": {
            "email_marketing_status": consent_status,
            "version": consent_version,
        },
    }


def _append_retention_state(event: dict[str, Any], *, repo_root: Path | None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    previous_snapshot = load_latest_contact_snapshot(str(event["contact_id"]), repo_root=repo_root)
    transition = evaluate_transition(event, previous_snapshot=previous_snapshot)
    contact_snapshot = build_contact_snapshot(
        previous_snapshot=previous_snapshot,
        event=event,
        transition=transition,
    )
    if contact_snapshot is None:
        raise SubscriberCoreError("retention_transition_not_applied")

    try:
        ensure_required_state_files(repo_root=repo_root)
        written_event = append_record("events.jsonl", event, repo_root=repo_root)
        written_transition = append_record("transitions.jsonl", transition, repo_root=repo_root)
        written_contact = append_record("contacts.jsonl", contact_snapshot, repo_root=repo_root)
    except Exception as exc:
        raise SubscriberCoreError("retention_write_failed") from exc

    return written_event, written_transition, written_contact


def confirm_signup(
    token: str,
    *,
    now: datetime | None = None,
    retention_repo_root: Path | None = None,
    config: SubscriberConfig | None = None,
) -> ConfirmationResult:
    token_hash = hash_token(token)
    moment = now or _utc_now()

    with _connect(config) as conn:
        row = _fetch_by_token_hash(conn, "pending_token_hash", token_hash)
        if row is None:
            raise SubscriberCoreError("confirmation_token_invalid")
        if str(row["status"]) != "pending" or row["pending_token_used_at"]:
            raise SubscriberCoreError("confirmation_token_not_active")
        expires_at = _parse_iso(row["pending_token_expires_at"])
        if expires_at is None or expires_at <= moment:
            raise SubscriberCoreError("confirmation_token_expired")

        consent_version = int(row["consent_version"] or 0) + 1
        event = _build_retention_event(
            row,
            event_type="contact_seeded",
            consent_status="opted_in",
            consent_version=consent_version,
        )
        written_event, _, written_contact = _append_retention_state(event, repo_root=retention_repo_root)

        unsubscribe_token = _new_token()
        conn.execute(
            """
            UPDATE subscribers
            SET status = 'confirmed',
                consent_version = ?,
                pending_token_used_at = ?,
                unsubscribe_token_hash = ?,
                unsubscribe_token_used_at = NULL,
                confirmed_at = ?,
                updated_at = ?
            WHERE subscriber_id = ?
            """,
            (
                consent_version,
                _iso(moment),
                hash_token(unsubscribe_token),
                _iso(moment),
                _iso(moment),
                row["subscriber_id"],
            ),
        )
        return ConfirmationResult(
            status=str(written_contact["current_state"]),
            subscriber_id=str(row["subscriber_id"]),
            contact_id=str(row["contact_id"]),
            retention_event_id=str(written_event["event_id"]),
            unsubscribe_token=unsubscribe_token,
        )


def unsubscribe(
    token: str,
    *,
    now: datetime | None = None,
    retention_repo_root: Path | None = None,
    config: SubscriberConfig | None = None,
) -> UnsubscribeResult:
    token_hash = hash_token(token)
    moment = now or _utc_now()

    with _connect(config) as conn:
        row = _fetch_by_token_hash(conn, "unsubscribe_token_hash", token_hash)
        if row is None:
            raise SubscriberCoreError("unsubscribe_token_invalid")
        if str(row["status"]) != "confirmed" or row["unsubscribe_token_used_at"]:
            raise SubscriberCoreError("unsubscribe_token_not_active")

        consent_version = int(row["consent_version"] or 0) + 1
        event = _build_retention_event(
            row,
            event_type="unsubscribe",
            consent_status="opted_out",
            consent_version=consent_version,
        )
        written_event, _, written_contact = _append_retention_state(event, repo_root=retention_repo_root)
        dispatch_plan = plan_dispatch(written_contact, contact_id=str(row["contact_id"]))

        conn.execute(
            """
            UPDATE subscribers
            SET status = 'unsubscribed',
                consent_version = ?,
                unsubscribe_token_used_at = ?,
                unsubscribed_at = ?,
                updated_at = ?
            WHERE subscriber_id = ?
            """,
            (
                consent_version,
                _iso(moment),
                _iso(moment),
                _iso(moment),
                row["subscriber_id"],
            ),
        )
        return UnsubscribeResult(
            status=str(written_contact["current_state"]),
            subscriber_id=str(row["subscriber_id"]),
            contact_id=str(row["contact_id"]),
            retention_event_id=str(written_event["event_id"]),
            dispatch_blocked=dispatch_plan.get("decision") == "blocked",
        )
