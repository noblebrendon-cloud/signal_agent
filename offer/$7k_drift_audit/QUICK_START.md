# Drift Diagnostic Quick Start Guide

## Overview
This diagnostic captures and quantifies real-time AI drift (Φ1) and its corresponding precision decay (Φ2) within your production endpoints. By wrapping your model with the Signal Agent Coherence Kernel, you unlock deterministic monitoring of prediction distribution confidence without impacting standard logging flows.

## 1. Example Endpoint Wrapper

Below is the standard integration pattern for a PyTorch or external API endpoint:

```python
from signal_agent.kernel import DriftMonitorKernel

# 1. Initialize the Kernel (On-Prem / In-Memory only)
kernel = DriftMonitorKernel(
    phi_threshold_1=0.15, # Dist. Divergence limit
    phi_threshold_2=0.05  # Accuracy drop limit
)

@app.post("/predict")
async def predict_endpoint(request: PredictRequest):
    # A) Your standard model inference
    inputs = preprocess(request.data)
    outputs, probabilities = my_model(inputs)
    
    # B) Async Drift Snapshot
    # Tracks the probability distributions and flags threshold breaches
    kernel.snapshot_async(
        input_data=request.data,
        probabilities=probabilities,
        actual_performance=request.ground_truth if available else None
    )
    
    return {"prediction": outputs}
```

## 2. CLI Execution Command
To manually run a retrospective drift scan against a static CSV log of probabilities, use the following execution command:

```bash
v0.1-drift-audit scan --baseline data/clean_logs.csv --target data/recent_logs.csv --output audit_report.json
```

## 3. Output Example
```json
{
  "timestamp": "2026-02-23T14:02:00Z",
  "status": "UNSTABLE_REGIME",
  "metrics": {
    "phi1_divergence": 0.412,
    "phi2_degradation": 0.125
  },
  "action": "HALT_RECOMMENDED",
  "reason": "KL Divergence (Φ1) exceeded 0.15. Downstream task precision degraded by 12.5%."
}
```

## 4. Execution Time Estimate
- **Integration Time:** ~30 Minutes (Drop-in wrapper layer).
- **Scan Latency Impact:** < 2ms per request (Async evaluation).
- **Retrospective Log Scan:** ~45 Seconds for 1,000,000 rows.
