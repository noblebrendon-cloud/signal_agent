"""Deterministic tokenizer for Interaction Signals."""
from __future__ import annotations
import re

_WORD_RE = re.compile(r"[a-zA-Z']+|\d+")
_SENT_END_RE = re.compile(r"[.!?]+")


def tokenize(text: str) -> list[str]:
    """Return lowercase word/number tokens."""
    return [t.lower() for t in _WORD_RE.findall(text)]


def sentence_split(text: str) -> list[str]:
    """Heuristic: split on . ! ? boundaries; return non-empty parts."""
    parts = _SENT_END_RE.split(text)
    return [p.strip() for p in parts if p.strip()]


def count_questions(text: str) -> int:
    return text.count("?")


def count_sentences(text: str) -> int:
    return max(1, len(sentence_split(text)))


def has_code_fence(text: str) -> bool:
    return "```" in text or "~~~" in text


def has_url(text: str) -> bool:
    return bool(re.search(r"https?://", text))


def has_digits(text: str) -> bool:
    return bool(re.search(r"\b\d+\.?\d*\b", text))
