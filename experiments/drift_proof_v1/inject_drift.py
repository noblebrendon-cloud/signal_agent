import os
import time
import pandas as pd
import numpy as np
import random
from transformers import pipeline
from datasets import load_dataset
from scipy.stats import entropy
from sklearn.metrics import accuracy_score
import matplotlib.pyplot as plt

# Ensure deterministic randomness for proof reproducibility
random.seed(42)
np.random.seed(42)

def inject_noise(text: str, severity: float = 0.2) -> str:
    """Vocabulary perturbation: Randomly swap characters to simulate input noise/typos."""
    words = text.split()
    drifted_words = []
    for word in words:
        if len(word) > 4 and random.random() < severity:
            idx = random.randint(1, len(word) - 2)
            word = word[:idx] + word[idx+1] + word[idx] + word[idx+2:]
        drifted_words.append(word)
    return " ".join(drifted_words)

def main():
    print("Loading model and dataset...")
    # Use the exact hash for lock
    model_name = "distilbert-base-uncased-finetuned-sst-2-english"
    revision = "af0f99bfd02f5a65c9eecd67fec0463ec18228aa"
    
    classifier = pipeline("text-classification", model=model_name, revision=revision, top_k=None)
    
    # Load SST2 validation set (take a small deterministic slice for speed, e.g., 200 samples)
    dataset = load_dataset("glue", "sst2", split="validation[:200]")
    
    clean_texts = dataset["sentence"]
    labels = dataset["label"]
    
    print("Generating drifted dataset...")
    # 20% typo severity
    drifted_texts = [inject_noise(t, severity=0.3) for t in clean_texts]

    print("Running baseline inference...")
    baseline_preds = classifier(clean_texts)
    
    print("Running drifted inference...")
    drifted_preds = classifier(drifted_texts)
    
    # Extract prob for class 1 (POSITIVE) for distribution comparison
    def get_pos_prob(preds_list):
        probs = []
        for preds in preds_list:
            for p in preds:
                if p["label"] == "POSITIVE":
                    probs.append(p["score"])
        return np.array(probs)

    def get_pred_label(preds_list):
        out = []
        for preds in preds_list:
            # First item in sorted by default? Pipeline with top_k=None returns list of dicts.
            # We must find the max score manually or just rely on dict.
            best = max(preds, key=lambda x: x["score"])
            out.append(1 if best["label"] == "POSITIVE" else 0)
        return np.array(out)
        
    p_baseline = get_pos_prob(baseline_preds)
    p_drifted = get_pos_prob(drifted_preds)
    
    y_baseline = get_pred_label(baseline_preds)
    y_drifted = get_pred_label(drifted_preds)
    
    acc_baseline = accuracy_score(labels, y_baseline)
    acc_drifted = accuracy_score(labels, y_drifted)
    
    # Calculate Phi 1: KL Divergence.
    # We bin the probabilities into deciles to compare distributions.
    bins = np.linspace(0, 1, 11)
    hist_base, _ = np.histogram(p_baseline, bins=bins, density=True)
    hist_drift, _ = np.histogram(p_drifted, bins=bins, density=True)
    
    # add epsilon to avoid div zero
    epsilon = 1e-5
    hist_base = hist_base + epsilon
    hist_drift = hist_drift + epsilon
    # normalize
    hist_base /= hist_base.sum()
    hist_drift /= hist_drift.sum()
    
    phi1_kl = entropy(hist_drift, hist_base) # D_KL(Drift || Base)
    
    # Calculate Phi 2: Performance Drop
    phi2_drop = acc_baseline - acc_drifted
    
    print(f"Baseline Accuracy: {acc_baseline:.3f}")
    print(f"Drifted Accuracy:  {acc_drifted:.3f}")
    print(f"Phi 1 (KL Div):    {phi1_kl:.4f}")
    print(f"Phi 2 (Acc Drop):  {phi2_drop:.4f}")
    
    # Save CSV
    records = [
        {
            "timestamp": time.time(),
            "dataset_state": "baseline",
            "phi1_divergence": 0.0,
            "phi2_degradation": 0.0,
            "accuracy": acc_baseline,
            "notes": "Clean SST-2 validation set"
        },
        {
            "timestamp": time.time() + 1,
            "dataset_state": "drifted",
            "phi1_divergence": phi1_kl,
            "phi2_degradation": phi2_drop,
            "accuracy": acc_drifted,
            "notes": "30% random character swap drift"
        }
    ]
    df = pd.DataFrame(records)
    csv_path = os.path.join(os.path.dirname(__file__), "drift_metrics.csv")
    df.to_csv(csv_path, index=False)
    print(f"Saved metrics to {csv_path}")

    # Generate Graphs
    fig_path1 = os.path.join(os.path.dirname(__file__), "phi1_divergence.png")
    fig_path2 = os.path.join(os.path.dirname(__file__), "phi2_accuracy.png")
    
    # Graph 1: Distribution Before/After
    plt.figure(figsize=(6, 4))
    plt.plot(bins[:-1], hist_base, marker='o', label='Baseline Dist', color='blue')
    plt.plot(bins[:-1], hist_drift, marker='x', label='Drifted Dist', color='red')
    plt.title(f"Phi 1: Probability Shift (KL={phi1_kl:.3f})")
    plt.xlabel("Confidence (Positive)")
    plt.ylabel("Frequency")
    plt.legend()
    plt.tight_layout()
    plt.savefig(fig_path1)
    
    # Graph 2: Bar chart for Accuracy
    plt.figure(figsize=(5, 4))
    plt.bar(["Baseline", "Drifted"], [acc_baseline, acc_drifted], color=["blue", "red"])
    plt.title(f"Phi 2: Accuracy Drop (-{phi2_drop*100:.1f}%)")
    plt.ylabel("Accuracy")
    plt.ylim(0, 1.0)
    plt.tight_layout()
    plt.savefig(fig_path2)
    
    print("Saved graphs. Complete.")

if __name__ == "__main__":
    main()
