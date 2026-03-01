# Metric Definition: Drift Proof v1

**Model Selected:** `distilbert-base-uncased-finetuned-sst-2-english` (HuggingFace)
**Dataset:** `sst2` (Stanford Sentiment Treebank v2 - Validation Split)

## Formal Metrics

**$\Phi_1$ (Distribution Divergence):**
Calculated using **Kullback-Leibler (KL) Divergence** (or Population Stability Index) between the baseline output probability distributions and the drifted probability distributions across the dataset.
- Captures the shift in model confidence and predicted class balances.
- Formula: $D_{KL}(P || Q) = \sum P(x) \ln\left(\frac{P(x)}{Q(x)}\right)$

**$\Phi_2$ (Performance Degradation Delta):**
Calculated as the absolute drop in **Accuracy**.
- Captures the direct downstream business impact of the drift on the model's primary task.
- Formula: $\Phi_2 = Accuracy_{baseline} - Accuracy_{drifted}$
