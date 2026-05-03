# Governed Shell Invariants

## Core Invariants

1. The agent is proposal-only.
2. The governor is authoritative.
3. Unknown or malformed input fails closed.
4. Raw shell representations are not part of the proposal contract.
5. Execution must never start from an unsealed proposal.

## Contract Invariants

1. Proposal operations are explicit by `operation_type`.
2. `powershell_cmdlet` operations identify actions by `cmdlet_id` only.
3. `registered_script` operations identify actions by `script_id` only.
4. `registered_native` may exist structurally but is not admitted by the MVP boundary.
5. Proposal objects use `additionalProperties: false` wherever practical.

## Path Invariants

1. Proposal path inputs use `root_id + relative_path`.
2. Absolute paths are not allowed in proposal input.
3. Parent traversal using `..` is not allowed.
4. Proposal input must not carry already-resolved absolute execution paths.

## Raw Shell Rejection Invariants

1. `command_text` is forbidden.
2. `shell_text` is forbidden.
3. `script_text` is forbidden.
4. Inline PowerShell `-Command` is forbidden.
5. `Invoke-Expression` is forbidden.
6. `Start-Process` is forbidden.

## Risk Invariants

1. Model-declared risk is annotation only.
2. Model-declared risk is never authoritative.
3. Later policy/risk logic must recompute risk deterministically from the bound operation catalog.

## Phase 1 Invariants

1. No execution is implemented.
2. No simulation runtime is implemented.
3. No registered script execution is implemented.
4. No model connection is implemented.
5. No permissive fallback is introduced.
