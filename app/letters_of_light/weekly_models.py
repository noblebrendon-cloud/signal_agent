from __future__ import annotations

import json
import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any


REQUIRED_FRONTMATTER_FIELDS = (
    "letter_id",
    "title",
    "week_date",
    "scripture_refs",
    "song",
    "audience_notes",
    "status",
    "reflection_questions",
    "closing_prayer",
)
REQUIRED_FIELDS = REQUIRED_FRONTMATTER_FIELDS + ("body",)
ALLOWED_WEEKLY_STATES = {
    "draft",
    "reviewed",
    "approved",
    "published",
    "printed",
    "shared_in_person",
    "archived",
}
POST_APPROVAL_STATES = {"published", "printed", "shared_in_person", "archived"}
WEEKLY_TRANSITIONS: dict[str | None, set[str]] = {
    None: {"draft"},
    "draft": {"reviewed"},
    "reviewed": {"approved"},
    "approved": set(POST_APPROVAL_STATES),
    "published": {"printed", "shared_in_person", "archived"},
    "printed": {"published", "shared_in_person", "archived"},
    "shared_in_person": {"published", "printed", "archived"},
    "archived": set(),
}
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class WeeklyLetterError(Exception):
    """Base error for weekly Letters of Light failures."""


class WeeklyLetterValidationError(WeeklyLetterError):
    """Raised when a canonical weekly letter fails validation."""


class WeeklyTransitionError(WeeklyLetterError):
    """Raised when a weekly letter state transition is invalid."""


class WeeklyExternalActionError(WeeklyLetterError):
    """Raised when a caller attempts an external or irreversible action."""


def derive_letter_id(week_date: str) -> str:
    normalized = str(week_date or "").strip()
    if not _DATE_RE.match(normalized):
        raise WeeklyLetterValidationError(f"malformed_week_date:{week_date}")
    return f"lol_{normalized.replace('-', '_')}"


def stable_json_dumps(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_hash(payload: object) -> str:
    return f"sha256:{sha256(stable_json_dumps(payload).encode('utf-8')).hexdigest()}"


def assert_no_external_action(**flags: Any) -> None:
    for key, value in flags.items():
        if _is_truthy(value):
            raise WeeklyExternalActionError(f"external_action_blocked:{key}")


def can_transition(from_state: str | None, to_state: str) -> bool:
    return to_state in WEEKLY_TRANSITIONS.get(from_state, set())


def require_transition(from_state: str | None, to_state: str) -> None:
    if not can_transition(from_state, to_state):
        source = "missing" if from_state is None else from_state
        raise WeeklyTransitionError(f"invalid_weekly_transition:{source}->{to_state}")


@dataclass(frozen=True)
class WeeklyLetter:
    letter_id: str
    title: str
    week_date: str
    scripture_refs: list[str]
    song: dict[str, str]
    audience_notes: list[str]
    status: str
    body: str
    reflection_questions: list[str]
    closing_prayer: str
    source_path: str = ""
    external_action_allowed: bool = False
    send_externally: bool = False

    @property
    def content_hash(self) -> str:
        return content_hash(self.canonical_payload())

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "letter_id": self.letter_id,
            "title": self.title,
            "week_date": self.week_date,
            "scripture_refs": list(self.scripture_refs),
            "song": dict(self.song),
            "audience_notes": list(self.audience_notes),
            "status": self.status,
            "body": self.body,
            "reflection_questions": list(self.reflection_questions),
            "closing_prayer": self.closing_prayer,
            "external_action_allowed": False,
            "send_externally": False,
        }

    def to_record(self) -> dict[str, Any]:
        return {
            "record_type": "letters_of_light_weekly_letter",
            "schema_version": "1.0",
            **self.canonical_payload(),
            "source_path": self.source_path,
            "content_hash": self.content_hash,
        }


def load_weekly_letter(path: str | Path) -> WeeklyLetter:
    source_path = Path(path)
    metadata, body = parse_json_frontmatter(source_path.read_text(encoding="utf-8"))
    return weekly_letter_from_payload(metadata, body=body, source_path=str(source_path))


def parse_json_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise WeeklyLetterValidationError("missing_json_frontmatter_delimiter")

    end_index = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            end_index = index
            break
    if end_index is None:
        raise WeeklyLetterValidationError("unterminated_json_frontmatter")

    raw_json = "\n".join(lines[1:end_index]).strip()
    if not raw_json:
        raise WeeklyLetterValidationError("empty_json_frontmatter")
    try:
        metadata = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise WeeklyLetterValidationError(f"invalid_json_frontmatter:{exc.msg}") from exc
    if not isinstance(metadata, dict):
        raise WeeklyLetterValidationError("frontmatter_must_be_object")

    body = "\n".join(lines[end_index + 1 :]).strip()
    if not body and isinstance(metadata.get("body"), str):
        body = metadata["body"].strip()
    return metadata, body


def weekly_letter_from_payload(
    payload: dict[str, Any],
    *,
    body: str | None = None,
    source_path: str = "",
) -> WeeklyLetter:
    if not isinstance(payload, dict):
        raise WeeklyLetterValidationError("payload_must_be_object")

    missing = [field for field in REQUIRED_FRONTMATTER_FIELDS if _is_missing(payload.get(field))]
    resolved_body = str(body if body is not None else payload.get("body") or "").strip()
    if not resolved_body:
        missing.append("body")
    if missing:
        raise WeeklyLetterValidationError(f"missing_required_fields:{','.join(missing)}")

    assert_no_external_action(
        external_action_allowed=payload.get("external_action_allowed", False),
        send_externally=payload.get("send_externally", False),
        external_send=payload.get("external_send", False),
        network_allowed=payload.get("network_allowed", False),
        irreversible_action_allowed=payload.get("irreversible_action_allowed", False),
    )

    week_date = str(payload["week_date"]).strip()
    expected_id = derive_letter_id(week_date)
    letter_id = str(payload["letter_id"]).strip()
    if letter_id != expected_id:
        raise WeeklyLetterValidationError(f"letter_id_not_deterministic:{letter_id}!={expected_id}")

    status = _clean_token(payload["status"])
    if status not in ALLOWED_WEEKLY_STATES:
        raise WeeklyLetterValidationError(f"invalid_status:{status}")

    scripture_refs = _validate_string_list(payload["scripture_refs"], "scripture_refs")
    audience_notes = _validate_string_list(payload["audience_notes"], "audience_notes")
    reflection_questions = _validate_string_list(payload["reflection_questions"], "reflection_questions")
    song = _validate_song(payload["song"])
    closing_prayer = str(payload["closing_prayer"]).strip()
    if not closing_prayer:
        raise WeeklyLetterValidationError("missing_required_fields:closing_prayer")

    return WeeklyLetter(
        letter_id=letter_id,
        title=str(payload["title"]).strip(),
        week_date=week_date,
        scripture_refs=scripture_refs,
        song=song,
        audience_notes=audience_notes,
        status=status,
        body=resolved_body,
        reflection_questions=reflection_questions,
        closing_prayer=closing_prayer,
        source_path=source_path,
        external_action_allowed=False,
        send_externally=False,
    )


def _validate_string_list(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise WeeklyLetterValidationError(f"malformed_{field_name}")
    cleaned = [str(item).strip() for item in value if str(item).strip()]
    if len(cleaned) != len(value):
        raise WeeklyLetterValidationError(f"malformed_{field_name}")
    return cleaned


def _validate_song(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise WeeklyLetterValidationError("missing_song_reference")
    cleaned = {str(key): str(val).strip() for key, val in value.items() if str(val).strip()}
    if not cleaned.get("title"):
        raise WeeklyLetterValidationError("missing_song_reference")
    if not any(cleaned.get(key) for key in ("reference", "link", "url", "notes")):
        raise WeeklyLetterValidationError("missing_song_reference")
    return cleaned


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict)):
        return not value
    return False


def _is_truthy(value: Any) -> bool:
    if value is True:
        return True
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "allow", "allowed", "send"}
    return False


def _clean_token(value: Any) -> str:
    return str(value or "").strip().lower()
