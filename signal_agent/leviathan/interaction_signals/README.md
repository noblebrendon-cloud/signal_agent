# Interaction Signals v0.1 – v0.5

**Status**: `CLOSED_LOOP_CONTROLLER`

Deterministic conversation behaviour classifier with Lyapunov stability scalar.

Interaction Signals is descriptive at the feature layer and prescriptive at the policy layer.
No prediction or learning occurs; behaviour emerges from deterministic state evolution and control policy.

## Signal modes

| Mode | Meaning |
|---|---|
| `PERFORMANCE` | Assertion, positioning, or presentation posture |
| `TRANSACTION` | Extraction, promotion, or leverage-seeking |
| `COGNITIVE_HONESTY` | Inquiry, repair, uncertainty handling |
| `MIXED` | No dominant behavioural signal |

Shipping/evidence reduces V(t) through state updates, not by mode label alone.

## Lyapunov V(t)

`V ∈ [0,1]`. High V = conversation at risk of divergence/pressure. Low V = stable.

`V = 0.6 · L_actor + 0.4 · L_thread`

- **L_actor**: 1-trust, extraction pressure, mode volatility, evasion, spread
- **L_thread**: coordination cost, convergence deficit, disagreement productivity, artifact gap

### Stability interpretation

Let ΔV(t) = V(t+1) − V(t)

| Condition | Interpretation |
|---|---|
| ΔV < 0 | Interaction stabilising (coherence increasing) |
| ΔV ≈ 0 | Neutral / informational exchange |
| ΔV > 0 | Divergence or coordination risk increasing |

Policy decisions attempt to select actions expected to minimise ΔV.

## Quick start

```powershell
# From repo root
$env:PYTHONPATH = "e:\signal_agent"

# Run demo stream
python -m signal_agent.leviathan.interaction_signals.cli.run_stream

# Custom JSONL events
python -m signal_agent.leviathan.interaction_signals.cli.run_stream --input events.jsonl --ledger out.jsonl

# Run tests (65 tests)
python -m unittest discover -s signal_agent/leviathan/interaction_signals/tests -p "test_*.py" -v
```

## Programmatic API (engine.py)

```python
from signal_agent.leviathan.interaction_signals.core.engine import StateStore, process_event
from signal_agent.leviathan.interaction_signals.core.types import Event

store = StateStore()
event = Event("e1", "alice", "thread1", "2026-02-28T18:00:00Z", "Book a call! Sign up.")
result = process_event(event, store, ledger_path=None)

print(result.mode, result.V, result.alert)
```

## OIL incident bridge

```python
from signal_agent.leviathan.interaction_signals.oil_bridge import events_from_artifacts_dir
from signal_agent.leviathan.interaction_signals.core.engine import StateStore, process_event
from pathlib import Path

store  = StateStore()
events = events_from_artifacts_dir(Path("oil/artifacts"), max_artifacts=50)
for ev in events:
    r = process_event(ev, store)
    if r.alert:
        print(f"ALERT {r.alert['kind']}: thread={r.event.thread_id} V={r.V:.4f}")
```

## File layout

```
core/
  types.py          dataclasses: Event, Features, Signal, ActorState, ThreadState
  ema.py            clamp01, ema, clamped_ema
  lexicons.py       curated word lists (10 lexicons)
  tokenize.py       regex tokenizer + sentence split
  features.py       23 deterministic features
  classify.py       softmax classifier + top-3 reasons
  state_update.py   EMA actor/thread state updates
  transitions.py    4x4 per-actor transition matrix
  lyapunov.py       V(t) scalar computation + delta
  ledger.py         append-only JSONL ledger
  engine.py         StateStore + process_event() API
  policy.py         Gating + posture policy governor
oil_bridge.py       OIL artifact → Event mapping
cli/run_stream.py   demo + JSONL stream runner
```

## State persistence

ActorState and ThreadState are intended to persist across runs.
Resetting state invalidates transition probabilities, entropy estimates,
and Lyapunov trend continuity.

Recommended deployment:
- periodic snapshot or KV persistence layer
- append-only ledger as recovery source of truth

## Policy Governor & Analytics (v0.2 – v0.5)

`core/policy.py` — pure function, no side effects. Runs automatically after every `process_event()` call.

```python
result = process_event(event, store)
action = result.policy_action   # PolicyAction, always set

# Fields
action.reply_depth        # "low" | "medium" | "high"
action.dm_gate            # bool — safe to move to DMs
action.off_platform_gate  # bool — safe to move off-platform
action.ask_for_artifact   # bool — request concrete evidence
action.pressure_protocol  # bool — enter de-escalation posture
action.notes              # list[str] — full audit trail
```

### CLI

```powershell
python -m signal_agent.leviathan.interaction_signals.cli.run_stream --emit-actions
python -m signal_agent.leviathan.interaction_signals.cli.run_stream --emit-actions --ledger out.jsonl
```

### Escalation invariant

DM or off-platform escalation is permitted only when:

- V(t) is below risk threshold, and
- recent ΔV ≤ 0, and
- flip-risk and cooldown gates are satisfied.

Escalation therefore follows demonstrated stability rather than perceived rapport.

### v0.3 stabilisers

**Cooldown / hysteresis** (`ActorState.cooldown_dm`, `cooldown_off` — int counters)
- Set to `max(current, 3/5)` by engine when `v_spike` or `pressure_protocol` fires
- Drained by 1 each event in `update_actor`; clamp ≥ 0
- Policy: if counter > 0 → gate stays locked + audit note added

**Adaptive flip-risk threshold** (replaces hard 0.35):
```
H_norm         = H(mode_histogram) / log(4)    ∈ [0, 1]
flip_threshold = 0.25 + 0.20 · H_norm          ∈ [0.25, 0.45]
```
### v0.4: Phase Space & Dyads
Adds `PhasePoint` mapping (T, Σ, V, Λ) and region sorting, plus track collaborative symmetry via `working_pair_score`. Run `run_stream --self-actor-id <actor>` to see dyads inline.

### v0.5: Post-Hoc Analytics
Adds `cli/summarize_ledger.py` for deterministic parsing of JSONL streams into transition metrics, flip-risks, and alerts timelines.
```powershell
python -m signal_agent.leviathan.interaction_signals.cli.summarize_ledger --ledger out.jsonl
```

Every ledger line includes `policy_action` for end-to-end auditability.
