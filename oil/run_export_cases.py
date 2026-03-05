"""
OIL -- Diagnostic Packaging Export (v0.9)

Exports verified case bundles into a client-safe dossier with a manifest.
Optionally anonymizes service names deterministically.

Usage:
  python -m oil.run_export_cases --output <dir>
         [--last N | --from YYYY-MM-DD --to YYYY-MM-DD]
         [--min-confidence 0.8]
         [--include-outcomes]
         [--anonymize]
         [--cases-dir <path>]

Output structure:
  <output>/cases/<run_id>/    -- copy of case folder (filtered files)
  <output>/manifest.json      -- per-case metadata list
  <output>/summary.json       -- aggregate stats
  <output>/summary.txt        -- human-readable aggregate
  <output>/anonymization_map.json  (only when --anonymize)

Exit codes: 0 = success, 1 = error.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

_OIL_ROOT = Path(__file__).resolve().parent
_DEFAULT_CASES_DIR = _OIL_ROOT / "cases"
_ENVELOPE_FIELDS = ["artifact_version", "oil_version", "created_utc", "run_id", "inputs_digest"]

# ─── helpers ──────────────────────────────────────────────────────────────────

def _parse_utc(ts: str) -> datetime:
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return datetime.min.replace(tzinfo=timezone.utc)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_bytes())
    except Exception:
        return None


def _is_hex_run_id(name: str) -> bool:
    return len(name) >= 8 and all(c in "0123456789abcdef" for c in name)

# ─── case loading ─────────────────────────────────────────────────────────────

def _load_case_meta(case_dir: Path) -> dict | None:
    """Load metadata for a case folder. Returns None if invalid."""
    memory = _load_json(case_dir / "memory.json")
    incident = _load_json(case_dir / "incident.json")
    if memory is None or incident is None:
        return None
    created_utc = memory.get("created_utc") or incident.get("created_utc", "")
    return {
        "run_id":         case_dir.name,
        "case_dir":       case_dir,
        "created_utc":    created_utc,
        "created_dt":     _parse_utc(created_utc),
        "fingerprint_id": memory.get("fingerprint_id", ""),
        "origin_service": memory.get("origin_service", ""),
        "action_target":  memory.get("action_target_service", ""),
        "confidence":     float(memory.get("confidence", 0.0)),
        "action_category":memory.get("action_category", ""),
        "inputs_digest":  incident.get("inputs_digest", ""),
        "artifact_path":  memory.get("artifact_path", ""),
        "memory":         memory,
        "incident":       incident,
    }

# ─── case selection ───────────────────────────────────────────────────────────

def select_cases(
    cases_dir: Path,
    last_n: int | None,
    from_dt: datetime | None,
    to_dt: datetime | None,
    min_confidence: float,
) -> list[dict]:
    """Enumerate and filter case folders. Returns list sorted by (created_utc, run_id)."""
    if not cases_dir.exists():
        return []

    metas = []
    for case_dir in cases_dir.iterdir():
        if not case_dir.is_dir() or not _is_hex_run_id(case_dir.name):
            continue
        meta = _load_case_meta(case_dir)
        if meta is None:
            continue
        if meta["confidence"] < min_confidence:
            continue
        dt = meta["created_dt"]
        if from_dt and dt < from_dt:
            continue
        if to_dt and dt > to_dt:
            continue
        metas.append(meta)

    # Deterministic sort by (created_utc, run_id)
    metas.sort(key=lambda m: (m["created_utc"], m["run_id"]))

    if last_n is not None:
        metas = metas[-last_n:]

    return metas

# ─── per-case verification ────────────────────────────────────────────────────

def _verify_case(meta: dict) -> str:
    """Return 'verified' or a short failure reason."""
    incident = meta["incident"]
    for field in _ENVELOPE_FIELDS:
        if not incident.get(field):
            return f"missing_field:{field}"

    # run_id consistency check
    created_utc = incident.get("created_utc", "")
    inputs_digest = incident.get("inputs_digest", "")
    payload = created_utc + "|" + inputs_digest
    computed = hashlib.sha256(payload.encode()).hexdigest()[:16]
    stored = incident.get("run_id", "")
    if stored != computed:
        return "run_id_mismatch"

    # Case incident.json vs original artifact digest (if available)
    artifact_path = Path(meta["artifact_path"]) if meta["artifact_path"] else None
    if artifact_path and artifact_path.exists():
        case_bytes = (meta["case_dir"] / "incident.json").read_bytes()
        art_bytes = artifact_path.read_bytes()
        if _sha256_bytes(case_bytes) != _sha256_bytes(art_bytes):
            return "incident_digest_mismatch"

    return "verified"

# ─── final outcome lookup ─────────────────────────────────────────────────────

def _get_final_outcome_kind(case_dir: Path) -> str:
    outcomes_path = case_dir / "outcomes.jsonl"
    if not outcomes_path.exists():
        return ""
    entries = []
    for line in outcomes_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if not entries:
        return ""
    from oil.memory.outcomes import select_final_outcome
    final = select_final_outcome(entries)
    return final["outcome_kind"] if final else ""

# ─── anonymization ────────────────────────────────────────────────────────────

def build_anon_map(metas: list[dict]) -> dict[str, str]:
    """Build deterministic service→SVC_NN mapping from all unique service names."""
    services: set[str] = set()
    for m in metas:
        for key in ("origin_service", "action_target"):
            svc = m.get(key, "")
            if svc:
                services.add(svc)
        # Also collect from incident report evidence and reference_service
        report = m.get("incident", {}).get("report", {})
        if isinstance(report, dict):
            rsvc = report.get("reference_service", "")
            if rsvc:
                services.add(rsvc)
            for ev in report.get("evidence", []):
                esvc = ev.get("service", "")
                if esvc:
                    services.add(esvc)
    mapping = {}
    for i, svc in enumerate(sorted(services), start=1):
        mapping[svc] = f"SVC_{i:02d}"
    return mapping


def _apply_anon_to_str(text: str, anon_map: dict[str, str]) -> str:
    """Apply anonymization map to a string (longest match first for safety)."""
    for real, alias in sorted(anon_map.items(), key=lambda kv: -len(kv[0])):
        text = text.replace(real, alias)
    return text


def _apply_anon_to_obj(obj: object, anon_map: dict[str, str]) -> object:
    """Recursively apply anonymization to a JSON-like object."""
    if isinstance(obj, str):
        return _apply_anon_to_str(obj, anon_map)
    if isinstance(obj, dict):
        return {k: _apply_anon_to_obj(v, anon_map) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_apply_anon_to_obj(item, anon_map) for item in obj]
    return obj


def _anonymize_case_export(case_export_dir: Path, anon_map: dict[str, str]) -> None:
    """Rewrite exported case files in-place applying anonymization."""
    for fname in ("incident.json", "memory.json"):
        fpath = case_export_dir / fname
        if fpath.exists():
            data = json.loads(fpath.read_bytes())
            anon_data = _apply_anon_to_obj(data, anon_map)
            fpath.write_text(
                json.dumps(anon_data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
    summary_path = case_export_dir / "summary.txt"
    if summary_path.exists():
        text = summary_path.read_text(encoding="utf-8")
        summary_path.write_text(_apply_anon_to_str(text, anon_map), encoding="utf-8")
    outcomes_path = case_export_dir / "outcomes.jsonl"
    if outcomes_path.exists():
        lines = outcomes_path.read_text(encoding="utf-8").splitlines()
        new_lines = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                entry["notes"] = _apply_anon_to_str(entry.get("notes", ""), anon_map)
                new_lines.append(json.dumps(entry, ensure_ascii=False, separators=(",", ":")))
            except json.JSONDecodeError:
                new_lines.append(line)
        outcomes_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

# ─── summary builders ─────────────────────────────────────────────────────────

def _build_summary(manifest: list[dict]) -> dict:
    if not manifest:
        return {
            "total_exported": 0, "date_range": {"from": "", "to": ""},
            "avg_confidence": 0.0, "verified_count": 0,
            "most_common_origin": "", "most_common_action": "",
            "outcome_counts": {},
        }
    confs = [e["confidence"] for e in manifest]
    origins = Counter(e["origin_service"] for e in manifest if e["origin_service"])
    actions = Counter(e["action_category"] for e in manifest if e["action_category"])
    outcomes = Counter(e["final_outcome_kind"] for e in manifest if e["final_outcome_kind"])
    verified = sum(1 for e in manifest if e["verification_status"] == "verified")
    dates = sorted(e["created_utc"] for e in manifest if e["created_utc"])
    return {
        "total_exported":      len(manifest),
        "date_range":          {"from": dates[0] if dates else "", "to": dates[-1] if dates else ""},
        "avg_confidence":      round(sum(confs) / len(confs), 4) if confs else 0.0,
        "verified_count":      verified,
        "most_common_origin":  origins.most_common(1)[0][0] if origins else "",
        "most_common_action":  actions.most_common(1)[0][0] if actions else "",
        "outcome_counts":      dict(outcomes),
    }


def _build_summary_txt(summary: dict) -> str:
    lines = [
        "OIL DIAGNOSTIC EXPORT SUMMARY",
        "=" * 40,
        f"total_exported:      {summary['total_exported']}",
        f"verified:            {summary['verified_count']}",
        f"avg_confidence:      {summary['avg_confidence']:.2%}",
        f"date_from:           {summary['date_range']['from']}",
        f"date_to:             {summary['date_range']['to']}",
        f"most_common_origin:  {summary['most_common_origin']}",
        f"most_common_action:  {summary['most_common_action']}",
    ]
    if summary.get("outcome_counts"):
        lines.append("outcome_counts:")
        for k, v in sorted(summary["outcome_counts"].items()):
            lines.append(f"  {k}: {v}")
    return "\n".join(lines)

# ─── export engine ────────────────────────────────────────────────────────────

def export_cases(
    cases_dir: Path,
    output_dir: Path,
    last_n: int | None = None,
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
    min_confidence: float = 0.0,
    include_outcomes: bool = False,
    anonymize: bool = False,
) -> dict:
    """Select, verify, and export case bundles. Returns a report dict."""
    metas = select_cases(cases_dir, last_n, from_dt, to_dt, min_confidence)
    anon_map: dict[str, str] = build_anon_map(metas) if anonymize else {}

    output_dir.mkdir(parents=True, exist_ok=True)
    cases_out = output_dir / "cases"
    cases_out.mkdir(exist_ok=True)

    manifest: list[dict] = []

    for meta in metas:
        run_id = meta["run_id"]
        case_dir = meta["case_dir"]
        export_case_dir = cases_out / run_id
        export_case_dir.mkdir(exist_ok=True)

        # Copy files (deterministic: alphabetical order)
        files_to_copy = sorted(case_dir.iterdir(), key=lambda p: p.name)
        for src in files_to_copy:
            if not src.is_file():
                continue
            if src.name == "outcomes.jsonl" and not include_outcomes:
                continue
            shutil.copy2(src, export_case_dir / src.name)

        # Anonymize in-place (post-copy)
        if anonymize:
            _anonymize_case_export(export_case_dir, anon_map)

        # Verification
        vstatus = _verify_case(meta)

        # Final outcome
        final_outcome = _get_final_outcome_kind(case_dir) if include_outcomes else ""

        entry = {
            "run_id":               run_id,
            "created_utc":          meta["created_utc"],
            "fingerprint_id":       meta["fingerprint_id"],
            "origin_service":       anon_map.get(meta["origin_service"], meta["origin_service"]) if anonymize else meta["origin_service"],
            "confidence":           meta["confidence"],
            "action_category":      meta["action_category"],
            "final_outcome_kind":   anon_map.get(final_outcome, final_outcome) if anonymize else final_outcome,
            "inputs_digest":        meta["inputs_digest"],
            "verification_status":  vstatus,
        }
        manifest.append(entry)

    # Write manifest
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # Write summary
    summary = _build_summary(manifest)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "summary.txt").write_text(_build_summary_txt(summary), encoding="utf-8")

    # Write anonymization map
    if anonymize:
        (output_dir / "anonymization_map.json").write_text(
            json.dumps(anon_map, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    return {
        "total_selected": len(metas),
        "total_exported": len(manifest),
        "manifest_path":  str(manifest_path),
        "output_dir":     str(output_dir),
        "anonymized":     anonymize,
    }

# ─── CLI ──────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="oil.run_export_cases",
        description="OIL -- export verified case bundles into a diagnostic dossier",
    )
    parser.add_argument("--output",          required=True, help="Output directory")
    parser.add_argument("--last",            type=int, default=None, metavar="N")
    parser.add_argument("--from",            dest="from_date", default=None, metavar="YYYY-MM-DD")
    parser.add_argument("--to",              dest="to_date",   default=None, metavar="YYYY-MM-DD")
    parser.add_argument("--min-confidence",  type=float, default=0.0)
    parser.add_argument("--include-outcomes",action="store_true", default=False)
    parser.add_argument("--anonymize",       action="store_true", default=False)
    parser.add_argument("--cases-dir",       default=str(_DEFAULT_CASES_DIR))
    args = parser.parse_args(argv)

    from_dt = None
    to_dt = None
    try:
        if args.from_date:
            from_dt = datetime.strptime(args.from_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if args.to_date:
            to_dt = datetime.strptime(args.to_date + "T23:59:59", "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        print(f"ERROR: invalid date: {exc}", file=sys.stderr)
        return 1

    try:
        report = export_cases(
            cases_dir=Path(args.cases_dir),
            output_dir=Path(args.output),
            last_n=args.last,
            from_dt=from_dt,
            to_dt=to_dt,
            min_confidence=args.min_confidence,
            include_outcomes=args.include_outcomes,
            anonymize=args.anonymize,
        )
        print(json.dumps(report, indent=2))
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
