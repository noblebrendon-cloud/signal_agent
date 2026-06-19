# v0.2 Operator Source-Control Audit

Target branch:

```text
release/v0.2-local-authoring-surface at 322455d
```

## Missing Modules

The clean release branch is missing:

- `signal_agent/operator/intent.py`
- `signal_agent/operator/planner.py`
- `signal_agent/operator/registry.py`

These modules exist in the dirty main worktree only as untracked files.

## Main Worktree Status

Read-only inspection in the dirty main worktree showed:

```text
?? signal_agent/operator/intent.py
?? signal_agent/operator/planner.py
?? signal_agent/operator/registry.py
```

Tracked operator files in main:

```text
signal_agent/operator/chat.py
signal_agent/operator/runtime.py
```

The missing modules are not tracked in main.

## Ignore Status

`git check-ignore -v` returned no ignore rule for:

- `signal_agent/operator/intent.py`
- `signal_agent/operator/planner.py`
- `signal_agent/operator/registry.py`

The files are untracked and not ignored.

## Git History Status

Reachable history contains the operator canonical ledger linkage commit:

```text
161e9da Add operator canonical governed-transition ledger linkage
```

That commit added:

- `signal_agent/formal_governance/adapters.py`
- `signal_agent/operator/chat.py`
- `signal_agent/operator/runtime.py`
- `tests/test_operator_canonical_ledger_adapter.py`

It did not add:

- `signal_agent/operator/intent.py`
- `signal_agent/operator/planner.py`
- `signal_agent/operator/registry.py`

Direct history checks for the three missing module paths returned no commits.

Targeted stash checks for `signal_agent/operator` returned no matching files.

Conclusion:

```text
The missing modules do not exist in any reachable committed history or checked stash evidence found by this audit.
```

## Committed Imports Requiring The Modules

On the clean release branch, committed files import the missing modules:

```text
signal_agent/operator/runtime.py: from .planner import OperatorPlan
signal_agent/operator/runtime.py: from .registry import OperatorRegistry
signal_agent/operator/runtime.py: from .planner import PlanStep
signal_agent/operator/runtime.py: from .intent import ParsedIntent
signal_agent/operator/chat.py: from .intent import IntentParser
signal_agent/operator/chat.py: from .planner import OperatorPlanner
signal_agent/operator/chat.py: from .registry import OperatorRegistry
tests/test_operator_canonical_ledger_adapter.py: from signal_agent.operator.intent import IntentParser, ParsedIntent
tests/test_operator_canonical_ledger_adapter.py: from signal_agent.operator.planner import OperatorPlan, OperatorPlanner, PlanStep
tests/test_operator_canonical_ledger_adapter.py: from signal_agent.operator.registry import OperatorRegistry, ToolDefinition, WorkflowDefinition
```

The committed operator adapter test is therefore not self-contained on a clean checkout.

## Untracked Module Shape

The dirty main worktree contains real source-shaped modules:

| File | Approximate role | Size |
| --- | --- | ---: |
| `signal_agent/operator/intent.py` | Intent parser and `ParsedIntent` dataclass | 16219 bytes |
| `signal_agent/operator/planner.py` | Operator plan dataclasses and planner | 3167 bytes |
| `signal_agent/operator/registry.py` | Operator registry YAML loader and definitions | 7378 bytes |

Observed definitions include:

- `ParsedIntent`
- `IntentParser`
- `PlanStep`
- `OperatorPlan`
- `OperatorPlanner`
- `IntentDefinition`
- `ToolDefinition`
- `WorkflowStepDefinition`
- `WorkflowDefinition`
- `OperatorRegistry`
- `normalize_text`

These files look like required runtime source, not generated output or disposable local artifacts.

## Required Runtime Status

The modules are required by committed runtime files:

- `signal_agent/operator/chat.py`
- `signal_agent/operator/runtime.py`

They are also required by the committed test:

- `tests/test_operator_canonical_ledger_adapter.py`

Because the runtime imports them directly, test collection cannot be made valid without either:

- committing the runtime modules, or
- changing/removing the committed runtime and test surface.

Changing the test to avoid the imports would weaken the advertised operator proof surface unless the test is first proven obsolete or unrelated.

## Source-Control Completeness Finding

The release branch is not source-control complete for the committed operator proof surface.

Do not tag a release that depends on untracked local operator modules.

The correct next step is an audited source-control repair, not a local copy into the release branch and not a test skip.
