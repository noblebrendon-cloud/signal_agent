"""
Falsification Stress Harness — deterministic adversarial load generator.

Generates synthetic raw capture files to stress-test:
- Clustering stability (bridge documents)
- Keyword stuffing resilience
- Instability detection (spikes)
- Decay policy (timestamps)

Usage:
  brn capture.stress --docs 200 --themes 5 --bridge --keyword-stuff
"""
from __future__ import annotations

import json
import os
import random
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional


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


# Deterministic themes (tokens + domains)
THEMES = [
    {
        "name": "crypto_scam",
        "tokens": ["bitcoin", "eth", "profit", "guaranteed", "wallet", "seed", "phrase", "urgent", "hack", "transfer"],
        "domains": ["crypto-secure.com", "wallet-drainer.net", "fast-money.io"]
    },
    {
        "name": "election_misinfo",
        "tokens": ["ballot", "fraud", "stolen", "machines", "count", "illegal", "poll", "vote", "rigged", "tally"],
        "domains": ["truth-news.org", "real-patriot.net", "stop-steal.com"]
    },
    {
        "name": "medical_pseudosc",
        "tokens": ["cure", "miracle", "cancer", "secret", "doctors", "hide", "natural", "remedy", "bigpharma", "vitamin"],
        "domains": ["natural-healer.com", "med-truth.io", "wellness-secrets.org"]
    },
    {
        "name": "tech_hype",
        "tokens": ["ai", "agi", "singularity", "robot", "future", "learn", "neural", "net", "gpu", "compute"],
        "domains": ["tech-daily.com", "ai-insider.io", "silicon-valley.net"]
    },
    {
        "name": "finance_news",
        "tokens": ["stock", "market", "trade", "index", "rate", "fed", "inflation", "bond", "yield", "crash"],
        "domains": ["finance-times.com", "market-watch.net", "wallstreet.io"]
    }
]


def generate_doc(
    timestamp: datetime,
    theme: Dict[str, Any],
    rng: random.Random,
    mix_theme: Optional[Dict[str, Any]] = None,
    keyword_stuff: Optional[str] = None,
) -> str:
    """Generate a synthetic document body."""
    tokens = theme["tokens"][:]
    domains = theme["domains"][:]
    
    if mix_theme:
        tokens.extend(mix_theme["tokens"])
        domains.extend(mix_theme["domains"])
        
    doc_tokens = []
    # Generate 50-100 words
    length = rng.randint(50, 100)
    
    for _ in range(length):
        if keyword_stuff and rng.random() < 0.3:
            doc_tokens.append(keyword_stuff)
        else:
            doc_tokens.append(rng.choice(tokens))
            
    # Inject 1-3 URLs
    doc_urls = []
    for _ in range(rng.randint(1, 3)):
        dom = rng.choice(domains)
        doc_urls.append(f"https://{dom}/article/{rng.randint(1000, 9999)}")
        
    body = " ".join(doc_tokens) + "\n\n" + "\n".join(doc_urls)
    return body


def run_stress(
    doc_count: int = 100,
    theme_count: int = 3,
    bridge: bool = False,
    keyword_stuff: bool = False,
    time_skew: bool = False,
    capture_dir: Optional[Path] = None,
    seed: int = 42,
    min_cluster_size: int = 2,
) -> Dict[str, Any]:
    """Generate synthetic load and run capture pipeline."""
    rng = random.Random(seed)
    base = capture_dir or _get_capture_dir()
    raw_dir = base / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    
    # Select active themes
    active_themes = THEMES[:min(theme_count, len(THEMES))]
    
    now = datetime.now(timezone.utc)
    created_files = []
    
    ts_map = {} # filename -> datetime

    # 1. Generate normal load
    for i in range(doc_count):
        theme = rng.choice(active_themes)
        
        # Time skew: spread over last 3 days
        if time_skew:
            offset_hours = rng.randint(0, 72)
            doc_ts = now - timedelta(hours=offset_hours)
        else:
            doc_ts = now
            
        body = generate_doc(doc_ts, theme, rng)
        
        ts_str = doc_ts.strftime("%Y-%m-%dT%H-%M-%S") + f"_{i:03d}Z"
        filename = f"raw_{ts_str}.md"
        
        frontmatter = (
            "---\n"
            f"timestamp_utc: {doc_ts.strftime('%Y-%m-%dT%H:%M:%SZ')}\n"
            "input_type: stress_test\n"
            f"source: synthetic_{theme['name']}\n"
            "---\n"
        )
        
        with open(raw_dir / filename, "w", encoding="utf-8", newline="\n") as f:
            f.write(frontmatter + body)
        created_files.append(filename)
        ts_map[filename] = doc_ts

    # 2. Generate bridge document (if requested)
    # Bridge between theme 0 and theme 1
    bridge_file = None
    if bridge and len(active_themes) >= 2:
        doc_ts = now
        # Mix theme 0 and 1 equally
        body = generate_doc(doc_ts, active_themes[0], rng, mix_theme=active_themes[1])
        ts_str = doc_ts.strftime("%Y-%m-%dT%H-%M-%S") + "_bridgeZ"
        filename = f"raw_{ts_str}.md"
        frontmatter = (
            "---\n"
            f"timestamp_utc: {doc_ts.strftime('%Y-%m-%dT%H:%M:%SZ')}\n"
            "input_type: stress_test\n"
            "source: synthetic_bridge\n"
            "---\n"
        )
        with open(raw_dir / filename, "w", encoding="utf-8", newline="\n") as f:
            f.write(frontmatter + body)
        created_files.append(filename)
        bridge_file = filename

    # 3. Generate keyword stuffed document (if requested)
    stuff_file = None
    if keyword_stuff:
        doc_ts = now
        # Stuff "buy" token
        body = generate_doc(doc_ts, active_themes[0], rng, keyword_stuff="buy")
        ts_str = doc_ts.strftime("%Y-%m-%dT%H-%M-%S") + "_stuffZ"
        filename = f"raw_{ts_str}.md"
        frontmatter = (
            "---\n"
            f"timestamp_utc: {doc_ts.strftime('%Y-%m-%dT%H:%M:%SZ')}\n"
            "input_type: stress_test\n"
            "source: synthetic_stuffed\n"
            "---\n"
        )
        with open(raw_dir / filename, "w", encoding="utf-8", newline="\n") as f:
            f.write(frontmatter + body)
        created_files.append(filename)
        stuff_file = filename

    # 4. Run Promote
    from app.hq.capture.promote import promote_run
    promo_result = promote_run(
        capture_dir=base,
        window_hours=24.0, # tighter window
        min_cluster_size=min_cluster_size,
        max_files=1000,
        strategy="hybrid",
        force=True
    )
    
    # 5. Run Instability
    from app.hq.capture.instability import scan_instability
    inst_result = scan_instability(
        capture_dir=base,
        window_days=7,
        min_today=5, # lower threshold for test
        spike_ratio=2.0 
    )

    return {
        "generated_count": len(created_files),
        "bridge_file": bridge_file,
        "stuffed_file": stuff_file,
        "promote_stats": {
            "clusters": promo_result.get("clusters"),
            "bundles": len(promo_result.get("bundles", [])),
        },
        "instability_stats": {
            "flags": len(inst_result.get("flags", [])),
            "utc_day": inst_result.get("utc_day"),
        }
    }


def main(argv: Optional[list] = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(prog="brn capture.stress")
    parser.add_argument("--docs", type=int, default=100)
    parser.add_argument("--themes", type=int, default=3)
    parser.add_argument("--bridge", action="store_true")
    parser.add_argument("--keyword-stuff", action="store_true")
    parser.add_argument("--time-skew", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    
    args = parser.parse_args(argv)
    
    result = run_stress(
        doc_count=args.docs,
        theme_count=args.themes,
        bridge=args.bridge,
        keyword_stuff=args.keyword_stuff,
        time_skew=args.time_skew,
        seed=args.seed
    )
    print(json.dumps(result, indent=2))
    return 0

if __name__ == "__main__":
    sys.exit(main())
