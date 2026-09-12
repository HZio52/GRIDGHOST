from __future__ import annotations
import argparse, json
from pathlib import Path
import pandas as pd
from xgboost import XGBClassifier
from ml.common import load_xy, group_split, balanced_weights, save_json
from ml.config import FEATURES, LABELS
from ml.evaluation import evaluate_and_save


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=Path("data/ml/training.csv"))
    ap.add_argument("--model", type=Path, default=Path("models/gridghost_xgb.json"))
    ap.add_argument("--reports", type=Path, default=Path("reports/ml"))
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    df, X, y, groups = load_xy(args.data)
    tr, va, te = group_split(df, X, y, groups, args.seed)
    Xtr, Xva, Xte = X.iloc[tr], X.iloc[va], X.iloc[te]
    ytr, yva, yte = y.iloc[tr], y.iloc[va], y.iloc[te]

    model = XGBClassifier(
        objective="multi:softprob", num_class=len(LABELS), eval_metric="mlogloss",
        n_estimators=500, max_depth=5, learning_rate=0.05,
        min_child_weight=2, subsample=0.85, colsample_bytree=0.85,
        reg_alpha=0.02, reg_lambda=1.0, gamma=0.0,
        tree_method="hist", random_state=args.seed, n_jobs=-1,
        early_stopping_rounds=35,
    )
    model.fit(Xtr, ytr, sample_weight=balanced_weights(ytr), eval_set=[(Xva, yva)], verbose=False)
    args.model.parent.mkdir(parents=True, exist_ok=True)
    model.save_model(args.model)

    val_metrics = evaluate_and_save(model, Xva, yva, args.reports, "validation")
    test_metrics = evaluate_and_save(model, Xte, yte, args.reports, "test")
    meta = {
        "model": "XGBoost multiclass policy imitation",
        "labels": LABELS, "features": FEATURES,
        "label_source": "GRIDGHOST V2 mathematical planner (bootstrap only)",
        "train_rows": len(tr), "validation_rows": len(va), "test_rows": len(te),
        "best_iteration": int(getattr(model, "best_iteration", model.n_estimators-1)),
        "validation_macro_f1": val_metrics["macro_f1"],
        "test_macro_f1": test_metrics["macro_f1"],
        "test_accuracy": test_metrics["accuracy"],
        "test_log_loss": test_metrics["log_loss"],
        "test_single_row_mean_latency_ms": test_metrics["single_row_mean_latency_ms"],
        "warning": "High score means imitation of the teacher on synthetic/augmented states, not proven race performance.",
    }
    save_json(meta, args.model.with_name("gridghost_xgb_metadata.json"))
    print(json.dumps(meta, indent=2))

if __name__ == "__main__":
    main()
