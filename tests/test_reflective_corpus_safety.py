from __future__ import annotations

import ast
from pathlib import Path


CORPUS_ROOT = Path(__file__).resolve().parents[1] / "app" / "reflective_corpus"
FORBIDDEN_MODULES = (
    "requests",
    "urllib",
    "http.client",
    "socket",
    "smtplib",
    "subprocess",
    "webbrowser",
)
FORBIDDEN_SOURCE_TOKENS = FORBIDDEN_MODULES


def test_reflective_corpus_has_no_forbidden_external_interfaces() -> None:
    violations: list[str] = []

    for path in sorted(CORPUS_ROOT.rglob("*.py")):
        relative_path = path.relative_to(CORPUS_ROOT.parents[1])
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if _is_forbidden_module(alias.name):
                        violations.append(f"{relative_path}: forbidden import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if _is_forbidden_module(module):
                    violations.append(f"{relative_path}: forbidden import from {module}")
                if module == "http" and any(alias.name == "client" for alias in node.names):
                    violations.append(f"{relative_path}: forbidden import from http.client")

        for token in FORBIDDEN_SOURCE_TOKENS:
            if token in source:
                violations.append(f"{relative_path}: forbidden token {token}")

    assert violations == []


def _is_forbidden_module(module_name: str) -> bool:
    return any(module_name == forbidden or module_name.startswith(f"{forbidden}.") for forbidden in FORBIDDEN_MODULES)
