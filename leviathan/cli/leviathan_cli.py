"""Compatibility shim for python -m leviathan.cli.leviathan_cli."""
from __future__ import annotations

from signal_agent.leviathan.cli.leviathan_cli import main


if __name__ == "__main__":
    raise SystemExit(main())

