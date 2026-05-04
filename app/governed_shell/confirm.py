from __future__ import annotations

from dataclasses import dataclass

from .errors import ConfirmationError


@dataclass(frozen=True)
class ConfirmationResult:
    clean: bool
    required: bool
    mode: str | None
    proposal_hash: str
    supplied_hash: str | None
    matched: bool
    reason_code: str
    issues: list[str]


def check_confirmation(
    proposal_hash: str,
    supplied_hash: str | None,
    required: bool,
    mode: str | None,
) -> ConfirmationResult:
    """Check exact proposal-hash confirmation without side effects."""

    resolved_mode = mode if mode is not None else ("exact_proposal_hash" if required else "none")
    if not required:
        return ConfirmationResult(
            clean=True,
            required=False,
            mode=resolved_mode,
            proposal_hash=proposal_hash,
            supplied_hash=supplied_hash,
            matched=supplied_hash == proposal_hash if supplied_hash is not None else False,
            reason_code="confirmation_not_required",
            issues=[],
        )

    if supplied_hash is None:
        return ConfirmationResult(
            clean=False,
            required=True,
            mode=resolved_mode,
            proposal_hash=proposal_hash,
            supplied_hash=None,
            matched=False,
            reason_code="confirmation_missing",
            issues=["exact proposal_hash confirmation is required but no hash was supplied."],
        )

    if supplied_hash != proposal_hash:
        return ConfirmationResult(
            clean=False,
            required=True,
            mode=resolved_mode,
            proposal_hash=proposal_hash,
            supplied_hash=supplied_hash,
            matched=False,
            reason_code="confirmation_mismatch",
            issues=["supplied_hash does not exactly match proposal_hash."],
        )

    return ConfirmationResult(
        clean=True,
        required=True,
        mode=resolved_mode,
        proposal_hash=proposal_hash,
        supplied_hash=supplied_hash,
        matched=True,
        reason_code="confirmation_matched",
        issues=[],
    )


def require_confirmation(
    proposal_hash: str,
    supplied_hash: str | None,
    required: bool,
    mode: str | None,
) -> ConfirmationResult:
    """Return a clean confirmation result or raise ConfirmationError."""

    result = check_confirmation(
        proposal_hash=proposal_hash,
        supplied_hash=supplied_hash,
        required=required,
        mode=mode,
    )
    if result.clean:
        return result

    detail = "; ".join(result.issues) if result.issues else result.reason_code
    raise ConfirmationError(
        f"Governed shell confirmation failed for {proposal_hash}: {result.reason_code}: {detail}"
    )
