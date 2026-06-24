"""Canonical Laviathon namespace backed by the legacy signal_agent.leviathan package."""
from __future__ import annotations

from importlib import import_module
from pathlib import Path

_LEGACY = import_module("signal_agent.leviathan")
_HERE = Path(__file__).resolve().parent

__doc__ = getattr(_LEGACY, "__doc__", __doc__)
__all__ = getattr(_LEGACY, "__all__", [])
__path__ = [str(_HERE), *list(getattr(_LEGACY, "__path__", []))]
