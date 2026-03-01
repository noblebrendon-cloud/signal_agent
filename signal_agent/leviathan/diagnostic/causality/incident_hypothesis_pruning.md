# Incident Hypothesis Pruning Checklist

This checklist enforces epistemic hygiene during incident response by capping parallel investigations and demanding falsifiable mechanisms.

## Initialization
- [ ] **Initialize causal ledger entry** for the current `incident_id`.
- [ ] **List between 2 to 5 hypotheses strictly** (hard cap).

## Hypothesis Qualification (Pre-Debate)
For each hypothesis being debated, ensure the following are documented:
- [ ] **Mechanism**: Explicitly define *how* the `cause_candidate` leads to the observed `trigger`. No correlation without mechanism.
- [ ] **Counterfactual**: Explicitly define what test or missing evidence would cleanly falsify the hypothesis.

## Investigation & Testing
- [ ] **Enforce concurrency limit**: Maximum of **3** parallel investigations at any time.
- [ ] **Prioritize tests**:
    - [ ] Run the **discriminating tests** first (those with the highest information gain that can falsify competing hypotheses).
    - [ ] Prioritize hypotheses with the strongest mechanism clarity.
    - [ ] Prioritize hypotheses with the fastest discriminating counterfactual.
    - [ ] Prioritize hypotheses that explain multiple signals coherently.

## Pruning & Resolution
- [ ] **Prune aggressively**: Strike out hypotheses where counterfactuals hold true.
- [ ] **Update ledger**: Keep the continuous causal ledger updated with discarded paths and newly gathered evidence.
- [ ] **Resolve with clarity**: Upon incident resolution, explicitly document:
    - the true root change
    - the validated mechanism
    - the structural prevention measure
