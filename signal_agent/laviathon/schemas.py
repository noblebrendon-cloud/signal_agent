from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
RationaleText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
BoundedText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]


class TransitionProposal(BaseModel):
    """
    Proposal-only Laviathon transition recommendation.

    This schema has no authority to commit state. Final disposition must come
    from deterministic governance gates.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    entity_id: NonEmptyString
    observed_state: NonEmptyString
    recommended_route: Literal["admit", "blocked_duplicate", "manual_review"]
    evidence_ids: list[NonEmptyString] = Field(min_length=1)
    rationale: RationaleText
    uncertainty_notes: BoundedText = ""
    requires_human_review: bool
