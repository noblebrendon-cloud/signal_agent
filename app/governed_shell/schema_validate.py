from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

from .errors import ProposalSchemaError


SCHEMA_PATH = Path(__file__).resolve().parent / "schemas" / "command_proposal.v1.json"


@dataclass(frozen=True)
class ValidationResult:
    clean: bool
    errors: list[str]
    schema_id: str | None = None
    schema_version: str | None = None


def _format_error_path(parts: tuple[object, ...]) -> str:
    if not parts:
        return "$"

    segments: list[str] = ["$"]
    for part in parts:
        if isinstance(part, int):
            segments.append(f"[{part}]")
        else:
            segments.append(f".{part}")
    return "".join(segments)


def _format_validation_error(error: object) -> str:
    path = _format_error_path(tuple(error.absolute_path))
    return f"{path}: {error.message}"


@lru_cache(maxsize=1)
def _load_command_schema() -> dict:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return schema


@lru_cache(maxsize=1)
def _command_proposal_validator() -> Draft202012Validator:
    return Draft202012Validator(_load_command_schema())


def validate_command_proposal(proposal: dict) -> ValidationResult:
    """Validate a proposal dict against the command proposal schema."""

    schema = _load_command_schema()
    schema_id = schema.get("$id")

    if type(proposal) is not dict:
        return ValidationResult(
            clean=False,
            errors=["$: Proposal must be a plain dict."],
            schema_id=schema_id,
            schema_version=None,
        )

    validator = _command_proposal_validator()
    errors = sorted(validator.iter_errors(proposal), key=lambda err: list(err.absolute_path))
    rendered_errors = [_format_validation_error(error) for error in errors]

    return ValidationResult(
        clean=not rendered_errors,
        errors=rendered_errors,
        schema_id=schema_id,
        schema_version=proposal.get("schema_version"),
    )


def require_valid_command_proposal(proposal: dict) -> dict:
    """Return the proposal if valid, otherwise raise ProposalSchemaError."""

    result = validate_command_proposal(proposal)
    if result.clean:
        return proposal

    details = "; ".join(result.errors) if result.errors else "unknown schema failure"
    raise ProposalSchemaError(f"Command proposal schema validation failed: {details}")
