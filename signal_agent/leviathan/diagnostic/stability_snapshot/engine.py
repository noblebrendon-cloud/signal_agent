"""
Snapshot Engine for evaluating the AI Stability Snapshot.
Deterministic, pure functions to score answers against the specification.
"""
from typing import List, Dict, Any
from .spec import QUESTIONS, MAX_SCORE
from .policy import THRESHOLDS

def compute_snapshot(answers: List[bool]) -> Dict[str, Any]:
    """
    Computes the stability snapshot score and interpretation deterministically.
    
    Args:
        answers: A list of exactly 15 boolean answers corresponding to the questions.
        
    Returns:
        dict: Deterministic dictionary mapping score, interpretation, and provided answers.
    """
    if len(answers) != MAX_SCORE:
        raise ValueError(f"Expected exactly {MAX_SCORE} answers, got {len(answers)}")
        
    score = 0
    structured_answers = []
    
    for i, answer in enumerate(answers):
        expected = QUESTIONS[i]["expected"]
        if answer is expected:
            score += 1
            
        structured_answers.append({
            "id": QUESTIONS[i]["id"],
            "answer": answer,
            "expected": expected,
            "points": 1 if answer is expected else 0
        })
        
    interpretation = "Unknown"
    for threshold in sorted(THRESHOLDS, key=lambda x: x["min_score"], reverse=True):
        if score >= threshold["min_score"]:
            interpretation = threshold["interpretation"]
            break
            
    # Deterministic dictionary returns
    return {
        "score": score,
        "max_score": MAX_SCORE,
        "interpretation": interpretation,
        "answers": structured_answers
    }
