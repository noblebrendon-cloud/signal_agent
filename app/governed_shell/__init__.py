"""Governed shell package.

Phase 1 exposes documentation-facing schema contracts only.
Execution, policy evaluation, simulation, and runner integration are
intentionally not implemented in this phase.
"""

from pathlib import Path

SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"

__all__ = ["SCHEMA_DIR"]
