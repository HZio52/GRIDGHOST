from __future__ import annotations
import argparse, json
from pathlib import Path
import optuna
import pandas as pd
from sklearn.metrics import f1_score
from xgboost import XGBClassifier
from ml.common import load_xy, group_split, balanced_weights, save_json
from ml.config import LABELS
from ml.evaluation import evaluate_and_save


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=Path("data/ml/training.csv"))
    ap.add_argument("--trials", type=int, default=30)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--model", type=Path, default=Path("models/gridghost_xgb_tuned.json"))
    ap.add_argument("--reports", type=Path, default=Path("reports/ml_tuned"))
    args = ap.parse_args()

    df, X, y, groups = load_xy(args.data)
    tr, va, te = group_split(df, X, y, groups, args.seed)
    Xtr, Xva, Xte = X.iloc[tr], X.iloc[va], X.iloc[te]
    ytr, yva, yte = y.iloc[tr], y.iloc[va], y.iloc[te]
    sw = balanced_weights(ytr)

    def objective(trial):
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 180, 800),
            "max_depth": trial.suggest_int("max_depth", 3, 9),
            "learning_rate": trial.suggest_float("learning_rate", 0.015, 0.20, log=True),
            "min_child_weight": trial.suggest_float("min_child_weight", 1.0, 12.0),
            "subsample": trial.suggest_float("subsample", 0.60, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.60, 1.0),
            "gamma": trial.suggest_float("gamma", 0.0, 2.0),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-4, 2.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 10.0, log=True),
        }
        model = XGBClassifier(
            objective="multi:softprob", num_class=len(LABELS), eval_metric="mlogloss",
            tree_method="hist", random_state=args.seed, n_jobs=-1,
            early_stopping_rounds=30, **params,
        )
        model.fit(Xtr, ytr, sample_weight=sw, eval_set=[(Xva, yva)], verbose=False)
        return f1_score(yva, model.predict(Xva), average="macro")

    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=args.seed))
    study.optimize(objective, n_trials=args.trials)
    best = study.best_params
    save_json({"best_macro_f1": study.best_value, "best_params": best, "trials": args.trials}, args.reports/"optuna_best.json")

    final = XGBClassifier(
        objective="multi:softprob", num_class=len(LABELS), eval_metric="mlogloss",
        tree_method="hist", random_state=args.seed, n_jobs=-1,
        early_stopping_rounds=35, **best,
    )
    final.fit(Xtr, ytr, sample_weight=sw, eval_set=[(Xva, yva)], verbose=False)
    args.model.parent.mkdir(parents=True, exist_ok=True)
    final.save_model(args.model)
    test_metrics = evaluate_and_save(final, Xte, yte, args.reports, "test_tuned")
    print(json.dumps({"best_validation_macro_f1": study.best_value, "best_params": best, "test": test_metrics}, indent=2))

if __name__ == "__main__":
    main()
