# Raspberry Pi Daily Witness Node Task Ledger

Status values: `proposed`, `blocked`, `in_progress`, `complete`

| task_id | task | status | evidence | next action |
|---|---|---|---|---|
| PI-WIT-001 | Inspect repo state and identify current witness surfaces | complete | `git status --short`, `git branch --show-current`, `git log --oneline -8`, targeted file listing | Keep work narrow because repo remains broadly dirty |
| PI-WIT-002 | Record project purpose, scope, and non-goals | complete | `docs/operator/pi_witness_node/PROJECT.md` | Review before staging |
| PI-WIT-003 | Record phased implementation plan | complete | `docs/operator/pi_witness_node/IMPLEMENTATION_PLAN.md` | Use as checklist for deployment branch work |
| PI-WIT-004 | Record branch and authority decisions | complete | `docs/operator/pi_witness_node/DECISION_LOG.md` | Do not push until explicitly approved |
| PI-WIT-005 | Add Pi manual witness wrapper script | complete | `scripts/run_pi_witness_check.sh`, `scripts/run_pi_witness_check.ps1` | Run focused static safety test |
| PI-WIT-006 | Add minimal project safety test | complete | `tests/test_pi_witness_project.py` | Run focused pytest command |
| PI-WIT-007 | Create narrow deployment branch from `origin/main` | proposed | Not executed | Operator approval required |
| PI-WIT-008 | Cherry-pick witness package onto deployment branch | proposed | Not executed | Operator approval required |
| PI-WIT-009 | Push deployment branch for Pi clone/pull | blocked | Push intentionally not performed | Wait for explicit push instruction |
| PI-WIT-010 | Run first manual Pi witness check | proposed | Not executed | Clone branch on Pi and run script manually |
| PI-WIT-011 | Record first Pi receipt | proposed | Not executed | Capture receipt path and result in operator notes |
| PI-WIT-012 | Decide whether scheduling is allowed later | blocked | Scheduling is out of scope for this phase | Require separate governance decision |
