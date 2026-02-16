# SIGNAL OPERATOR GUIDE (Internal)

## Purpose

This system stages governed signal artifacts for publishing.
It does NOT auto-post.
It produces ready-to-copy outputs.

If something fails, it fails safely.

---

## Core Workflow (3 Steps)

### 1) Generate Signal Artifacts

When you have an idea or completed feature:

```
brn meme.offload --in <artifact_path> --pack CONTENT_MEME_OFFLOAD_v1 --n 2
```

This places staged items into:

```
data/social_queue/<lane>/<platform>/
```

You do not need to inspect internal files.

---

### 2) Compose Publish-Ready Outputs

Example (LinkedIn, artifact lane):

```
brn signal.compose --lane artifact_channel --platform linkedin --limit 3
```

This generates:

```
data/social_out/<lane>/<platform>/<queue_id>/
```

Inside each folder:
- `post.html`
- `post.md`
- `manifest.json`

Use `post.md` for quick copy/paste.
Use `post.html` if you need structured formatting.

---

### 3) Publish Manually

Open the generated folder.
Copy from `post.md`.
Paste into platform.
Attach image if applicable.
Done.

No automation.
No scheduling.
No API calls.

---

## Lanes Explained

**artifact_channel**
- LinkedIn
- Substack
- GitHub

Structured authority signal.

**human_channel**
- Facebook
- YouTube

Personal signal.

Always choose lane intentionally.

---

## Common Commands

LinkedIn (artifact):

```
brn signal.compose --lane artifact_channel --platform linkedin --limit 1
```

Facebook (human):

```
brn signal.compose --lane human_channel --platform facebook --limit 1
```

YouTube:

```
brn signal.compose --lane human_channel --platform youtube --limit 1
```

Dry-run (validate only):

```
brn signal.compose --lane artifact_channel --platform linkedin --limit 5 --dry-run
```

---

## If Something Errors

1. Read the error message.
2. Ensure referenced files exist in `data/social_queue/`.
3. Ensure render paths exist.
4. Re-run command.
5. If still failing, review test fixtures for structure reference.

The system fails closed.
It does not silently corrupt output.

---

## Important Rules

- Do not edit files inside `data/social_out/` manually.
- If content must change, regenerate from queue.
- Do not bypass validation.
- Do not modify manifest files.
- Do not embed timestamps in templates.

---

## Mental Model

Build deeply.
Extract lightly.
Compose weekly.
Publish intentionally.

The system protects determinism.
You provide judgment.
