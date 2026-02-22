# Capture Layer v0.3 FIX1 Validation Report
**Date:** 2026-02-17 11:45:17 UTC

## Validation Checks
| Check | Status | Details |
|-------|--------|---------|
| A1: Invariant Check | PASS | See log |
| A2: CLI Presence | PASS | See log |
| A3: Stress Schema | PASS | See log |
| A4: Status Telemetry | PASS | See log |
| A5: Two-Stage Decay | PASS | See log |
| A6: Router Hash | PASS | See log |
| A7: Instability Rule | PASS | See log |
| A8: Bridge Defense | PASS | See log |
| A9: Regression Tests | PASS | See log |
| A10: Determinism | PASS | See log |

## Registry Invariant Status
Artifact Registry Path: `E:\signal_agent\data\artifact_registry.jsonl`
Drift Detected: **False**

### Baseline Snapshot
```json
{
  "exists": true,
  "size": 43797,
  "mtime": 1771322142000000000,
  "sha256": "780102ab3c32f9ba831dedb9a77cbe3f08828d1eb9630fde6603146cbd66fe62"
}
```

### Final Snapshot
```json
{
  "exists": true,
  "size": 43797,
  "mtime": 1771322142000000000,
  "sha256": "780102ab3c32f9ba831dedb9a77cbe3f08828d1eb9630fde6603146cbd66fe62"
}
```

*Registry Integrity Verified*

## Execution Log
```
A1: Invariant Check: PASS - Registry baseline established. Exists: True
A2: CLI Presence: PASS - All CLIs present
COMMAND: C:\Users\mrcol\AppData\Local\Python\pythoncore-3.12-64\python.exe -m app.agent capture.stress --docs 25 --themes 3 --bridge --keyword-stuff --time-skew
OUTPUT: {
  "docs_generated": 27,
  "themes": 3,
  "clusters_created": 3,
  "bridge_isolated": false,
  "keyword_stuffing_isolated": true,
  "instability_detected": false
}
...
STDERR: [DEBUG] Instability scanning 27 files.
[DEBUG] Check tid=33e34410074a day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Check tid=c010611bdfa7 day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Check tid=c10d1c35577c day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Instability scanning 27 files.
[DEBUG] Check tid=33e34410074a day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Check tid=c010611bdfa7 day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Check tid=c10d1c35577c day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
...
A3: Stress Schema: PASS - Schema correct.
COMMAND: C:\Users\mrcol\AppData\Local\Python\pythoncore-3.12-64\python.exe -m app.agent capture.status
OUTPUT: {
  "raw_count": 0,
  "promoted_count": 3,
  "archived_count": 27,
  "expired_stage1_count": 0,
  "expired_stage2_count": 0,
  "raw_oldest_age_days": null,
  "raw_newest_age_minutes": null,
  "instability_flags_last_24h": 0,
  "router_ruleset_hash": "7cad2a1c8c65",
  "last_capture_ts": null,
  "last_promotion_ts": "2026-02-17T11:45:04Z",
  "last_decay_ts": null,
  "last_instability_ts": null
}
...
A4: Status Telemetry: PASS - Status telemetry correct
COMMAND: C:\Users\mrcol\AppData\Local\Python\pythoncore-3.12-64\python.exe -m app.agent capture.decay --days 14 --purge-days 30
OUTPUT: {
  "status": "ok",
  "days": 14,
  "purge_days": 30,
  "stage1_count": 1,
  "stage2_count": 0,
  "stage1_moved": [
    "raw_2026-02-02T11-45-07_testA5Z.md"
  ],
  "stage2_moved": []
}
...
COMMAND: C:\Users\mrcol\AppData\Local\Python\pythoncore-3.12-64\python.exe -m app.agent capture.decay --days 14 --purge-days 30
OUTPUT: {
  "status": "ok",
  "days": 14,
  "purge_days": 30,
  "stage1_count": 0,
  "stage2_count": 1,
  "stage1_moved": [],
  "stage2_moved": [
    "raw_2026-02-02T11-45-07_testA5Z.md"
  ]
}
...
A5: Two-Stage Decay: PASS - Two-stage decay verified
COMMAND: C:\Users\mrcol\AppData\Local\Python\pythoncore-3.12-64\python.exe -m app.agent capture.add --text routing test
OUTPUT: [OK] raw_2026-02-17T11-45-08_476Z.md -> E:\signal_agent\data\capture\raw\raw_2026-02-17T11-45-08_476Z.md
...
COMMAND: C:\Users\mrcol\AppData\Local\Python\pythoncore-3.12-64\python.exe -m app.agent capture.promote --min-cluster-size 1 --force
OUTPUT: {
  "status": "ok",
  "instability_flags": [],
  "clusters": 1,
  "bundles": [
    {
      "bundle": "bundle_20260217_abf87199e910.md",
      "cluster_id": "abf87199e910",
      "files": [
        "raw_2026-02-17T11-45-08_476Z.md"
      ],
      "curated": false,
      "status": "partial"
    }
  ],
  "bridge_forced_count": 0
}
...
STDERR: [DEBUG] Instability scanning 1 files.
[DEBUG] Check tid=099081e4031a day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
...
COMMAND: C:\Users\mrcol\AppData\Local\Python\pythoncore-3.12-64\python.exe -m app.agent capture.route --bundle E:\signal_agent\data\capture\promoted\bundle_20260217_abf87199e910.md
OUTPUT: {
  "bundle": "bundle_20260217_abf87199e910.md",
  "spine": "misc",
  "score": 0.065,
  "rationale": {
    "top_keywords": [],
    "matched_domains": []
  },
  "router_ruleset_hash": "7cad2a1c8c65",
  "status": "ok",
  "error": null
}
...
COMMAND: C:\Users\mrcol\AppData\Local\Python\pythoncore-3.12-64\python.exe -m app.agent capture.status
OUTPUT: {
  "raw_count": 0,
  "promoted_count": 1,
  "archived_count": 1,
  "expired_stage1_count": 0,
  "expired_stage2_count": 0,
  "raw_oldest_age_days": null,
  "raw_newest_age_minutes": null,
  "instability_flags_last_24h": 0,
  "router_ruleset_hash": "7cad2a1c8c65",
  "last_capture_ts": "2026-02-17T11:45:08Z",
  "last_promotion_ts": "2026-02-17T11:45:08Z",
  "last_decay_ts": null,
  "last_instability_ts": null
}
...
A6: Router Hash: PASS - Hash consistent: 7cad2a1c8c65
COMMAND: C:\Users\mrcol\AppData\Local\Python\pythoncore-3.12-64\python.exe -m app.agent capture.stress --docs 30 --themes 1 --keyword-stuff --seed 1
OUTPUT: {
  "docs_generated": 31,
  "themes": 1,
  "clusters_created": 1,
  "bridge_isolated": true,
  "keyword_stuffing_isolated": true,
  "instability_detected": true
}
...
STDERR: [DEBUG] Instability scanning 31 files.
[DEBUG] Check tid=06ff8d7a94e9 day=2026-02-17 count=3 baseline=0.00 ratio=3000000000.00
[DEBUG] Check tid=0da8cf3fa541 day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Check tid=1d486df4bd7d day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Check tid=23e8addb8131 day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Check tid=2d4f4f4c682c day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Check tid=3659a7d199ef day=2026-02-17 count=6 baseline=0.00 ratio=6000000000.00
[DEBUG] Flagged spike tid=3659a7d199ef day=2026-02-17 count=6 ratio=6000000000.00
[DEBUG] Check tid=3ffa73007de7 day=2026-02-17 count=4 baseline=0.00 ratio=4000000000.00
[DEBUG] Check tid=426d7094438a day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Check tid=51026ff08bbc day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Check tid=69c9e1944139 day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00...
COMMAND: C:\Users\mrcol\AppData\Local\Python\pythoncore-3.12-64\python.exe -m app.agent capture.instability --window-days 7 --min-today 1 --ratio 0.1
OUTPUT: {
  "status": "ok",
  "flags": [
    {
      "topic_id": "06ff8d7a94e9",
      "utc_day": "2026-02-17",
      "today_count": 3,
      "baseline": 0.0,
      "spike_ratio": 3000000000.0,
      "severity": "major",
      "top_tokens": [
        "align",
        "coherence",
        "diagnostic",
        "drift",
        "embedding",
        "kernel",
        "metric",
        "signal",
        "stability",
        "vector",
        "article",
        "https"
      ],
      "domains": [
        "ai...
STDERR: [DEBUG] Instability scanning 31 files.
[DEBUG] Check tid=06ff8d7a94e9 day=2026-02-17 count=3 baseline=0.00 ratio=3000000000.00
[DEBUG] Flagged spike tid=06ff8d7a94e9 day=2026-02-17 count=3 ratio=3000000000.00
[DEBUG] Check tid=0da8cf3fa541 day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Flagged spike tid=0da8cf3fa541 day=2026-02-17 count=1 ratio=1000000000.00
[DEBUG] Check tid=1d486df4bd7d day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Flagged spike tid=1d486df4bd7d day=2026-02-17 count=1 ratio=1000000000.00
[DEBUG] Check tid=23e8addb8131 day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Flagged spike tid=23e8addb8131 day=2026-02-17 count=1 ratio=1000000000.00
[DEBUG] Check tid=2d4f4f4c682c day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Flagged spike tid=2d4f4f4c682c day=2026-02-17 count=1 ratio=1000000000.00
[DEBUG] Check tid=3659a7d199ef day=2026-02-17 count=6 baseline=0.00 ratio=6000000000.00
[DEBUG] Flagged spike t...
A7: Instability Rule: PASS - PASS_WITH_NOTE: Cold start detected (baseline=0). Valid behavior.
COMMAND: C:\Users\mrcol\AppData\Local\Python\pythoncore-3.12-64\python.exe -m app.agent capture.stress --docs 60 --themes 2 --bridge --keyword-stuff --time-skew --seed 42
OUTPUT: {
  "docs_generated": 62,
  "themes": 2,
  "clusters_created": 2,
  "bridge_isolated": true,
  "keyword_stuffing_isolated": true,
  "instability_detected": false
}
...
STDERR: [DEBUG] Instability scanning 62 files.
[DEBUG] Check tid=0688a90d8a15 day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Check tid=06ff8d7a94e9 day=2026-02-17 count=1 baseline=0.67 ratio=1.50
[DEBUG] Check tid=0c99bb1e8986 day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Check tid=18945dab80d6 day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Check tid=3b366b92471b day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Check tid=42804ec9858d day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Check tid=4cc053b5d4d2 day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Check tid=6eefabac529d day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Check tid=715a3d41e86d day=2026-02-17 count=1 baseline=0.17 ratio=6.00
[DEBUG] Check tid=7175cd6370e1 day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Check tid=7d822230390d day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Che...
COMMAND: C:\Users\mrcol\AppData\Local\Python\pythoncore-3.12-64\python.exe -m app.agent capture.promote --min-cluster-size 1 --force --window-hours 72
OUTPUT: {
  "status": "ok",
  "instability_flags": [],
  "clusters": 3,
  "bundles": [
    {
      "bundle": "bundle_20260217_19058a1b1adc.md",
      "cluster_id": "19058a1b1adc",
      "files": [
        "raw_2026-02-14T11-45-10_042Z.md",
        "raw_2026-02-14T14-45-10_044Z.md",
        "raw_2026-02-14T20-45-10_052Z.md",
        "raw_2026-02-15T02-45-10_020Z.md",
        "raw_2026-02-15T02-45-10_023Z.md",
        "raw_2026-02-15T03-45-10_034Z.md",
        "raw_2026-02-15T08-45-10_032Z.md",
        "r...
STDERR: [DEBUG] Instability scanning 62 files.
[DEBUG] Check tid=0688a90d8a15 day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Check tid=06ff8d7a94e9 day=2026-02-17 count=1 baseline=0.67 ratio=1.50
[DEBUG] Check tid=0c99bb1e8986 day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Check tid=18945dab80d6 day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Check tid=3b366b92471b day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Check tid=42804ec9858d day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Check tid=4cc053b5d4d2 day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Check tid=6eefabac529d day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Check tid=715a3d41e86d day=2026-02-17 count=1 baseline=0.17 ratio=6.00
[DEBUG] Check tid=7175cd6370e1 day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Check tid=7d822230390d day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Che...
A8: Bridge Defense: PASS - Bridge defense successful (Forced Count: 1, Logged: True)
A9: Regression Tests: PASS - Tests passed
COMMAND: C:\Users\mrcol\AppData\Local\Python\pythoncore-3.12-64\python.exe -m app.agent capture.stress --docs 60 --themes 2 --bridge --keyword-stuff --time-skew --seed 42
OUTPUT: {
  "docs_generated": 62,
  "themes": 2,
  "clusters_created": 2,
  "bridge_isolated": true,
  "keyword_stuffing_isolated": true,
  "instability_detected": false
}
...
STDERR: [DEBUG] Instability scanning 62 files.
[DEBUG] Check tid=0688a90d8a15 day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Check tid=06ff8d7a94e9 day=2026-02-17 count=1 baseline=0.67 ratio=1.50
[DEBUG] Check tid=0c99bb1e8986 day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Check tid=18945dab80d6 day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Check tid=3b366b92471b day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Check tid=42804ec9858d day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Check tid=4cc053b5d4d2 day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Check tid=6eefabac529d day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Check tid=715a3d41e86d day=2026-02-17 count=1 baseline=0.17 ratio=6.00
[DEBUG] Check tid=7175cd6370e1 day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Check tid=7d822230390d day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Che...
COMMAND: C:\Users\mrcol\AppData\Local\Python\pythoncore-3.12-64\python.exe -m app.agent capture.stress --docs 60 --themes 2 --bridge --keyword-stuff --time-skew --seed 42
OUTPUT: {
  "docs_generated": 62,
  "themes": 2,
  "clusters_created": 2,
  "bridge_isolated": true,
  "keyword_stuffing_isolated": true,
  "instability_detected": false
}
...
STDERR: [DEBUG] Instability scanning 62 files.
[DEBUG] Check tid=0688a90d8a15 day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Check tid=06ff8d7a94e9 day=2026-02-17 count=1 baseline=0.67 ratio=1.50
[DEBUG] Check tid=0c99bb1e8986 day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Check tid=18945dab80d6 day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Check tid=3b366b92471b day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Check tid=42804ec9858d day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Check tid=4cc053b5d4d2 day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Check tid=6eefabac529d day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Check tid=715a3d41e86d day=2026-02-17 count=1 baseline=0.17 ratio=6.00
[DEBUG] Check tid=7175cd6370e1 day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Check tid=7d822230390d day=2026-02-17 count=1 baseline=0.00 ratio=1000000000.00
[DEBUG] Che...
A10: Determinism: PASS - Deterministic behavior confirmed
```