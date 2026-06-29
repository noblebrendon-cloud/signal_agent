# Operator Content Library

This directory is the shared evidence-to-teaching library for completed system work.
It is committed documentation, not runtime state, product-local documentation, or
publication automation.

The library preserves verified build events, extracts reusable teaching atoms, queues
possible derivatives, and records only content that was actually published. It does
not create posts, videos, essays, diagrams, or social content automatically.

## Placement

The library lives at:

```text
docs/operator/content_library/
```

This level is intentionally above individual implementation domains. Project Studio,
Governed Publishing, Laviathon, Clarity Systems Group, publishing surfaces, and future
tools can all feed it without making one product's local docs the source of record.

Do not move this library under `app/`, `data/state/`, or only under
`project_studio/`. Those are implementation or runtime domains.

## Layers

| Layer | Purpose |
| --- | --- |
| `events/` | Factual records of completed builds or system changes. |
| `teaching_atoms/` | Reusable concepts extracted from one or more events. |
| `derivatives/` | Queued, drafted, and published content artifacts when deliberately created later. |
| `CONTENT_LIBRARY_INDEX.md` | Event-level index and capture status. |
| `PUBLISHED_CONTENT_INDEX.md` | Public publication log. |
| `tools/new_content_event.py` | Idempotent scaffold for creating or reopening event records. |

## Operating Rule

Capture first; publish later. A build event is allowed to preserve evidence, concepts,
and future derivative ideas. It must not silently convert a passing implementation
boundary into public content.

