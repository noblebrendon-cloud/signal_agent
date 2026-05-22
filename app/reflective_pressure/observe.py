from __future__ import annotations

from pathlib import Path

from app.reflective_pressure.models import build_observation_record
from app.reflective_pressure.store import append_observation


def record_observation(
    *,
    draft_id: str,
    input_id: str,
    observation_window: str = "manual",
    views: int | float = 0,
    reactions: int | float = 0,
    comments: int | float = 0,
    shares: int | float = 0,
    saves: int | float = 0,
    profile_clicks: int | float = 0,
    recognition_events: int | float = 0,
    constructive_reply_ratio: int | float = 0,
    self_insertion_density: int | float = 0,
    delayed_recirculation: int | float = 0,
    contradiction_heat: int | float = 0,
    notes: str = "",
    created_at: str | None = None,
    repo_root: Path | None = None,
) -> dict:
    record = build_observation_record(
        draft_id=draft_id,
        input_id=input_id,
        observation_window=observation_window,
        views=views,
        reactions=reactions,
        comments=comments,
        shares=shares,
        saves=saves,
        profile_clicks=profile_clicks,
        recognition_events=recognition_events,
        constructive_reply_ratio=constructive_reply_ratio,
        self_insertion_density=self_insertion_density,
        delayed_recirculation=delayed_recirculation,
        contradiction_heat=contradiction_heat,
        notes=notes,
        created_at=created_at,
    )
    return append_observation(record, repo_root=repo_root)
