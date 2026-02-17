"""
Instability Detector — flag volatile topic spikes in captured material.

Maintains rolling counters in instability_state.json.
Detects when today's capture volume for a topic exceeds baseline.
Logs flags to instability_log.jsonl.

Hardened Features:
- Token cap alignment (max 5 references per doc)
- UTC Day explicit key
- Zero-day inclusion in baseline
- Severity classification
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional


_TOKEN_RE = re.compile(r"[a-z0-9]+")
_URL_RE = re.compile(r"https?://[^\s\)>\]\"']+", re.IGNORECASE)
_MAX_TOKEN_COUNT = 5  # Alignment with promote.py

_STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "it", "this", "that", "was", "be",
    "are", "as", "not", "no", "so", "if", "do", "has", "had", "have",
    "will", "would", "could", "should", "may", "can", "just", "also",
    "than", "then", "very", "too", "about", "up", "out", "into", "over",
    "after", "before", "between", "under", "all", "each", "every", "both",
    "such", "through", "its", "my", "your", "our", "their", "he", "she",
    "we", "they", "me", "him", "her", "us", "them", "i", "you",
    "been", "being", "did", "does", "doing", "what", "which", "who",
    "whom", "when", "where", "why", "how", "any", "some", "only",
    "other", "more", "most", "own", "same", "few", "many", "much",
})


def _get_root() -> Path:
    override = os.environ.get("SIGNAL_AGENT_ROOT")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[3]


def _get_capture_dir() -> Path:
    override = os.environ.get("CAPTURE_DIR")
    if override:
        return Path(override)
    return _get_root() / "data" / "capture"


def _extract_tokens(text: str) -> List[str]:
    words = _TOKEN_RE.findall(text.lower())
    # Cap token references to prevent keyword stuffing influence
    counts = Counter(words)
    capped_tokens = []
    for w, c in counts.items():
        if w not in _STOPWORDS and len(w) > 1:
            # We add it min(c, 5) times to the list to represent capped frequency
            for _ in range(min(c, _MAX_TOKEN_COUNT)):
                capped_tokens.append(w)
    return capped_tokens


def _extract_domains(text: str) -> List[str]:
    urls = _URL_RE.findall(text)
    domains = []
    for url in urls:
        try:
            rest = url.split("://", 1)[1] if "://" in url else url
            domain = rest.split("/")[0].split("?")[0].split("#")[0]
            domains.append(domain.lower())
        except (IndexError, ValueError):
            pass
    return sorted(set(domains))


def compute_topic_id(top_tokens: List[str], domains: List[str]) -> str:
    """Deterministic topic ID from top tokens + domains."""
    canon = "|".join(sorted(top_tokens[:12])) + "||" + "|".join(sorted(domains[:6]))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()[:12]


def _parse_frontmatter_ts(text: str) -> Optional[str]:
    """Extract timestamp_utc from frontmatter."""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].split("\n"):
                if line.strip().startswith("timestamp_utc:"):
                    return line.split(":", 1)[1].strip()
    return None


def _load_state(state_path: Path) -> Dict[str, Any]:
    if state_path.exists():
        try:
            return json.loads(state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"updated_utc": None, "topics": {}}


def _save_state(state_path: Path, state: Dict[str, Any]) -> None:
    with open(state_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(state, f, indent=2, sort_keys=True)
        f.write("\n")


def _append_instability_log(
    capture_dir: Path,
    entry: Dict[str, Any],
) -> None:
    log_path = capture_dir / "instability_log.jsonl"
    line = json.dumps(entry, sort_keys=True) + "\n"
    with open(log_path, "a", encoding="utf-8", newline="\n") as f:
        f.write(line)


def scan_instability(
    window_days: int = 7,
    min_today: int = 6,
    spike_ratio: float = 3.0,
    capture_dir: Optional[Path] = None,
    now_utc: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Scan raw captures for topic spikes.
    Returns dict with instability flags.
    """
    base = capture_dir or _get_capture_dir()
    raw_dir = base / "raw"
    state_path = base / "instability_state.json"

    now = now_utc or datetime.now(timezone.utc)
    today_str = now.strftime("%Y-%m-%d")

    # Load all raw files
    all_files: List[Path] = []
    for d in [raw_dir, base / "archive"]:
        if d.exists():
            all_files.extend(d.glob("raw_*.md"))
    all_files.sort(key=lambda p: p.name)

    # Build per-day topic counts
    topic_daily: Dict[str, Dict[str, int]] = {}
    topic_meta: Dict[str, Dict[str, Any]] = {}

    for rf in all_files:
        try:
            text = rf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        ts_str = _parse_frontmatter_ts(text)
        if ts_str:
            try:
                dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                file_date = dt.strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                file_date = today_str
        else:
            file_date = today_str

        body = text
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                body = parts[2]

        tokens = _extract_tokens(body)
        domains = _extract_domains(body)

        counts = Counter(tokens)
        top_tokens = [t for t, _ in counts.most_common(12)]

        tid = compute_topic_id(top_tokens, domains)

        if tid not in topic_daily:
            topic_daily[tid] = {}
            topic_meta[tid] = {"top_tokens": top_tokens, "domains": domains}

        topic_daily[tid][file_date] = topic_daily[tid].get(file_date, 0) + 1

    flags: List[Dict[str, Any]] = []

    # Generate last N day strings for baseline
    day_strings = []
    for i in range(window_days):
        d = now - timedelta(days=i)
        day_strings.append(d.strftime("%Y-%m-%d"))

    for tid, daily in sorted(topic_daily.items()):
        today_count = daily.get(today_str, 0)

        # Baseline: mean of last N days excluding today (INCLUDE ZEROS)
        # Previously we might have used .get() which returns 0, but logic was:
        # sum(baseline_days) / len(baseline_days).
        # We ensure we iterate over ALL day_strings[1:] even if not in daily.
        baseline_days = [daily.get(ds, 0) for ds in day_strings[1:]]
        baseline = (sum(baseline_days) / max(len(baseline_days), 1)) + 1e-9

        ratio = today_count / baseline

        is_spike = (
            (today_count >= min_today and ratio >= spike_ratio) or
            (today_count >= min_today * 2.5)  # absolute spike check
        )

        if is_spike:
            # Severity classification
            severity = "minor"
            if today_count >= 20:
                severity = "extreme"
            elif ratio >= 5.0:
                severity = "major"

            meta = topic_meta.get(tid, {"top_tokens": [], "domains": []})
            flags.append({
                "topic_id": tid,
                "utc_day": today_str,
                "today_count": today_count,
                "baseline": round(baseline, 4),
                "spike_ratio": round(ratio, 4),
                "severity": severity,
                "top_tokens": meta["top_tokens"],
                "domains": meta["domains"],
            })

    # Update state
    state = _load_state(state_path)
    state["updated_utc"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    state["utc_day"] = today_str
    
    for tid, daily in topic_daily.items():
        # Keep last 7 days history relative to day_strings
        last_7 = [daily.get(ds, 0) for ds in reversed(day_strings)]
        
        # Calculate new baseline for state storage
        baseline_vals = last_7[:-1] if len(last_7) > 1 else last_7
        
        state["topics"][tid] = {
            "baseline_per_day": round(sum(baseline_vals) / max(len(baseline_vals), 1), 4),
            "last_7_days": last_7[-7:] if len(last_7) >= 7 else last_7,
            "last_seen_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    _save_state(state_path, state)

    # Log flags
    if flags:
        log_entry = {
            "timestamp_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "utc_day": today_str,
            "flags": flags,
            "window_days": window_days,
            "min_today": min_today,
            "spike_ratio_threshold": spike_ratio,
        }
        _append_instability_log(base, log_entry)

    return {
        "status": "ok",
        "flags": flags,
        "total_topics": len(topic_daily),
        "scanned_files": len(all_files),
        "utc_day": today_str,
    }


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def main(argv: Optional[list] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="brn capture.instability",
        description="Detect volatile topic spikes in captured material.",
    )
    parser.add_argument("--window-days", type=int, default=7, help="Rolling window (days)")
    parser.add_argument("--min-today", type=int, default=6, help="Min docs today to flag")
    parser.add_argument("--ratio", type=float, default=3.0, help="Spike ratio threshold")

    args = parser.parse_args(argv)
    result = scan_instability(
        window_days=args.window_days,
        min_today=args.min_today,
        spike_ratio=args.ratio,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
