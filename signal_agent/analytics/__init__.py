"""Read-only internal signal intelligence for governance telemetry."""

__all__ = [
    "SELF_OBSERVATION_REPORT_VERSION",
    "build_self_observation_report",
    "read_jsonl_with_metadata",
    "render_self_observation_markdown",
    "write_self_observation_report",
]


def __getattr__(name: str):
    if name in {
        "SELF_OBSERVATION_REPORT_VERSION",
        "build_self_observation_report",
        "read_jsonl_with_metadata",
        "write_self_observation_report",
    }:
        from . import self_observation

        return getattr(self_observation, name)
    if name == "render_self_observation_markdown":
        from .report_builder import render_self_observation_markdown

        return render_self_observation_markdown
    raise AttributeError(name)
