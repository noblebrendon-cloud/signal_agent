# Signal Pipelines — Lane-Aware Post Composer (Internal)

> **v0.1** — Internal tooling only. No network calls. No external posting.

## Overview

The Signal Pipelines subsystem converts social queue items into publishable render targets (HTML + MD + manifest) staged to the filesystem. All outputs are deterministic (byte-identical across runs), idempotent, and fail-closed.

## Dual Lanes

| Lane | Purpose | Platforms |
|------|---------|-----------|
| `artifact_channel` | Automated artifact distribution | linkedin, substack, github |
| `human_channel` | Human-reviewed content | facebook, youtube |

## Directory Layout

```
data/social_queue/                    # Input queue items (JSON)
├── artifact_channel/
│   ├── linkedin/
│   ├── substack/
│   └── github/
└── human_channel/
    ├── facebook/
    └── youtube/

data/social_out/                      # Composed outputs
├── artifact_channel/
│   ├── linkedin/<queue_id>/
│   │   ├── post.html
│   │   ├── post.md
│   │   └── manifest.json
│   ├── substack/<queue_id>/
│   └── github/<queue_id>/           # MD-only (no HTML)
└── human_channel/
    ├── facebook/<queue_id>/
    └── youtube/<queue_id>/
```

## Queue Contract: `social_queue_v1`

Each queue item is a JSON file with these required fields:

| Field | Type | Description |
|-------|------|-------------|
| `queue_version` | string | Must be `"social_queue_v1"` |
| `queue_id` | string | 12-char hex (auto-computed if missing) |
| `lane` | string | `"artifact_channel"` or `"human_channel"` |
| `platform` | string | linkedin, substack, github, facebook, youtube |
| `intent` | string | `"post"`, `"description"`, or `"thread"` |
| `meme_id` | string | Source meme identifier |
| `render_paths` | list[str] | Paths to rendered artifacts (must exist) |
| `artifact_links` | list[{label,path}] | Artifact references |
| `copy.headline` | string | Post headline (can be empty for youtube) |
| `copy.body` | string | Post body text |
| `pack.pack_id` | string | Constraint pack ID |
| `pack.pack_hash` | string | Pack integrity hash |
| `provenance.*` | strings | source_artifact_id, session_id, created_at_utc |

### `queue_id` Computation

If not provided, computed deterministically:

```
queue_id = sha256(
    queue_version + lane + platform + intent +
    normalized(headline + body) +
    sorted(render_paths) +
    sorted(artifact_links by label+path)
)[:12]
```

## Determinism Guarantees

- **UTF-8 encoding, LF-only newlines** — no CRLF in any output
- **Sorted inputs** — render_paths and artifact_links sorted before rendering
- **Normalized text** — CRLF → LF, trailing spaces stripped
- **No timestamps in outputs** — only in manifest provenance (from input)
- **Atomic writes** — temp file + `os.replace()`
- **SHA256 in manifest** — verifiable integrity for all output files

## Idempotency

- If output files exist with identical bytes → skip (no write)
- If output files exist with different bytes → fail-closed (use `--force` to overwrite)
- Manifest SHA256 hashes enable verification

## CLI Usage

```bash
# Compose oldest 5 LinkedIn queue items
brn signal.compose --lane artifact_channel --platform linkedin --limit 5

# Dry-run validation only
brn signal.compose --lane human_channel --platform youtube --limit 10 --dry-run

# Force overwrite existing outputs
brn signal.compose --lane artifact_channel --platform substack --limit 3 --force
```

## No Network Calls

This subsystem writes to the local filesystem only. No HTTP requests, no API calls, no webhooks. Queue items are consumed from `data/social_queue/` and outputs are written to `data/social_out/`.

## Module Location

```
app/hq/post_composer/
├── __init__.py
├── queue_contract.py     # SocialQueueV1 + validation
├── compose.py            # Compose engine
└── templates/
    ├── linkedin_post.html
    ├── facebook_post.html
    ├── youtube_description.html
    └── substack_post.html
```
