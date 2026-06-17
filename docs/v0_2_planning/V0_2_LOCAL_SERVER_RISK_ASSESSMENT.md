# v0.2 Local Server Risk Assessment

Version target:

```text
v0.2-local-authoring-surface
```

## Assessment Purpose

This document records why local server work is deferred for v0.2 until the command-router foundation and write-boundary tests exist.

It is documentation/decision only. It does not add server code, network behavior, browser-backend submission, production writes, or default canonical ledger writes.

## Current Decision

Local server work is deferred.

The next approved runtime direction is a local command-router foundation with fail-closed path classification and explicit output boundaries.

## Key Risks

### Mistaken Production Backend

A local server may be mistaken for a production backend even when it is intended only for local use.

Risk:

- Users may infer production readiness.
- Documentation may drift into backend-wired UI claims.
- Local-only proof could be overstated as deployed governance.

Required mitigation before approval:

- Explicit local-only server boundary.
- Release language that forbids production claims.
- Tests proving no production writes.

### Backend-Wired UI Implication

Adding a server near the static prototype could imply that the UI is backend-wired.

Risk:

- Static manual export/import boundary becomes unclear.
- Browser submission may be assumed even if not implemented.
- UI claims may outrun runtime evidence.

Required mitigation before approval:

- Separate browser submission decision.
- Explicit UI boundary document.
- Browser interaction tests only after submission is approved.

### Write-Boundary Complexity

Server routes can create hidden write paths.

Risk:

- Request handlers may write outside approved workspaces.
- Default output paths may reappear.
- Production ledgers or repo `data/` could become accidental targets.

Required mitigation before approval:

- Path classifier implemented and tested first.
- Output policy test matrix passing.
- Production JSONL fingerprint tests.
- No default output directories.

### Authority Model Complexity

Server-mediated actions require stronger authority decisions than local CLI commands.

Risk:

- Browser session identity may be confused with human authority.
- Generated output may self-certify through server routing.
- Review status may become ambiguous.

Required mitigation before approval:

- Local authority model test.
- Self-certification rejection test.
- Explicit session and reviewer marker policy.

### Authentication And Session Boundary

Even a local server needs a decision about access and session state.

Risk:

- Open local ports may accept unintended requests.
- Session state may act as hidden authority.
- Browser origin behavior may affect trust assumptions.

Required mitigation before approval:

- Explicit local-only network policy.
- Explicit authentication/session boundary.
- Explicit allowed origins if browser submission is later approved.

### Claim Inflation

Server behavior can make a local proof surface sound like an app release.

Risk:

- "Local server exists" becomes "production app exists."
- "Packet submission works locally" becomes "UI is governed."
- "Some paths are gated" becomes "all authoring is governed."

Required mitigation before approval:

- Safe claims document update.
- Release boundary update.
- Explicit non-production language in user-facing docs.

## Preconditions Before Local Server Work

Local server work should not start until these are complete:

- Command router implemented and tested.
- Path classification implemented and tested.
- Workspace validation tested.
- Output directory validation tested.
- Optional ledger path validation tested.
- Production JSONL fingerprint preservation tested.
- Authority marker behavior tested.
- Self-certification rejection tested.
- Server boundary document approved.
- Local-only network policy approved.
- Browser submission decision approved or explicitly deferred.
- Authentication/session boundary approved.

## Current Recommendation

Do not add a local server in Phase 26.

Phase 26 should implement the local command-router runtime foundation first.

## Safe Claim

Use:

```text
v0.2 defers local server work until command-router write boundaries, authority behavior, and no-production-write tests exist.
```

Do not use:

```text
v0.2 includes a local server.
```
