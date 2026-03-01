"""
OIL Memory -- Deterministic Action Extraction (v0.6)

v0.6 improvements:
  - Negation guard: if "don't" / "do not" / "avoid" appears within 3 tokens
    BEFORE a keyword, that keyword is skipped.
  - Compound support: first two non-negated keyword matches are returned as
    primary_action_category and fallback_action_category.
  - action_category kept as backward-compat alias for primary_action_category.

extract_action(report, origin_service) -> dict with keys:
  action_category          (str) -- alias for primary; kept for compat
  primary_action_category  (str) -- first non-negated match
  fallback_action_category (str) -- second non-negated match, or ""
  action_target_service    (str)
  action_reason            (str)

Categories (first match wins per token):
  rollback           <- "rollback"
  restart            <- "restart"
  scale              <- "scale"
  failover           <- "failover"
  hotfix             <- "hotfix" | "patch"
  vendor_escalation  <- "vendor" | "provider"
  investigate        <- "investigate" | "collect"
  unknown            <- empty text (no matches at all)
"""
from __future__ import annotations

import re

_CATEGORY_RULES: list[tuple[str, str]] = [
    ("rollback",    "rollback"),
    ("restart",     "restart"),
    ("scale",       "scale"),
    ("failover",    "failover"),
    ("hotfix",      "hotfix"),
    ("patch",       "hotfix"),
    ("vendor",      "vendor_escalation"),
    ("provider",    "vendor_escalation"),
    ("investigate", "investigate"),
    ("collect",     "investigate"),
]

_NEGATION_SINGLES = frozenset(["don't", "dont", "avoid"])  # single-token negators


def _is_negated(tokens: list[str], keyword_idx: int) -> bool:
    """Return True if a negation marker appears within 3 tokens before keyword_idx.

    Sentence boundary (a token that was a sentence-final word, now bare after
    stripping, but we detect via the raw scan) stops the negation scope.
    Because we strip punctuation including '.' in _parse_categories, a sentence
    boundary is detected by checking if the token BEFORE was originally
    sentence-final — but since we strip those chars too, we rely on the
    tokeniser already separating sentences via whitespace.

    Actually: because '.' is now stripped, "rollback." → "rollback". The window
    for "investigate" (index 3) would be ["do", "not", "rollback"] — and
    "rollback" is itself a keyword token, not a negator. So negation only
    triggers for "not" directly in the window. But "do not rollback investigate"
    would still falsely negate "investigate" 3 tokens away.

    Solution: if the window contains a keyword (action word), break before it —
    the negation applies only up to the first keyword after the negator.
    """
    window = tokens[max(0, keyword_idx - 3): keyword_idx]
    for j, w in enumerate(window):
        if w in _NEGATION_SINGLES:
            # ensure no other keyword token sits between negator and current keyword
            # (that earlier keyword would have consumed the negation)
            return True
        # two-token "do not"
        if w == "not" and j > 0 and window[j - 1] == "do":
            # negation is valid only if current keyword is the FIRST keyword
            # after "do not" — i.e., no other ACTION keyword between "not" and here
            intervening = window[j + 1:]
            for iw in intervening:
                if any(kw in iw for kw, _ in _CATEGORY_RULES):
                    # a keyword sits between "do not" and the current token
                    # → negation consumed by that intervening keyword, not this one
                    return False
            return True
    return False


def _parse_categories(action_text: str) -> list[str]:
    """Return ordered list of non-negated category matches (deduped, order preserved)."""
    # Normalize: lowercase, strip punctuation INCLUDING periods so
    # "rollback." → "rollback" and sentence boundaries don't bleed negation scope.
    tokens = re.sub(r"[\"'.,;!?]", "", action_text.lower()).split()

    seen: set[str] = set()
    categories: list[str] = []

    for i, token in enumerate(tokens):
        for keyword, category in _CATEGORY_RULES:
            if keyword in token:          # substring match within token
                if not _is_negated(tokens, i) and category not in seen:
                    categories.append(category)
                    seen.add(category)
                break  # one category per token position

    return categories


def _extract_target(action_text: str, origin_service: str) -> str:
    """Extract target service from action text.

    Looks for the pattern "to '<service>'" (single quotes, as produced by
    recommended_human_action in generator.py). Falls back to origin_service.
    """
    m = re.search(r"to\s+'([^'\s:]+)", action_text)
    if m:
        return m.group(1)
    return origin_service


def _build_reason(report: dict) -> str:
    """Build a short, deterministic reason phrase from the top evidence item."""
    evidence = report.get("evidence", [])
    if not evidence:
        top_cause = report.get("top_ranked_cause", "")
        return f"top cause: {top_cause[:60]}" if top_cause else "no evidence available"

    top = evidence[0]
    service = top.get("service", "")
    metric = top.get("metric_name", "")
    delta = top.get("delta", 0.0)
    direction = "drop" if delta < 0 else "spike"
    if metric:
        return f"{service}/{metric} {direction} ({delta:+.1f})"
    return f"{service} {direction} ({delta:+.1f})"


def extract_action(report: dict, origin_service: str) -> dict:
    """Extract a deterministic structured action recommendation from a report.

    Args:
        report: output of generate_explanation().
        origin_service: the top hypothesis origin_service (plain service name).

    Returns dict with keys:
        action_category          -- backward-compat alias for primary
        primary_action_category  -- first non-negated keyword match
        fallback_action_category -- second non-negated match, or ""
        action_target_service    -- origin_service or extracted service name
        action_reason            -- deterministic phrase from evidence
    """
    action_text = report.get("recommended_human_action", "")
    matches = _parse_categories(action_text)

    if not matches and not action_text.strip():
        primary = "unknown"
    elif not matches:
        primary = "investigate"   # text present, no keyword hit → default
    else:
        primary = matches[0]

    fallback = matches[1] if len(matches) >= 2 else ""

    target = _extract_target(action_text, origin_service)
    reason = _build_reason(report)

    return {
        "action_category":          primary,   # backward compat
        "primary_action_category":  primary,
        "fallback_action_category": fallback,
        "action_target_service":    target,
        "action_reason":            reason,
    }
