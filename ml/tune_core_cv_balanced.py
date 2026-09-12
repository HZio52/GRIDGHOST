from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import optuna
import pandas as pd

from sklearn.metrics import f1_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.utils.class_weight import compute_sample_weight
from xgboost import XGBClassifier


LABELS = [
    "ATTACK",
    "DEFEND",
    "HOLD",
    "CONSERVE",
]


FEATURES = [
    "own_speed_kph",
    "rival_speed_kph",
    "speed_delta_kph",
    "gap_s",
    "gap_rate_s_per_s",
    "own_energy_mj",
    "energy_uncertainty_mj",
    "recovery_kw",
    "recovery_uncertainty_kw",
]


def main() -> None:

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--data",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--trials",
        type=int,
        default=30,
    )

    parser.add_argument(
        "--folds",
        type=int,
        default=5,
    )

    parser.add_argument(
        "--model",
        type=Path,
        default=Path(
            "models/gridghost_core_tuned_balanced.json"
        ),
    )

    parser.add_argument(
        "--report",
        type=Path,
        default=Path(
            "reports/ml/core_cv_tuning_balanced.json"
        ),
    )

    args = parser.parse_args()

    df = pd.read_csv(args.data)

    required = set(
        FEATURES + ["action", "source_group"]
    )

    missing = sorted(
        required - set(df.columns)
    )

    if missing:
        raise ValueError(
            f"Missing columns: {missing}"
        )

    X = df[FEATURES].copy()

    label_to_id = {
        label: index
        for index, label in enumerate(LABELS)
    }

    y = (
        df["action"]
        .map(label_to_id)
        .astype(int)
        .to_numpy()
    )

    groups = (
        df["source_group"]
        .to_numpy()
    )

    splitter = StratifiedGroupKFold(
        n_splits=args.folds,
        shuffle=True,
        random_state=42,
    )

    # Freeze the exact same folds for every trial.
    splits = list(
        splitter.split(
            X,
            y,
            groups,
        )
    )

    print()
    print("=" * 72)
    print("GRIDGHOST BALANCED CORE CV TUNING")
    print("=" * 72)

    print(f"Rows          : {len(df)}")
    print(
        f"Source groups : "
        f"{df['source_group'].nunique()}"
    )
    print(f"Features      : {len(FEATURES)}")
    print(f"CV folds      : {args.folds}")
    print(f"Optuna trials : {args.trials}")
    print()

    def objective(trial: optuna.Trial) -> float:

        params = {
            "objective": "multi:softprob",
            "num_class": len(LABELS),
            "tree_method": "hist",
            "eval_metric": "mlogloss",
            "random_state": 42,
            "n_jobs": -1,

            "n_estimators": trial.suggest_int(
                "n_estimators",
                200,
                700,
            ),

            "max_depth": trial.suggest_int(
                "max_depth",
                3,
                9,
            ),

            "learning_rate": trial.suggest_float(
                "learning_rate",
                0.015,
                0.20,
                log=True,
            ),

            "min_child_weight":
                trial.suggest_float(
                    "min_child_weight",
                    1.0,
                    12.0,
                ),

            "subsample": trial.suggest_float(
                "subsample",
                0.60,
                1.0,
            ),

            "colsample_bytree":
                trial.suggest_float(
                    "colsample_bytree",
                    0.60,
                    1.0,
                ),

            "gamma": trial.suggest_float(
                "gamma",
                0.0,
                2.0,
            ),

            "reg_alpha": trial.suggest_float(
                "reg_alpha",
                1e-4,
                2.0,
                log=True,
            ),

            "reg_lambda": trial.suggest_float(
                "reg_lambda",
                1e-3,
                10.0,
                log=True,
            ),
        }

        fold_scores = []

        for train_idx, val_idx in splits:

            train_groups = set(
                groups[train_idx]
            )

            val_groups = set(
                groups[val_idx]
            )

            if train_groups & val_groups:
                raise RuntimeError(
                    "Group leakage detected."
                )

            train_weights = compute_sample_weight(
                class_weight="balanced",
                y=y[train_idx],
            )

            model = XGBClassifier(
                **params
            )

            model.fit(
                X.iloc[train_idx],
                y[train_idx],
                sample_weight=train_weights,
                verbose=False,
            )

            predictions = model.predict(
                X.iloc[val_idx]
            )

            score = f1_score(
                y[val_idx],
                predictions,
                average="macro",
            )

            fold_scores.append(
                score
            )

        return float(
            np.mean(fold_scores)
        )

    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(
            seed=42
        ),
    )

    study.optimize(
        objective,
        n_trials=args.trials,
    )

    print()
    print("=" * 72)
    print("BEST BALANCED GROUPED-CV RESULT")
    print("=" * 72)

    print(
        f"Mean Macro-F1: "
        f"{study.best_value}"
    )

    print()
    print("Best parameters:")

    for key, value in study.best_params.items():
        print(
            f"{key:22s}: {value}"
        )

    # ========================================================
    # Final model on all available bootstrap data
    # ========================================================

    final_params = {
        **study.best_params,
        "objective": "multi:softprob",
        "num_class": len(LABELS),
        "tree_method": "hist",
        "eval_metric": "mlogloss",
        "random_state": 42,
        "n_jobs": -1,
    }

    final_weights = compute_sample_weight(
        class_weight="balanced",
        y=y,
    )

    final_model = XGBClassifier(
        **final_params
    )

    final_model.fit(
        X,
        y,
        sample_weight=final_weights,
        verbose=False,
    )

    args.model.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    final_model.save_model(
        args.model
    )

    report = {
        "model":
            "GRIDGHOST Balanced Core XGBoost",

        "feature_count":
            len(FEATURES),

        "features":
            FEATURES,

        "training_rows":
            int(len(df)),

        "source_groups":
            int(
                df["source_group"]
                .nunique()
            ),

        "cv_folds":
            int(args.folds),

        "optuna_trials":
            int(args.trials),

        "class_weighting":
            "balanced",

        "best_cv_macro_f1":
            float(
                study.best_value
            ),

        "best_params":
            study.best_params,

        "label_source":
            (
                "GRIDGHOST V2 mathematical planner "
                "(bootstrap only)"
            ),
    }

    args.report.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with args.report.open(
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            report,
            handle,
            indent=2,
        )

    print()
    print(
        f"Model saved -> {args.model}"
    )

    print(
        f"Report saved -> {args.report}"
    )


if __name__ == "__main__":
    main()