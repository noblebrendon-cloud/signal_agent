from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from hashlib import sha256

from .errors import ProposalNormalizationError, ProposalPathError
from .proposal import dump_canonical_json
from .schema_validate import require_valid_command_proposal


_ABSOLUTE_PATH_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|[\\/])")
_FORBIDDEN_PATH_CHARS = {"|", ">", "<", ";", "&", "`"}


@dataclass(frozen=True)
class PathValidationResult:
    clean: bool
    errors: list[str]
    normalized_paths: dict[str, str]


@dataclass(frozen=True)
class NormalizedProposal:
    proposal: dict
    canonical_json: str
    proposal_hash: str
    path_validation: PathValidationResult


def _normalize_relative_path(path_value: str) -> str:
    if _ABSOLUTE_PATH_RE.match(path_value):
        raise ProposalPathError(f"Relative path must not be absolute: {path_value!r}")

    if any(character in path_value for character in _FORBIDDEN_PATH_CHARS):
        raise ProposalPathError(
            f"Relative path contains forbidden shell metacharacters: {path_value!r}"
        )

    standardized = path_value.replace("\\", "/")
    segments = standardized.split("/")
    normalized_segments: list[str] = []

    for segment in segments:
        if segment in ("", "."):
            continue
        if segment == "..":
            raise ProposalPathError(
                f"Relative path must not contain parent traversal: {path_value!r}"
            )
        normalized_segments.append(segment)

    if not normalized_segments:
        return "."

    return "/".join(normalized_segments)


def _argument_collections(operation: dict) -> list[tuple[str, list[dict]]]:
    collections: list[tuple[str, list[dict]]] = []

    parameters = operation.get("parameters")
    if isinstance(parameters, list):
        collections.append(("parameters", parameters))

    arguments = operation.get("arguments")
    if isinstance(arguments, list):
        collections.append(("arguments", arguments))

    return collections


def validate_path_refs(proposal: dict) -> PathValidationResult:
    """Validate symbolic path references without resolving host paths."""

    errors: list[str] = []
    normalized_paths: dict[str, str] = {}

    if type(proposal) is not dict:
        return PathValidationResult(
            clean=False,
            errors=["$: Proposal must be a plain dict."],
            normalized_paths={},
        )

    path_refs = proposal.get("path_refs")
    if not isinstance(path_refs, list):
        return PathValidationResult(
            clean=False,
            errors=["$.path_refs: path_refs must be a list."],
            normalized_paths={},
        )

    defined_path_ref_ids: set[str] = set()

    for index, path_ref in enumerate(path_refs):
        if type(path_ref) is not dict:
            errors.append(f"$.path_refs[{index}]: path reference must be an object.")
            continue

        path_ref_id = path_ref.get("path_ref_id")
        if isinstance(path_ref_id, str):
            if path_ref_id in defined_path_ref_ids:
                errors.append(f"$.path_refs[{index}].path_ref_id: duplicate path_ref_id {path_ref_id!r}.")
            else:
                defined_path_ref_ids.add(path_ref_id)

        relative_path = path_ref.get("relative_path")
        if not isinstance(relative_path, str):
            errors.append(f"$.path_refs[{index}].relative_path: relative_path must be a string.")
            continue

        try:
            normalized_path = _normalize_relative_path(relative_path)
        except ProposalPathError as exc:
            errors.append(f"$.path_refs[{index}].relative_path: {exc}")
            continue

        if isinstance(path_ref_id, str):
            normalized_paths[path_ref_id] = normalized_path

    operations = proposal.get("operations", [])
    if isinstance(operations, list):
        for op_index, operation in enumerate(operations):
            if type(operation) is not dict:
                errors.append(f"$.operations[{op_index}]: operation must be an object.")
                continue

            for collection_name, items in _argument_collections(operation):
                for item_index, item in enumerate(items):
                    if type(item) is not dict:
                        errors.append(
                            f"$.operations[{op_index}].{collection_name}[{item_index}]: value must be an object."
                        )
                        continue

                    if item.get("value_type") != "path_ref":
                        continue

                    path_ref_id = item.get("path_ref")
                    if not isinstance(path_ref_id, str):
                        errors.append(
                            f"$.operations[{op_index}].{collection_name}[{item_index}].path_ref: path_ref must be a string."
                        )
                        continue

                    if path_ref_id not in defined_path_ref_ids:
                        errors.append(
                            f"$.operations[{op_index}].{collection_name}[{item_index}].path_ref: "
                            f"unknown path_ref {path_ref_id!r}."
                        )
    else:
        errors.append("$.operations: operations must be a list.")

    return PathValidationResult(
        clean=not errors,
        errors=errors,
        normalized_paths=normalized_paths,
    )


def _canonicalized_copy(proposal: dict, path_validation: PathValidationResult) -> dict:
    normalized_proposal = copy.deepcopy(proposal)

    path_refs = normalized_proposal.get("path_refs", [])
    if isinstance(path_refs, list):
        for path_ref in path_refs:
            if type(path_ref) is not dict:
                continue

            path_ref_id = path_ref.get("path_ref_id")
            if isinstance(path_ref_id, str) and path_ref_id in path_validation.normalized_paths:
                path_ref["relative_path"] = path_validation.normalized_paths[path_ref_id]

    canonical_json = dump_canonical_json(normalized_proposal)
    try:
        canonicalized = json.loads(canonical_json)
    except json.JSONDecodeError as exc:
        raise ProposalNormalizationError(
            f"Canonical proposal JSON could not be reloaded: {exc}"
        ) from exc

    if type(canonicalized) is not dict:
        raise ProposalNormalizationError("Canonical proposal must remain a plain dict.")

    return canonicalized


def canonicalize_proposal(proposal: dict) -> dict:
    """Return a deterministic, normalized copy of a valid proposal."""

    require_valid_command_proposal(proposal)
    path_validation = validate_path_refs(proposal)
    if not path_validation.clean:
        raise ProposalPathError("; ".join(path_validation.errors))

    return _canonicalized_copy(proposal, path_validation)


def compute_proposal_hash(proposal: dict) -> str:
    """Compute a stable hash for a valid, normalized proposal."""

    canonical_proposal = canonicalize_proposal(proposal)
    canonical_json = dump_canonical_json(canonical_proposal)
    return f"sha256:{sha256(canonical_json.encode('utf-8')).hexdigest()}"


def normalize_and_hash_proposal(proposal: dict) -> NormalizedProposal:
    """Validate, canonicalize, and hash a proposal without side effects."""

    require_valid_command_proposal(proposal)
    path_validation = validate_path_refs(proposal)
    if not path_validation.clean:
        raise ProposalPathError("; ".join(path_validation.errors))

    canonical_proposal = _canonicalized_copy(proposal, path_validation)
    canonical_json = dump_canonical_json(canonical_proposal)
    proposal_hash = f"sha256:{sha256(canonical_json.encode('utf-8')).hexdigest()}"

    return NormalizedProposal(
        proposal=canonical_proposal,
        canonical_json=canonical_json,
        proposal_hash=proposal_hash,
        path_validation=path_validation,
    )
