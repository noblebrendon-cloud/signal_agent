from __future__ import annotations

from pathlib import Path
from typing import Any

from app.letters_of_light.weekly_models import (
    WeeklyLetter,
    assert_no_external_action,
    content_hash,
    require_transition,
)
from app.retention.jsonl_store import append_record


LETTERS_LEDGER = "letters_of_light_letters.jsonl"
TRANSITIONS_LEDGER = "letters_of_light_transitions.jsonl"


def register_weekly_letter(
    letter: WeeklyLetter,
    *,
    actor_id: str = "local-operator",
    repo_root: str | Path | None = None,
    external_action_allowed: bool = False,
) -> dict[str, Any]:
    assert_no_external_action(external_action_allowed=external_action_allowed)
    letter_record = append_record(
        LETTERS_LEDGER,
        letter.to_record(),
        repo_root=Path(repo_root) if repo_root else None,
    )
    transition_record = append_weekly_transition(
        letter_id=letter.letter_id,
        from_state=None,
        to_state=letter.status,
        actor_id=actor_id,
        repo_root=repo_root,
        reason_code="weekly_letter_registered",
    )
    return {
        "clean": True,
        "letter_record": letter_record,
        "transition_record": transition_record,
    }


def append_weekly_transition(
    *,
    letter_id: str,
    from_state: str | None,
    to_state: str,
    actor_id: str,
    repo_root: str | Path | None = None,
    reason_code: str = "operator_transition",
    external_action_allowed: bool = False,
    send_externally: bool = False,
) -> dict[str, Any]:
    assert_no_external_action(
        external_action_allowed=external_action_allowed,
        send_externally=send_externally,
    )
    require_transition(from_state, to_state)
    record = {
        "record_type": "letters_of_light_weekly_transition",
        "schema_version": "1.0",
        "transition_id": _transition_id(
            letter_id=letter_id,
            from_state=from_state,
            to_state=to_state,
            actor_id=actor_id,
            reason_code=reason_code,
        ),
        "letter_id": letter_id,
        "from_state": from_state,
        "to_state": to_state,
        "actor_id": str(actor_id or "").strip(),
        "reason_code": reason_code,
        "external_action_allowed": False,
        "send_externally": False,
    }
    if not record["actor_id"]:
        raise ValueError("missing_actor_id")
    return append_record(
        TRANSITIONS_LEDGER,
        record,
        repo_root=Path(repo_root) if repo_root else None,
    )


def _transition_id(
    *,
    letter_id: str,
    from_state: str | None,
    to_state: str,
    actor_id: str,
    reason_code: str,
) -> str:
    material = {
        "letter_id": letter_id,
        "from_state": from_state,
        "to_state": to_state,
        "actor_id": actor_id,
        "reason_code": reason_code,
    }
    return f"loltrn_{content_hash(material).split(':', 1)[1][:16]}"
