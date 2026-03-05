# Causal Drift Index

## Metric Overview
The **Causal Drift Index (CDI)** measures the degree of divergence in causal interpretation between different individuals or teams while observing the exact same telemetry or incident symptoms.

**Problem Statement**: Teams can share dashboards and still diverge because telemetry encodes symptoms, not agreed causal interpretation. If the CDI is high, the true incident surface is the mismatch in epistemic models, not missing observability data.

## Calculation Components
To quantify CDI during an incident or post-incident review, measure the disparity in hypothesis ledgers across participating groups:

**1. Number of Distinct Root Cause Candidates (C)**
- How many unique fundamental changes or events are proposed as the origin across all teams?
- *Ideal component score:* 1 (All teams agree on the candidate space).

**2. Mechanism Variance (M)**
- Given the exact same `trigger`, what percentage of proposed `mechanisms` conflict physically or logically?
- *Ideal component score:* 0%.

**3. Counterfactual Absence Rate (A)**
- The ratio of active hypotheses across teams lacking a stated falsification condition (counterfactual).
- *Ideal component score:* 0.0.

## Diagnostic Value
A continuously high Causal Drift Index indicates that the system architecture has exceeded the mental models of its operators. The fastest path to reduction is explicitly mandating completion of the **Causal Ledger** (mechanism + counterfactual) prior to debate.
