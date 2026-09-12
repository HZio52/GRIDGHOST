from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    log_loss,
)
from sklearn.model_selection import StratifiedGroupKFold
from xgboost import XGBClassifier


# ============================================================
# GRIDGHOST CORE MODEL CONFIGURATION
# ============================================================

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


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Evaluate the tuned GRIDGHOST Core XGBoost model "
            "using grouped out-of-fold predictions."
        )
    )

    parser.add_argument(
        "--data",
        type=Path,
        required=True,
        help="Training CSV containing features, action and source_group.",
    )

    parser.add_argument(
        "--tuning-report",
        type=Path,
        required=True,
        help="JSON report produced by tune_core_cv.py.",
    )

    parser.add_argument(
        "--folds",
        type=int,
        default=5,
        help="Number of StratifiedGroupKFold folds.",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports/ml/core_tuned_oof"),
        help="Directory where evaluation outputs are written.",
    )

    args = parser.parse_args()

    # --------------------------------------------------------
    # Validate input files
    # --------------------------------------------------------

    if not args.data.exists():
        raise FileNotFoundError(
            f"Training data not found: {args.data}"
        )

    if not args.tuning_report.exists():
        raise FileNotFoundError(
            f"Tuning report not found: {args.tuning_report}"
        )

    args.output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # Load dataset
    # --------------------------------------------------------

    df = pd.read_csv(args.data)

    required_columns = set(
        FEATURES + ["action", "source_group"]
    )

    missing_columns = sorted(
        required_columns - set(df.columns)
    )

    if missing_columns:
        raise ValueError(
            "Dataset is missing required columns: "
            + ", ".join(missing_columns)
        )

    # --------------------------------------------------------
    # Load tuned hyperparameters
    # --------------------------------------------------------

    with args.tuning_report.open(
        "r",
        encoding="utf-8",
    ) as handle:
        tuning = json.load(handle)

    if "best_params" not in tuning:
        raise ValueError(
            "Tuning report does not contain 'best_params'."
        )

    best_params = tuning["best_params"]

    # --------------------------------------------------------
    # Encode target labels
    # --------------------------------------------------------

    label_to_id = {
        label: index
        for index, label in enumerate(LABELS)
    }

    id_to_label = {
        index: label
        for label, index in label_to_id.items()
    }

    unknown_labels = sorted(
        set(df["action"].dropna().unique())
        - set(LABELS)
    )

    if unknown_labels:
        raise ValueError(
            f"Unknown action labels found: {unknown_labels}"
        )

    y = (
        df["action"]
        .map(label_to_id)
        .astype(int)
        .to_numpy()
    )

    X = df[FEATURES].copy()

    groups = (
        df["source_group"]
        .to_numpy()
    )

    print()
    print("=" * 72)
    print("GRIDGHOST TUNED CORE OOF EVALUATION")
    print("=" * 72)

    print(f"Rows          : {len(df)}")
    print(
        f"Source groups : "
        f"{df['source_group'].nunique()}"
    )
    print(f"Features      : {len(FEATURES)}")
    print(f"CV folds      : {args.folds}")

    print()
    print("Features:")

    for feature in FEATURES:
        print(f"  - {feature}")

    print()

    # --------------------------------------------------------
    # Grouped cross-validation
    # --------------------------------------------------------

    splitter = StratifiedGroupKFold(
        n_splits=args.folds,
        shuffle=True,
        random_state=42,
    )

    oof_probabilities = np.zeros(
        (len(df), len(LABELS)),
        dtype=np.float64,
    )

    oof_margins = np.zeros(
        (len(df), len(LABELS)),
        dtype=np.float64,
    )

    oof_predictions = np.zeros(
        len(df),
        dtype=np.int64,
    )

    oof_fold = np.zeros(
        len(df),
        dtype=np.int64,
    )

    fold_metrics = []

    # --------------------------------------------------------
    # Train one model per fold
    # --------------------------------------------------------

    for fold, (train_idx, val_idx) in enumerate(
        splitter.split(
            X,
            y,
            groups,
        ),
        start=1,
    ):

        train_groups = set(
            groups[train_idx]
        )

        validation_groups = set(
            groups[val_idx]
        )

        overlap = (
            train_groups
            & validation_groups
        )

        if overlap:
            raise RuntimeError(
                "GROUP LEAKAGE DETECTED: "
                f"{sorted(overlap)}"
            )

        model_params = {
            **best_params,
            "objective": "multi:softprob",
            "num_class": len(LABELS),
            "tree_method": "hist",
            "eval_metric": "mlogloss",
            "random_state": 42,
            "n_jobs": -1,
        }

        model = XGBClassifier(
            **model_params
        )

        # ----------------------------------------------------
        # Fit
        # ----------------------------------------------------

        model.fit(
            X.iloc[train_idx],
            y[train_idx],
            verbose=False,
        )

        # ----------------------------------------------------
        # Predict probabilities
        # ----------------------------------------------------

        probabilities = model.predict_proba(
            X.iloc[val_idx]
        )

        probabilities = np.asarray(
            probabilities,
            dtype=np.float64,
        )

        # XGBoost probabilities can differ from exactly 1.0
        # by tiny floating-point amounts such as ~1e-8.
        # Normalize each row explicitly before log-loss.
        row_sums = probabilities.sum(
            axis=1,
            keepdims=True,
        )

        if np.any(row_sums <= 0):
            raise RuntimeError(
                "Invalid probability row with sum <= 0."
            )

        probabilities = (
            probabilities
            / row_sums
        )

        predictions = np.argmax(
            probabilities,
            axis=1,
        )

        # ----------------------------------------------------
        # Raw margins for later probability calibration
        # ----------------------------------------------------

        dmatrix = xgb.DMatrix(
            X.iloc[val_idx],
            feature_names=FEATURES,
        )

        margins = (
            model
            .get_booster()
            .predict(
                dmatrix,
                output_margin=True,
            )
        )

        margins = np.asarray(
            margins,
            dtype=np.float64,
        )

        # ----------------------------------------------------
        # Store OOF results
        # ----------------------------------------------------

        oof_probabilities[
            val_idx
        ] = probabilities

        oof_margins[
            val_idx
        ] = margins

        oof_predictions[
            val_idx
        ] = predictions

        oof_fold[
            val_idx
        ] = fold

        # ----------------------------------------------------
        # Fold metrics
        # ----------------------------------------------------

        fold_macro_f1 = f1_score(
            y[val_idx],
            predictions,
            average="macro",
        )

        fold_accuracy = accuracy_score(
            y[val_idx],
            predictions,
        )

        fold_log_loss = log_loss(
            y[val_idx],
            probabilities,
            labels=list(
                range(len(LABELS))
            ),
        )

        fold_metrics.append(
            {
                "fold": fold,
                "train_rows": int(
                    len(train_idx)
                ),
                "validation_rows": int(
                    len(val_idx)
                ),
                "train_groups": int(
                    len(train_groups)
                ),
                "validation_groups": int(
                    len(validation_groups)
                ),
                "macro_f1": float(
                    fold_macro_f1
                ),
                "accuracy": float(
                    fold_accuracy
                ),
                "log_loss": float(
                    fold_log_loss
                ),
            }
        )

        print(
            f"Fold {fold}: "
            f"Macro-F1={fold_macro_f1:.6f}  "
            f"Accuracy={fold_accuracy:.6f}  "
            f"LogLoss={fold_log_loss:.6f}"
        )

    # --------------------------------------------------------
    # Sanity checks
    # --------------------------------------------------------

    if np.any(oof_fold == 0):
        raise RuntimeError(
            "Some rows did not receive an OOF prediction."
        )

    probability_sums = (
        oof_probabilities.sum(axis=1)
    )

    max_probability_deviation = float(
        np.max(
            np.abs(
                probability_sums - 1.0
            )
        )
    )

    # --------------------------------------------------------
    # Overall OOF metrics
    # --------------------------------------------------------

    accuracy = accuracy_score(
        y,
        oof_predictions,
    )

    macro_f1 = f1_score(
        y,
        oof_predictions,
        average="macro",
    )

    weighted_f1 = f1_score(
        y,
        oof_predictions,
        average="weighted",
    )

    loss = log_loss(
        y,
        oof_probabilities,
        labels=list(
            range(len(LABELS))
        ),
    )

    report = classification_report(
        y,
        oof_predictions,
        labels=list(
            range(len(LABELS))
        ),
        target_names=LABELS,
        output_dict=True,
        zero_division=0,
    )

    matrix = confusion_matrix(
        y,
        oof_predictions,
        labels=list(
            range(len(LABELS))
        ),
    )

    # --------------------------------------------------------
    # Save metrics.json
    # --------------------------------------------------------

    metrics = {
        "model": "GRIDGHOST Tuned Core XGBoost",
        "evaluation": "5-fold grouped out-of-fold",
        "label_source": (
            "GRIDGHOST V2 mathematical planner "
            "(bootstrap only)"
        ),
        "feature_count": len(FEATURES),
        "features": FEATURES,
        "rows": int(len(df)),
        "source_groups": int(
            df["source_group"].nunique()
        ),
        "cv_folds": int(args.folds),
        "accuracy": float(accuracy),
        "macro_f1": float(macro_f1),
        "weighted_f1": float(
            weighted_f1
        ),
        "log_loss": float(loss),
        "max_probability_sum_deviation": (
            max_probability_deviation
        ),
        "best_params": best_params,
        "classification_report": report,
        "fold_metrics": fold_metrics,
    }

    metrics_path = (
        args.output_dir
        / "metrics.json"
    )

    with metrics_path.open(
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            metrics,
            handle,
            indent=2,
        )

    # --------------------------------------------------------
    # Save confusion matrix
    # --------------------------------------------------------

    matrix_df = pd.DataFrame(
        matrix,
        index=[
            f"actual_{label}"
            for label in LABELS
        ],
        columns=[
            f"pred_{label}"
            for label in LABELS
        ],
    )

    matrix_path = (
        args.output_dir
        / "confusion_matrix.csv"
    )

    matrix_df.to_csv(
        matrix_path,
        index=True,
        index_label="actual",
    )

    # --------------------------------------------------------
    # Save OOF predictions
    # --------------------------------------------------------

    predictions_df = pd.DataFrame(
        {
            "source_group":
                groups,

            "fold":
                oof_fold,

            "actual":
                [
                    id_to_label[
                        int(index)
                    ]
                    for index in y
                ],

            "predicted":
                [
                    id_to_label[
                        int(index)
                    ]
                    for index
                    in oof_predictions
                ],

            "prob_ATTACK":
                oof_probabilities[:, 0],

            "prob_DEFEND":
                oof_probabilities[:, 1],

            "prob_HOLD":
                oof_probabilities[:, 2],

            "prob_CONSERVE":
                oof_probabilities[:, 3],

            "margin_ATTACK":
                oof_margins[:, 0],

            "margin_DEFEND":
                oof_margins[:, 1],

            "margin_HOLD":
                oof_margins[:, 2],

            "margin_CONSERVE":
                oof_margins[:, 3],
        }
    )

    predictions_path = (
        args.output_dir
        / "oof_predictions.csv"
    )

    predictions_df.to_csv(
        predictions_path,
        index=False,
    )

    # --------------------------------------------------------
    # Save fold metrics separately
    # --------------------------------------------------------

    fold_metrics_path = (
        args.output_dir
        / "fold_metrics.csv"
    )

    pd.DataFrame(
        fold_metrics
    ).to_csv(
        fold_metrics_path,
        index=False,
    )

    # --------------------------------------------------------
    # Console summary
    # --------------------------------------------------------

    print()
    print("=" * 72)
    print("GRIDGHOST TUNED CORE OOF EVALUATION")
    print("=" * 72)

    print(
        f"Accuracy    : {accuracy:.6f}"
    )

    print(
        f"Macro-F1    : {macro_f1:.6f}"
    )

    print(
        f"Weighted-F1 : {weighted_f1:.6f}"
    )

    print(
        f"Log loss    : {loss:.6f}"
    )

    print(
        "Probability max deviation from 1.0: "
        f"{max_probability_deviation:.12e}"
    )

    print()
    print("PER-CLASS RESULTS")
    print("-" * 72)

    for label in LABELS:

        stats = report[label]

        print(
            f"{label:10s} "
            f"P={stats['precision']:.4f}  "
            f"R={stats['recall']:.4f}  "
            f"F1={stats['f1-score']:.4f}  "
            f"N={int(stats['support'])}"
        )

    print()
    print("CONFUSION MATRIX")
    print("-" * 72)

    print(matrix_df)

    print()
    print("=" * 72)
    print("OUTPUT FILES")
    print("=" * 72)

    print(
        f"Metrics       -> {metrics_path}"
    )

    print(
        f"Matrix        -> {matrix_path}"
    )

    print(
        f"OOF data      -> {predictions_path}"
    )

    print(
        f"Fold metrics  -> {fold_metrics_path}"
    )


if __name__ == "__main__":
    main()