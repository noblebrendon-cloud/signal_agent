# Product Demo Script: $7K Drift Diagnostic

## 1. Problem Framing (5 minutes)
*Goal: Establish the pain of silent failure.*
- "Thanks for taking the time to chat. We focus on one specific problem: Silent AI Failure."
- "You know the scenario. The API is returning 200 OK, latency is fine, but the actual intelligence of the model is eroding. Prompts decay, data distributions shift, and what was 95% accurate on day one is now 82% accurate."
- "The problem is, you don’t find out until a transaction hard-fails or a customer complains. It's an un-metered revenue leak."

## 2. Show Simulated Drift Proof (10 minutes)
*Goal: Prove that we have the deterministic solution using Phase 1 evidence.*
- **Screen Share:** Show `drift_proof_report_v1.pdf`.
- "We ran a baseline on a standard production model. When we intentionally injected a 30% organic input decay (typos, OCR shifts), here is what happened."
- "Look at this Distribution Divergence Graph ($Φ_1$). This is the model’s internal confidence probability shifting left. It's becoming uncertain."
- "Now look at the Accuracy Correlation ($Φ_2$). Accuracy dropped from 91% down to 78%. An immediate 12.5% direct failure surge."
- "The key takeaway: **$Φ_1$ (Confidence Drift) happens BEFORE $Φ_2$ (Accuracy Drop).** If you measure $Φ_1$, you can circuit-break the failure before it hits the user."

## 3. ROI Plug-In (5 minutes)
*Goal: Monetize the problem using the prospect's numbers.*
- **Screen Share:** Pull up `ROI_CALCULATOR.xlsx`.
- "Let's plug your numbers in. What's your average QPS? Let's say 50."
- "If you experience a 5% silent retry/failure rate, based on industry averages of $250/minute for defective AI execution, you are leaking [calculate] annually."
- "If we can cut that instability duration by just 20% through early halting, you save [calculate] immediately."

## 4. What the Audit Delivers (5 minutes)
*Goal: Explain the fixed, low-risk offer.*
- "Here is what we do. We don't want a massive enterprise integration. We do a focused, 5-to-7 day diagnostic specifically on your Tier-1 endpoint."
- "We run the scan. If there is no drift, you're clear."
- "If there is drift, you receive a full Distribution Divergence Graph ($Φ_1$), the Accuracy Correlation Analysis ($Φ_2$), and a 3-step Deterministic Remediation Brief telling your engineering team exactly what hysteresis loop or threshold to tune."

## 5. The Close 
*Goal: Secure the $7K commitment conditionally.*
- "It is a $7,000 flat fee. We do not invoice you until the final Drift Proof report reaches your desk and the analysis is conclusive."
- "If this is valuable to you, we can get the script running locally on your infrastructure by tomorrow morning. Are you open to moving forward?"
