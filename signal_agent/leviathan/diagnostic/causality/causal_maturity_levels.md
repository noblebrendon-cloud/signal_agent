# Causal Maturity Levels

Use the following rubric to assess organizational maturity in capturing causality as a first-class artifact.

## Evaluation Questions
1. Do you externalize causal interpretation, or only telemetry?
2. Can two teams produce the same root cause story from the same evidence?
3. Is there a cap on concurrent hypotheses during incidents?
4. Are mechanisms and counterfactuals enforced as required fields before taking action?
5. Do postmortems update a living causal knowledge base rather than gathering dust?

## Scoring Levels

### **L0: Anecdotal Response**
- **Characteristics**: No causal artifacts exist. 
- **Incident Behaviour**: Telemetry is shared but interpretation is entirely oral. Post-hoc narratives are written to close out tickets. The loudest signal or highest rank in the room dictates the assumed cause.

### **L1: Ritual Postmortems**
- **Characteristics**: Postmortems exist but are retroactive.
- **Incident Behaviour**: No structured hypothesis tracking during active fires. Explanations compete informally. Causal claims are often just the name of the highest spiking alert.

### **L2: Spasmodic Tracking**
- **Characteristics**: Incident hypothesis tracking exists (e.g., shared docs) but is not continuous in peacetime.
- **Incident Behaviour**: Checklists or tables are used to track hypotheses, but mechanism and counterfactual columns are frequently left blank. Telemetry correlation stands in for mechanistic cause.

### **L3: Epistemic Externalization**
- **Characteristics**: The causal ledger is continuous, versioned, and referenced in day-to-day changes.
- **Incident Behaviour**: Explanations do not advance without documented mechanisms. Causal artifacts accompany telemetry dashboards.

### **L4: Rigorous Pruning**
- **Characteristics**: Discriminating tests determine action. Hard caps on active hypotheses.
- **Incident Behaviour**: Strict concurrency limits (`max_active_hypotheses: 5`, `max_parallel_investigations: 3`). Teams automatically detect and report "causal drift" across divisions interpreting the same telemetry differently.
