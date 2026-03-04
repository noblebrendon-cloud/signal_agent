import unittest
from signal_agent.leviathan.diagnostic.stability_snapshot.engine import compute_snapshot
from signal_agent.leviathan.diagnostic.stability_snapshot.spec import QUESTIONS

class TestSnapshotEngine(unittest.TestCase):
    
    def test_perfect_score(self):
        """Test that matching all expected answers yields max score and stable interpretation."""
        answers = [q["expected"] for q in QUESTIONS]
        result = compute_snapshot(answers)
        
        self.assertEqual(result["score"], 15)
        self.assertEqual(result["max_score"], 15)
        self.assertEqual(result["interpretation"], "Stable causal and structural foundation")
        self.assertEqual(len(result["answers"]), 15)
        
        for ans in result["answers"]:
            self.assertEqual(ans["points"], 1)

    def test_zero_score(self):
        """Test that missing all expected answers yields 0 and high risk."""
        answers = [not q["expected"] for q in QUESTIONS]
        result = compute_snapshot(answers)
        
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["interpretation"], "Critical instability, loss of causal observability, and unbounded risk")
        
        for ans in result["answers"]:
            self.assertEqual(ans["points"], 0)
            
    def test_moderate_score(self):
        """Test a border case around moderate threshold."""
        answers = [q["expected"] for q in QUESTIONS]
        # Invert the first 9 answers to get score 15 - 9 = 6 (Moderate risk starts at 6)
        for i in range(9):
            answers[i] = not answers[i]
            
        result = compute_snapshot(answers)
        self.assertEqual(result["score"], 6)
        self.assertEqual(result["interpretation"], "Significant epistemic decay and uncontrolled automation failures")
        
    def test_invalid_length_rejected(self):
        """Test that giving fewer or more than 15 answers throws ValueError."""
        with self.assertRaises(ValueError):
            compute_snapshot([True] * 14)
            
        with self.assertRaises(ValueError):
            compute_snapshot([True] * 16)

if __name__ == '__main__':
    unittest.main()
