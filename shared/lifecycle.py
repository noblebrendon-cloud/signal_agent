"""
shared/lifecycle.py — DEPRECATED lifecycle transition helpers.

STATUS: DEPRECATED — DO NOT USE FOR PRODUCTION LIFECYCLE TRANSITIONS.

All lifecycle transitions MUST flow through the canonical governance gate:
    from app.hq.governance import validate_transition, emit_transition_event

This module formerly contained a 3-entry shadow transition table that
bypassed policy evaluation, lane checking, and canonical event emission.
It has been replaced with hard failures that direct callers to the
canonical authority.

Retained exports:
    InvalidTransitionError — kept for backward compatibility in catch blocks.

Deprecated exports (hard-fail on call):
    can_transition()     — raises RuntimeError directing to canonical gate.
    require_transition() — raises RuntimeError directing to canonical gate.
"""


class InvalidTransitionError(RuntimeError):
    """Raised when an invalid lifecycle transition is attempted.

    This exception class is retained for backward compatibility.
    It may be caught by existing error-handling code.
    """
    pass


def can_transition(from_state: str, to_state: str) -> bool:
    """DEPRECATED — raises immediately.

    Use instead:
        from app.hq.governance import validate_transition
        result = validate_transition(current_state, next_state, lane_id)
        allowed = result["allowed"]
    """
    raise RuntimeError(
        "shared.lifecycle.can_transition() is DEPRECATED and no longer a valid "
        "lifecycle authority. All lifecycle transitions must use the canonical "
        "governance gate: app.hq.governance.validate_transition(). "
        f"Attempted: {from_state} -> {to_state}"
    )


def require_transition(from_state: str, to_state: str) -> None:
    """DEPRECATED — raises immediately.

    Use instead:
        from app.hq.governance import validate_transition
        result = validate_transition(current_state, next_state, lane_id)
        if not result["allowed"]:
            raise InvalidTransitionError(result["reason"])
    """
    raise RuntimeError(
        "shared.lifecycle.require_transition() is DEPRECATED and no longer a "
        "valid lifecycle authority. All lifecycle transitions must use the "
        "canonical governance gate: app.hq.governance.validate_transition(). "
        f"Attempted: {from_state} -> {to_state}"
    )
