"""HQ capture package contract.

Runtime surface:
- `capture_add` / `capture_status`
- `promote_run`
- `route_bundle`
- `decay_run`
- `scan_instability`

Diagnostic-only surface:
- `stress.py`

Directory lifecycle:
- `raw/` accepts volatile capture fragments and feeds promotion, decay, and instability.
- `promoted/` stores promoted bundle artifacts awaiting downstream routing or review.
- `archive/` stores raw files successfully consumed by promotion and is read-only lineage history.
- `expired_stage1/` stores first-stage decay retention outputs from `raw/`.
- `expired_stage2/` stores terminal second-stage decay retention outputs from `expired_stage1/`.
- `constraints/spines/<lane>/incoming/` stores routed copies and is not capture-owned long-term storage.
"""

DIRECTORY_LIFECYCLE_CONTRACT = {
    "raw": "Volatile capture intake surface for raw fragments; feeds promotion, decay, and instability.",
    "promoted": "Bundle storage owned by promotion; read by router and downstream review flows.",
    "archive": "Terminal lineage sink for raw files successfully consumed by promotion.",
    "expired_stage1": "First-stage decay retention surface; receives old raw files and feeds second-stage decay only.",
    "expired_stage2": "Terminal decay retention surface; receives files from expired_stage1 and does not feed promotion.",
    "spine_incoming": "Routed-copy destination under constraints/spines/<lane>/incoming; not capture-owned long-term storage.",
}

BOUNDARY_CONTRACT = {
    "intake_pipeline": (
        "intake_pipeline owns governed batch ingestion and supported-input policy; "
        "hq_capture owns volatile fragment capture and downstream capture lifecycle."
    ),
    "hq_curation": (
        "hq_capture owns bundle assembly and promotion; hq_curation owns deterministic "
        "staging, dedup, registry append, and compiled-to-staged lifecycle registration."
    ),
}

PROMOTED_RUNTIME_SURFACE = (
    "capture_add",
    "capture_status",
    "promote_run",
    "route_bundle",
    "decay_run",
    "scan_instability",
)

DIAGNOSTIC_ONLY_MODULES = ("stress",)

__all__ = [
    "DIRECTORY_LIFECYCLE_CONTRACT",
    "BOUNDARY_CONTRACT",
    "PROMOTED_RUNTIME_SURFACE",
    "DIAGNOSTIC_ONLY_MODULES",
]
