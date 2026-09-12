from __future__ import annotations
from pathlib import Path
import json, time
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.metrics import classification_report, confusion_matrix, f1_score, accuracy_score, log_loss
from ml.config import LABELS


def evaluate_and_save(model, X, y, out_dir: Path, prefix: str):
    out_dir.mkdir(parents=True, exist_ok=True)
    pred = model.predict(X)
    prob = model.predict_proba(X)
    metrics = {
        "accuracy": float(accuracy_score(y, pred)),
        "macro_f1": float(f1_score(y, pred, average="macro")),
        "weighted_f1": float(f1_score(y, pred, average="weighted")),
        "log_loss": float(log_loss(y, prob, labels=list(range(len(LABELS))))),
        "classification_report": classification_report(y, pred, target_names=LABELS, output_dict=True, zero_division=0),
    }
    n = min(2000, len(X))
    t0 = time.perf_counter()
    for i in range(n):
        model.predict_proba(X.iloc[[i]])
    elapsed = time.perf_counter() - t0
    metrics["single_row_mean_latency_ms"] = float((elapsed / max(n,1))*1000)

    cm = confusion_matrix(y, pred, labels=list(range(len(LABELS))))
    pd.DataFrame(cm, index=[f"actual_{x}" for x in LABELS], columns=[f"pred_{x}" for x in LABELS]).to_csv(out_dir/f"{prefix}_confusion_matrix.csv")
    fig, ax = plt.subplots(figsize=(7, 6))
    im = ax.imshow(cm)
    ax.set_xticks(range(len(LABELS)), LABELS, rotation=30, ha="right")
    ax.set_yticks(range(len(LABELS)), LABELS)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Actual")
    ax.set_title(f"{prefix} confusion matrix")
    for i in range(len(LABELS)):
        for j in range(len(LABELS)):
            ax.text(j, i, str(cm[i,j]), ha="center", va="center")
    fig.tight_layout()
    fig.savefig(out_dir/f"{prefix}_confusion_matrix.png", dpi=160)
    plt.close(fig)
    (out_dir/f"{prefix}_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics
