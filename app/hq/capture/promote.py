"""
Promotion Layer — deterministic clustering + curate handoff.

Clusters raw capture notes, emits promoted bundles, hands off to curate.
Records lineage in promotion_log.jsonl.
Archives processed raw files.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.utils.io_contract import append_jsonl_atomic


CURATE_HANDOFF_MODE = "disabled"
CURATION_HANDOFF_NOTE = (
    "promote_run() stops at bundle creation, routing, and archive movement; "
    "hq_curation is a separate downstream stage and is not invoked by default."
)


# ===================================================================
# Built-in stopwords (minimal, no external deps)
# ===================================================================

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
    "https", "http", "www", "com", "net", "org", "io", "html", "htm",
    "article", "content", "page", "index",
})

_URL_RE = re.compile(r"https?://[^\s\)>\]\"']+", re.IGNORECASE)
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_TOP_K = 64
_MAX_TOKEN_COUNT = 5  # cap per-doc token frequency to resist keyword stuffing


# ===================================================================
# Helpers
# ===================================================================

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


def _canonical_state_paths(capture_dir: Path) -> tuple[Path, Path]:
    capture_root = capture_dir.resolve()
    if capture_root.name == "capture" and capture_root.parent.name == "data":
        repo_root = capture_root.parent.parent
    else:
        repo_root = capture_root.parent
    state_root = repo_root / "data" / "state"
    return (
        state_root / "artifact_registry.jsonl",
        state_root / "transition_gate_events.jsonl",
    )


def _parse_frontmatter(text: str) -> Tuple[Dict[str, str], str]:
    """Parse YAML frontmatter from markdown. Returns (meta, body)."""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            meta_raw = parts[1].strip()
            body = parts[2].strip()
            meta = {}
            for line in meta_raw.split("\n"):
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip()
            return meta, body
    return {}, text.strip()


def _extract_tokens(text: str) -> List[str]:
    """Extract lowercase tokens, strip punctuation, drop stopwords."""
    words = _TOKEN_RE.findall(text.lower())
    return [w for w in words if w not in _STOPWORDS and len(w) > 1]


def _extract_urls(text: str) -> List[str]:
    """Extract URLs from text."""
    return _URL_RE.findall(text)


def _extract_domains(urls: List[str]) -> List[str]:
    """Extract domains from URLs."""
    domains = []
    for url in urls:
        try:
            # Remove protocol
            rest = url.split("://", 1)[1] if "://" in url else url
            domain = rest.split("/")[0].split("?")[0].split("#")[0]
            domains.append(domain.lower())
        except (IndexError, ValueError):
            pass
    return sorted(set(domains))


def _build_tf(tokens: List[str]) -> Dict[str, float]:
    """Build term-frequency map capped to top K, with per-token cap."""
    counts = Counter(tokens)
    # Cap each token count to resist keyword stuffing
    capped = {word: min(count, _MAX_TOKEN_COUNT) for word, count in counts.items()}
    total = sum(capped.values()) if capped else 1
    # Take top K by capped count (deterministic: sort by -count then alpha)
    top = sorted(capped.items(), key=lambda x: (-x[1], x[0]))[:_TOP_K]
    return {word: count / total for word, count in top}


def _cosine_similarity(tf1: Dict[str, float], tf2: Dict[str, float]) -> float:
    """Cosine similarity between two TF maps."""
    keys = set(tf1.keys()) | set(tf2.keys())
    if not keys:
        return 0.0
    dot = sum(tf1.get(k, 0.0) * tf2.get(k, 0.0) for k in keys)
    mag1 = math.sqrt(sum(v * v for v in tf1.values()))
    mag2 = math.sqrt(sum(v * v for v in tf2.values()))
    if mag1 == 0 or mag2 == 0:
        return 0.0
    return dot / (mag1 * mag2)


def _jaccard(set1: set, set2: set) -> float:
    """Jaccard similarity between two sets."""
    if not set1 and not set2:
        return 0.0
    inter = len(set1 & set2)
    union = len(set1 | set2)
    return inter / union if union else 0.0


def _parse_timestamp(ts_str: str) -> Optional[datetime]:
    """Parse ISO timestamp from frontmatter."""
    if not ts_str or ts_str == "null":
        return None
    try:
        # Try standard ISO
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


# ===================================================================
# Document representation
# ===================================================================

class _Doc:
    """Internal representation of a raw capture file."""

    def __init__(self, path: Path, meta: Dict[str, str], body: str):
        self.path = path
        self.name = path.name
        self.meta = meta
        self.body = body
        self.tokens = _extract_tokens(body)
        self.urls = _extract_urls(body)
        self.domains = set(_extract_domains(self.urls))
        self.tf = _build_tf(self.tokens)
        self.timestamp = _parse_timestamp(meta.get("timestamp_utc", ""))

    def timestamp_hours(self) -> Optional[float]:
        """Return timestamp as hours since epoch."""
        if self.timestamp:
            return self.timestamp.timestamp() / 3600.0
        return None


# ===================================================================
# Clustering
# ===================================================================

class _Cluster:
    """Greedy cluster accumulator."""

    def __init__(self, doc: _Doc):
        self.docs: List[_Doc] = [doc]
        self._tf_sum: Dict[str, float] = dict(doc.tf)
        self._domains: set = set(doc.domains)
        self._ts_sum: float = doc.timestamp_hours() or 0.0
        self._ts_count: int = 1 if doc.timestamp_hours() is not None else 0

    def centroid_tf(self) -> Dict[str, float]:
        n = len(self.docs)
        return {k: v / n for k, v in self._tf_sum.items()}

    def centroid_domains(self) -> set:
        return self._domains

    def centroid_ts_hours(self) -> Optional[float]:
        if self._ts_count == 0:
            return None
        return self._ts_sum / self._ts_count

    def add(self, doc: _Doc) -> None:
        self.docs.append(doc)
        for k, v in doc.tf.items():
            self._tf_sum[k] = self._tf_sum.get(k, 0.0) + v
        self._domains |= doc.domains
        th = doc.timestamp_hours()
        if th is not None:
            self._ts_sum += th
            self._ts_count += 1


def _score(
    doc: _Doc,
    cluster: _Cluster,
    window_hours: float,
    strategy: str,
) -> float:
    """Compute similarity score between doc and cluster centroid."""
    cosine = _cosine_similarity(doc.tf, cluster.centroid_tf())

    if strategy == "keyword":
        return cosine

    jaccard_dom = _jaccard(doc.domains, cluster.centroid_domains())

    if strategy == "domain_time":
        # Skip cosine, use domain + time only
        time_decay = 0.0
        doc_ts = doc.timestamp_hours()
        cent_ts = cluster.centroid_ts_hours()
        if doc_ts is not None and cent_ts is not None and window_hours > 0:
            delta = abs(doc_ts - cent_ts)
            time_decay = max(0.0, 1.0 - (delta / window_hours))
        return 0.5 * jaccard_dom + 0.5 * time_decay

    # hybrid (default)
    time_decay = 0.0
    doc_ts = doc.timestamp_hours()
    cent_ts = cluster.centroid_ts_hours()
    if doc_ts is not None and cent_ts is not None and window_hours > 0:
        delta = abs(doc_ts - cent_ts)
        time_decay = max(0.0, 1.0 - (delta / window_hours))

    return 0.7 * cosine + 0.2 * jaccard_dom + 0.1 * time_decay


def _cluster_docs(
    docs: List[_Doc],
    threshold: float,
    window_hours: float,
    strategy: str,
) -> Tuple[List[_Cluster], int]:
    """Greedy deterministic clustering with bridge-doc defense. Docs must be sorted. Returns (clusters, bridge_forced_count)."""
    clusters: List[_Cluster] = []
    bridge_forced_count = 0
    
    for doc in docs:
        if not clusters:
            clusters.append(_Cluster(doc))
            continue

        best_cluster = None
        best_score = -1.0
        
        # Score against all existing clusters
        candidates = []
        for cluster in clusters:
            s = _score(doc, cluster, window_hours, strategy)
            if s >= threshold:
                candidates.append((s, cluster))
        
        # Sort candidates by score descending
        candidates.sort(key=lambda x: x[0], reverse=True)
        
        if not candidates:
            # No match -> new cluster
            clusters.append(_Cluster(doc))
            continue
            
        # Bridge detection
        # If matches >= 2 clusters with high token overlap and low score difference
        # overlap_ratio = |intersection| / max(1, |doc_set|)
        if len(candidates) >= 2:
            s1, c1 = candidates[0]
            s2, c2 = candidates[1]
            
            # Check score difference < 0.05
            if (s1 - s2) < 0.05:
                doc_tokens = set(doc.tokens)
                
                # Helper to calculate overlap
                def calc_overlap(c):
                    # Keys in cluster TF represent union of tokens in cluster
                    c_tokens = set(c._tf_sum.keys())
                    if not c_tokens: return 0.0
                    return len(doc_tokens & c_tokens) / max(1, len(doc_tokens))

                ov1 = calc_overlap(c1)
                ov2 = calc_overlap(c2)
                
                # If high overlap with both (>= 0.40)
                if ov1 >= 0.40 and ov2 >= 0.40:
                    # Bridge detected! Force new cluster to separate them
                    clusters.append(_Cluster(doc))
                    bridge_forced_count += 1
                    continue

        # No bridge detected, assign to best
        candidates[0][1].add(doc)
            
    return clusters, bridge_forced_count


# ===================================================================
# Promotion
# ===================================================================

def _cluster_id(filenames: List[str]) -> str:
    """Deterministic cluster ID: sha256 of filenames joined by '|', hex12."""
    canon = "|".join(sorted(filenames))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()[:12]


def _build_bundle_content(cluster: _Cluster, cluster_cid: str) -> str:
    """Build bundle markdown from a cluster."""
    lines = [
        "---",
        f"cluster_id: {cluster_cid}",
        f"file_count: {len(cluster.docs)}",
        f"created_utc: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "---",
        "",
        "## Included Files",
        "",
    ]
    for doc in cluster.docs:
        lines.append(f"- {doc.name}")

    # Collected URLs
    all_urls = []
    for doc in cluster.docs:
        all_urls.extend(doc.urls)
    all_urls = sorted(set(all_urls))
    if all_urls:
        lines.append("")
        lines.append("## Extracted URLs")
        lines.append("")
        for url in all_urls:
            lines.append(f"- {url}")

    # Content
    lines.append("")
    lines.append("## Content")
    lines.append("")
    for i, doc in enumerate(cluster.docs):
        if i > 0:
            lines.append("")
            lines.append("---")
            lines.append("")
        lines.append(doc.body)

    return "\n".join(lines) + "\n"


def _try_curate(bundle_path: Path) -> Tuple[bool, Optional[str]]:
    """Legacy/manual curate handoff helper, excluded from the default runtime path."""
    try:
        from app.hq.curation.curate import curate_file
        result = curate_file(str(bundle_path))
        if isinstance(result, dict):
            return True, result.get("hash") or result.get("path") or str(result)
        return True, str(result) if result else None
    except Exception as e:
        print(f"  [WARN] curate handoff failed: {e}", file=sys.stderr)
        return False, None


def _append_promo_log(
    capture_dir: Path,
    entry: Dict[str, Any],
) -> None:
    """Append to promotion_log.jsonl."""
    log_path = capture_dir / "promotion_log.jsonl"
    try:
        append_jsonl_atomic(log_path, dict(sorted(entry.items())))
    except Exception as exc:
        raise RuntimeError(f"Failed to append promotion log to {log_path}") from exc


def _append_canonical_hq_promotion_decision(
    canonical_ledger_path: Optional[Path],
    *,
    validation: Dict[str, Any],
    artifact_id: str,
    bundle_filename: str,
    cluster_id: str,
    candidate_cluster_members: List[str],
    bundle_path: Path,
    transition_ledger_path: Path,
    artifact_registry_path: Path,
    transition_event: Optional[Dict[str, Any]] = None,
    promotion_log_path: Optional[Path] = None,
) -> None:
    if canonical_ledger_path is None:
        return

    from signal_agent.formal_governance.adapters import append_hq_promotion_entry

    append_hq_promotion_entry(
        Path(canonical_ledger_path),
        validation=validation,
        artifact_id=artifact_id,
        bundle_filename=bundle_filename,
        cluster_id=cluster_id,
        candidate_cluster_members=candidate_cluster_members,
        bundle_path=bundle_path,
        promotion_log_path=promotion_log_path,
        transition_ledger_path=transition_ledger_path,
        transition_event=transition_event,
        artifact_registry_path=artifact_registry_path,
    )


def promote_run(
    window_hours: float = 48.0,
    min_cluster_size: int = 2,
    max_files: int = 500,
    dry_run: bool = False,
    threshold: float = 0.18,
    strategy: str = "hybrid",
    force: bool = False,
    capture_dir: Optional[Path] = None,
    canonical_ledger_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Run promotion: cluster raw captures, emit bundles, route them, and archive raw inputs.

    Returns summary dict.
    """
    base = capture_dir or _get_capture_dir()
    raw_dir = base / "raw"
    promoted_dir = base / "promoted"
    archive_dir = base / "archive"

    for d in (raw_dir, promoted_dir, archive_dir):
        d.mkdir(parents=True, exist_ok=True)

    # 1) Read raw files (sorted ascending for determinism)
    raw_files = sorted(raw_dir.glob("raw_*.md"))[:max_files]
    if not raw_files:
        return {"status": "no_raw_files", "clusters": 0, "bundles": [], "bridge_forced_count": 0}

    # 2) Parse into docs
    docs: List[_Doc] = []
    for rf in raw_files:
        try:
            text = rf.read_text(encoding="utf-8", errors="replace")
            meta, body = _parse_frontmatter(text)
            docs.append(_Doc(rf, meta, body))
        except Exception:
            continue

    if not docs:
        return {"status": "no_parseable_docs", "clusters": 0, "bundles": [], "bridge_forced_count": 0}

    # 3) Cluster
    clusters, bridge_forced_count = _cluster_docs(docs, threshold, window_hours, strategy)

    # 4) Filter by min size
    viable = [c for c in clusters if len(c.docs) >= min_cluster_size]

    if dry_run:
        summary = []
        for c in viable:
            cid = _cluster_id([d.name for d in c.docs])
            summary.append({
                "cluster_id": cid,
                "size": len(c.docs),
                "files": [d.name for d in c.docs],
            })
        return {
            "status": "dry_run", 
            "clusters": len(viable), 
            "bundles": summary,
            "bridge_forced_count": bridge_forced_count
        }

    # 5) Promote each viable cluster
    bundles = []
    for cluster in viable:
        filenames = [d.name for d in cluster.docs]
        cid = _cluster_id(filenames)
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        bundle_name = f"bundle_{date_str}_{cid}.md"
        bundle_path = promoted_dir / bundle_name

        # Resumability: skip if bundle exists unless --force
        if bundle_path.exists() and not force:
            bundles.append({"bundle": bundle_name, "status": "exists_skipped"})
            continue

        artifact_id = bundle_name
        registry_path, transition_ledger_path = _canonical_state_paths(base)
        from shared.state_registry import record_state, get_state
        from app.hq.governance import validate_transition, emit_transition_event, new_run_id

        prior = get_state(artifact_id, registry_path=registry_path)
        prior_state = prior.get("state") if prior else None
        promotion_run_id = new_run_id("promote")
        validation = validate_transition(
            current_state=prior_state,
            next_state="promoted",
            lane_id="volatile_capture",
            context={
                "module": "app.hq.capture.promote",
                "operation": "promote_run",
                "cluster_id": cid,
                "bundle_filename": bundle_name,
                "candidate_cluster_members": filenames,
            },
        )
        if not validation.get("allowed"):
            transition_event = emit_transition_event(
                validation,
                run_id=promotion_run_id,
                artifact_id=artifact_id,
                ledger_path=transition_ledger_path,
                context={
                    "module": "app.hq.capture.promote",
                    "operation": "promote_run",
                    "cluster_id": cid,
                    "bundle_filename": bundle_name,
                },
                event_type="transition_rejected",
            )
            _append_canonical_hq_promotion_decision(
                canonical_ledger_path,
                validation=validation,
                artifact_id=artifact_id,
                bundle_filename=bundle_name,
                cluster_id=cid,
                candidate_cluster_members=filenames,
                bundle_path=bundle_path,
                transition_ledger_path=transition_ledger_path,
                transition_event=transition_event,
                artifact_registry_path=registry_path,
            )
            current_label = prior_state if prior_state else "missing"
            raise RuntimeError(
                f"Canonical gate rejected promotion: "
                f"{current_label}->promoted: {validation.get('reason')}"
            )

        # Final promoted artifact materialization happens only after the
        # governed promotion decision succeeds. Candidate preparation above is
        # in-memory only and must not create promoted bundle artifacts.
        content = _build_bundle_content(cluster, cid)
        with open(bundle_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)

        transition_event = emit_transition_event(
            validation,
            run_id=promotion_run_id,
            artifact_id=artifact_id,
            ledger_path=transition_ledger_path,
            context={
                "module": "app.hq.capture.promote",
                "operation": "promote_run",
                "cluster_id": cid,
                "bundle_filename": bundle_name,
            },
            event_type="transition_attempt",
        )
        record_state(
            artifact_id=artifact_id,
            state="promoted",
            path=str(bundle_path),
            registry_path=registry_path,
        )

        # Spine router handoff (best-effort)
        route_result = _try_route(bundle_path)

        # Curate handoff is intentionally outside the promoted runtime surface.
        # curated, curated_ref = _try_curate(bundle_path)
        curated = False
        curated_ref = None

        # Archive raw files
        for doc in cluster.docs:
            dest = archive_dir / doc.name
            if doc.path.exists() and not dest.exists():
                shutil.move(str(doc.path), str(dest))

        # Collect domains
        all_domains = sorted(set().union(*(d.domains for d in cluster.docs)))

        # Log
        log_entry = {
            "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "cluster_id": cid,
            "bundle_filename": bundle_name,
            "raw_files": filenames,
            "domains": all_domains,
            "strategy": strategy,
            "threshold": threshold,
            "curate_invoked": curated,
            "curated_artifact_ref": curated_ref,
            "routed_spine": route_result.get("spine") if route_result else None,
            "bridge_forced": bridge_forced_count > 0,
            "status": "ok" if curated else "partial",
            "error": None,
        }

        _append_promo_log(base, log_entry)

        _append_canonical_hq_promotion_decision(
            canonical_ledger_path,
            validation=validation,
            artifact_id=artifact_id,
            bundle_filename=bundle_name,
            cluster_id=cid,
            candidate_cluster_members=filenames,
            bundle_path=bundle_path,
            transition_ledger_path=transition_ledger_path,
            transition_event=transition_event,
            artifact_registry_path=registry_path,
            promotion_log_path=base / "promotion_log.jsonl",
        )

        # Emit PromotionSucceeded event (best-effort)
        try:
            from shared.events import emit_event
            emit_event(
                "PromotionSucceeded",
                artifact_id,
                {
                    "bundle_path": str(bundle_path),
                    "cluster_id": cid,
                    "file_count": len(cluster.docs),
                },
            )
        except Exception:
            pass


        bundles.append({
            "bundle": bundle_name,
            "cluster_id": cid,
            "files": filenames,
            "curated": curated,
            "status": "ok" if curated else "partial",
        })

    return {
        "status": "ok",
        "instability_flags": _try_instability(base),
        "clusters": len(viable),
        "bundles": bundles,
        "bridge_forced_count": bridge_forced_count,
    }


# Spine router + instability helpers
# ===================================================================


def _try_route(bundle_path: Path) -> Optional[Dict[str, Any]]:
    """Best-effort spine routing after bundle creation."""
    try:
        from app.hq.capture.router import route_bundle
        return route_bundle(bundle_path=bundle_path)
    except Exception as e:
        print(f"  [WARN] route failed: {e}", file=sys.stderr)
        return None


def _try_instability(capture_dir: Path) -> List[Dict[str, Any]]:
    """Best-effort instability scan after promotion."""
    try:
        from app.hq.capture.instability import scan_instability
        result = scan_instability(capture_dir=capture_dir)
        return result.get("flags", [])
    except Exception as e:
        print(f"  [WARN] instability scan failed: {e}", file=sys.stderr)
        return []


# ===================================================================
# CLI entrypoint
# ===================================================================

def main(argv: Optional[list] = None) -> int:
    """CLI entrypoint for promote subcommand."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="brn capture.promote",
        description="Promote raw captures into clustered bundles.",
    )
    parser.add_argument(
        "--window-hours", type=float, default=48.0,
        help="Time window for clustering (hours)")
    parser.add_argument(
        "--min-cluster-size", type=int, default=2,
        help="Minimum docs per cluster")
    parser.add_argument(
        "--max-files", type=int, default=500,
        help="Maximum raw files to process")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview clusters without creating bundles")
    parser.add_argument(
        "--threshold", type=float, default=0.18,
        help="Similarity threshold for clustering")
    parser.add_argument(
        "--strategy", choices=["hybrid", "keyword", "domain_time"],
        default="hybrid", help="Clustering strategy")
    parser.add_argument(
        "--force", action="store_true",
        help="Overwrite existing bundles")
 
    args = parser.parse_args(argv)

    result = promote_run(
        window_hours=args.window_hours,
        min_cluster_size=args.min_cluster_size,
        max_files=args.max_files,
        dry_run=args.dry_run,
        threshold=args.threshold,
        strategy=args.strategy,
        force=args.force,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
