# Verify System Stabilization Report

## Summary

`tools/verify_system.py` was stabilized without changing `app/retention` runtime behavior.

The final verifier result is:

- `E:\signal_agent\.venv\Scripts\python.exe tools/verify_system.py` -> `passed`

## Root Cause: `pypdf` Failure

The original verifier treated `pypdf` as a hard repo-wide import requirement:

- `tools/verify_system.py` imported `from pypdf import PdfReader`

That failed in the repo venv because `pypdf` is not installed there.

After inspection, `pypdf` is **not** part of the active PDF extraction runtime path:

- `app/intake/extract_pdf_text.py` uses `pdfminer.six`
- `app/intake/intake.py` lazy-loads extractor dependencies by file type
- there was no active runtime import path that required `pypdf`

The same pattern applied to other format-specific extractor dependencies:

- `ebooklib`
- `bs4`

### Resolution

`pypdf` was **isolated as optional** in `tools/verify_system.py` rather than added to runtime-critical verification.

What changed:

- required import probe now checks only core verifier dependencies
- optional extractor dependencies are reported deterministically via `OPTIONAL_IMPORT_STATUS`
- missing optional extractor packages no longer fail the whole verifier

`environment/requirements.lock` was **not** changed. It already documents `pypdf`, but the verifier no longer treats it as a hard requirement for repo-wide verification.

## Root Cause: Provider Assertion Mismatch

The original verifier expected:

- `[ok:gemini-3-pro]`

The observed runtime output was:

- `[ok:google:gemini-3-pro] test`

After inspection, the observed output is canonical:

- `app/agent.py` keys models as fully qualified `provider:model`
- `AgentConfig.models` contains `google:gemini-3-pro-high`, `google:gemini-3-pro`, `google:gemini-3-flash`
- `StubProvider.call()` returns `[ok:{model}] ...`

So the verifier expectation was stale, not the runtime output.

### Resolution

The **expected behavior** in `tools/verify_system.py` was changed.

What changed:

- the fallback probe now derives the expected fallback key from `SignalAgent().config.models[1]`
- the verifier now asserts against the canonical fully qualified provider identity instead of the stale unqualified string

Runtime provider semantics were **not** changed.

## Additional Verifier Stabilization

One more pre-existing verifier issue surfaced after the import and provider fixes:

- `tools/verify_system.py` launched curation as `python app/hq/curation/curate.py ...`
- that execution style broke `from app...` imports because it did not preserve the repo root as the import base

### Resolution

The verifier now launches curation as:

- `python -m app.hq.curation.curate ...`

The curation regression sub-checks also now pass `--no-governor` so they test curation behavior itself rather than failing against the live Activation Governor drift lock state.

This did not change curation runtime behavior. It only corrected the verifier harness.

## Files Changed

- `tools/verify_system.py`
- `tests/test_agent_resilience.py`
- `docs/operator/verify_system_stabilization_report.md`
- `docs/operator/retention_module_registration_report.md`

## Exact Verification Commands Run

```powershell
E:\signal_agent\.venv\Scripts\python.exe -m pytest tests/test_agent_resilience.py -q
E:\signal_agent\.venv\Scripts\python.exe -m pytest tests/test_retention_cli.py -q
E:\signal_agent\.venv\Scripts\python.exe -m pytest tests/test_retention_reconcile.py -q
E:\signal_agent\.venv\Scripts\python.exe -m pytest tests/test_retention_dispatch_gate.py -q
E:\signal_agent\.venv\Scripts\python.exe -m pytest tests/test_retention_send_queue.py -q
E:\signal_agent\.venv\Scripts\python.exe -m pytest tests/test_retention_sender_contract.py -q
E:\signal_agent\.venv\Scripts\python.exe -m pytest tests/test_retention_authorization.py -q
E:\signal_agent\.venv\Scripts\python.exe tools/verify_system.py
```

## Verification Results

- `tests/test_agent_resilience.py`: `2 passed`
- `tests/test_retention_cli.py`: `18 passed`
- `tests/test_retention_reconcile.py`: `6 passed`
- `tests/test_retention_dispatch_gate.py`: `11 passed`
- `tests/test_retention_send_queue.py`: `8 passed`
- `tests/test_retention_sender_contract.py`: `10 passed`
- `tests/test_retention_authorization.py`: `12 passed`
- `tools/verify_system.py`: `passed`

## Retention Confirmation

`app/retention` runtime behavior was not changed.

No retention ledgers were mutated by this stabilization pass.
