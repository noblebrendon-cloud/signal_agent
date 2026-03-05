"""
Diagnostic Specification for the AI Stability Snapshot.
Pure data structures defining the 15-question evaluation rubric,
scoring mechanics, and interpretation thresholds.
"""

QUESTIONS = [
    {
        "id": "q1",
        "text": "Are your workflows documented end-to-end?",
        "expected": True
    },
    {
        "id": "q2",
        "text": "Does one person hold critical process knowledge?",
        "expected": False
    },
    {
        "id": "q3",
        "text": "Are AI outputs reviewed by a defined owner?",
        "expected": True
    },
    {
        "id": "q4",
        "text": "Do you have version control on shared documents?",
        "expected": True
    },
    {
        "id": "q5",
        "text": "Can you map where your operational data lives?",
        "expected": True
    },
    {
        "id": "q6",
        "text": "Are multiple AI tools solving overlapping problems?",
        "expected": False
    },
    {
        "id": "q7",
        "text": "Do you track automation errors or failures?",
        "expected": True
    },
    {
        "id": "q8",
        "text": "Is there a rollback plan if automation fails?",
        "expected": True
    },
    {
        "id": "q9",
        "text": "Has AI reduced workload or only shifted it?",
        "expected": True  # Assuming 'Yes' means it has reduced workload
    },
    {
        "id": "q10",
        "text": "Do you know what would break first if usage doubled tomorrow?",
        "expected": True  # Adapted from "If usage doubled tomorrow, what would break first?"
    },
    {
        "id": "q11",
        "text": "Do you externalize causal interpretation, or only telemetry?",
        "expected": True  # Assuming Yes means externalizing causal interpretation
    },
    {
        "id": "q12",
        "text": "Can two teams produce the same root cause story from the same evidence?",
        "expected": True
    },
    {
        "id": "q13",
        "text": "Is there a cap on concurrent hypotheses during incidents?",
        "expected": True
    },
    {
        "id": "q14",
        "text": "Are mechanisms and counterfactuals enforced as required fields before taking action?",
        "expected": True
    },
    {
        "id": "q15",
        "text": "Do postmortems update a living causal knowledge base rather than gathering dust?",
        "expected": True
    }
]

MAX_SCORE = len(QUESTIONS)

# Invariant bands synced from invariant_declaration.yaml
THRESHOLDS = [
    {"min_score": 13, "interpretation": "Stable causal and structural foundation", "band": "GREEN"},
    {"min_score": 9,  "interpretation": "Emerging causal drift or process documentation gaps", "band": "YELLOW"},
    {"min_score": 5,  "interpretation": "Significant epistemic decay and uncontrolled automation failures", "band": "ORANGE"},
    {"min_score": 0,  "interpretation": "Critical instability, loss of causal observability, and unbounded risk", "band": "RED"}
]
