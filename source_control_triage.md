# Source Control Triage

## Repository State

- Repository: `E:/signal_agent`
- Current branch: `main`
- Upstream: `origin/main`
- Outgoing commits: yes, `main` is ahead of `origin/main` by 84 commits
- Incoming commits: none observed from `git rev-list --left-right --count '@{u}...HEAD'` (`0 84`)
- Initial changed state: 41 tracked modified files and 1,621 untracked files before new ignore rules

## KEEP_IN_GIT

Tracked modified source, docs, specs, config, and tests:

- `ARCHITECTURE.md`
- `app/agent.py`
- `app/agents/social_offload/social_offload.py`
- `app/audit/runtime_audit.py`
- `app/audit/task_contract.py`
- `app/bookgen/cli.py`
- `app/bookgen/render.py`
- `app/bookgen/templates/book.md.j2`
- `app/bookgen/templates/cover_front.txt.j2`
- `app/bookgen/typeset.py`
- `app/letters_of_light/weekly_render.py`
- `app/pipeline/contract_evaluator.py`
- `app/retention/cli.py`
- `books/projects/communication_architecture/book_project.yaml`
- `books/specs/communication_architecture.yaml`
- `config/spine_router.yaml`
- `data/INDEX_ARTIFACTS.md`
- `laviathon/LEGACY.md`
- `laviathon/labs/simulator/README_viewer_notes.md`
- `laviathon/labs/simulator/index.html`
- `laviathon/labs/simulator/substack_release_post.md`
- `signal_agent/core/clock/clock.py`
- `signal_agent/formal_governance/__init__.py`
- `signal_agent/leviathan/cli/leviathan_cli.py`
- `signal_agent/leviathan/diagnostic/stability_snapshot/cli.py`
- `signal_agent/leviathan/diagnostic/stability_snapshot/policy.py`
- `signal_agent/leviathan/interaction_signals/README.md`
- `signal_agent/leviathan/interaction_signals/cli/repro_report.py`
- `site_laviathon/LEGACY.md`
- `site_laviathon/labs/simulator/README_viewer_notes.md`
- `site_laviathon/labs/simulator/index.html`
- `site_laviathon/labs/simulator/substack_release_post.md`
- `tests/test_bookgen_project_compile.py`
- `tests/test_bookgen_render.py`
- `tests/test_clock_loop.py`
- `tests/test_contract_evaluator.py`
- `tests/test_letters_of_light_weekly_render.py`
- `tests/test_leviathan_clock_governance.py`
- `tests/test_task_contract_runtime.py`

Untracked source, docs, specs, architecture files, scripts, tests, examples, and assets that look appropriate to keep after review:

- Root docs/specs: `.env.example`, `CANONICAL_DIRS.txt`, `GOVERNANCE_KERNEL.md`, `IMPLEMENTATION_RECEIPT.md`, `MARKET_ENTRY_ANALYSIS.md`, `RELEASE_READINESS.md`, `SYSTEM_RESEARCH_BRIEF.md`
- Root scripts/tests/config: `build_spec.py`, `dump_docs.py`, `parse_out.py`, `pyproject.toml`, `scaffold_cfs.py`, `test_adaptive_loop.py`
- Application source: `app/audit/`, `app/bookgen/`, `app/letters_of_light/`, `app/retention/`, `app/social_orchestration/`, `app/sovereign_contribution/`
- Web/app source: `apps/laviathon-api/`, `apps/laviathon-docs/`, `apps/laviathon-labs/`, `apps/laviathon-web/`
- Book/source assets and specs: `assets/`, `books/book covers/`, `books/projects/communication_architecture/assets/`, `books/specs/dust_quietly.yaml`
- Config/specs: `config/integrations/shopify.yaml`, `config/operator/`, `config/policies/context_assembly_policy.yaml`, `config/policies/inference_cache_policy.yaml`, `constraints/packs/domain/wtpu_pack.yaml`
- Docs and examples: `docs/`, `examples/`, `marketing/`, `migration_reports/`
- Source packages/modules: `formal_governance/`, `leviathan/`, `orchestration_core/`, `products/governed_authoring_studio/`, `security/`, `services/`, `shared/`, `signal_agent/`, `surfaces/`
- Scripts and tools: `scripts/`, `tools/`
- Site source: `sites/`
- Tests: `tests/drift_audit/`, `tests/memory/`, `tests/security/`, `tests/test_*.py`, `tests/live_probe_append_only.py`, `tests/validate_governance.py`

## IGNORE

Generated outputs, dumps, build artifacts, caches, logs, temporary files, and local runtime state now covered by `.gitignore`:

- `artifacts/`
- `outbound/`
- `reviews/`
- `books/out/`
- `data/claims/`
- `data/docs/processed/`
- `data/graph/`
- `data/operator/`
- `data/outputs/`
- `data/platform/`
- `data/validation/`
- `data/intake/text/*.pdf`
- `orchestration_core/execution_log.jsonl`
- `signal_agent/leviathan/diagnostic/causality/ledger/*.jsonl`
- `signal_agent/runtime/processed/`
- `tests/.probe_workspace/`
- `tmp_route_debug/`
- `tmp_probe.ps1`
- `tmp_test_output.txt`
- `tests_output*.txt`
- `probe_output.txt`
- `parse_results.txt`
- `test_simple.txt`
- `docx_dump.json`
- `out*.json`
- `*.egg-info/`
- `~$*`
- `data/**/*.lock`
- `*.jsonl.lock`

Already-covered generated/local rules in the existing `.gitignore` include Python caches, `.pytest_cache/`, virtual environments, logs, runtime capture output, `data/state/`, and real `.env` files.

## NEVER_COMMIT

Secret-bearing or private local files/data:

- `.env`
- `.env.*` except `.env.example`
- `config/integrations/shopify_crawler.yaml`
- `config/integrations/printful.yaml`
- `config/integrations/*.secret.yaml`
- `config/secrets/`
- `data/reddit/` because it contains private local account export data including identity, message, IP, and preference CSVs
- `mcp-chatbot/servers_config.json` until manually verified, because it is local tool/server configuration inside a nested checkout

## REVIEW_MANUALLY

Ambiguous paths that should not be staged without a deliberate decision:

- `data/artifact_registry.jsonl` and `data/intake/intake.jsonl`: tracked runtime/data ledgers with local modifications
- `data/intake/text/2026-03-16__concept__human_intent_traceability_stack.md`: local intake source text; decide whether it is project source or private input data
- `mcp-chatbot/`: nested Git repository with its own `.git`, `.venv`, and local server config; decide whether it should be a submodule, vendored source, or ignored local checkout
- `site_refactor_working/`: working site refactor tree; decide whether to promote into `sites/` or ignore as scratch
- `migration_reports/`: useful docs/reports, but includes a generated JSON inventory; stage intentionally if these are desired history
- `books/book covers/` and `books/projects/communication_architecture/assets/`: likely source assets, but confirm large PNGs should live in Git

## Suggested Next Git Commands

Immediate verification after this triage:

```powershell
git status --short
git diff --cached
git diff --cached -- .gitignore source_control_triage.md
```

If the staged triage files look correct, keep them staged and then review the remaining source changes by area:

```powershell
git diff --stat
git diff -- app signal_agent tests docs config books
git status --short --ignored
```

When ready to stage keep-worthy work, use explicit path groups rather than `git add .`:

```powershell
git add ARCHITECTURE.md GOVERNANCE_KERNEL.md IMPLEMENTATION_RECEIPT.md MARKET_ENTRY_ANALYSIS.md RELEASE_READINESS.md SYSTEM_RESEARCH_BRIEF.md CANONICAL_DIRS.txt pyproject.toml
git add app/audit app/bookgen app/letters_of_light app/retention app/social_orchestration app/sovereign_contribution
git add apps/laviathon-api apps/laviathon-docs apps/laviathon-labs apps/laviathon-web
git add config/spine_router.yaml config/integrations/shopify.yaml config/operator config/policies/context_assembly_policy.yaml config/policies/inference_cache_policy.yaml constraints/packs/domain/wtpu_pack.yaml
git add docs examples formal_governance leviathan marketing migration_reports products/governed_authoring_studio security services shared signal_agent surfaces scripts tools
git add books/projects/communication_architecture books/specs "books/book covers"
git add sites
git add tests/drift_audit tests/memory tests/security tests/live_probe_append_only.py tests/test_*.py tests/validate_governance.py
```

Hold these until manual review is complete:

```powershell
git status --short -- data/artifact_registry.jsonl data/intake/intake.jsonl data/intake/text mcp-chatbot site_refactor_working
```
